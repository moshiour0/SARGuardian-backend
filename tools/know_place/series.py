"""Deterministic selector for an arbitrary AOI/date-range GOFF pair series.

The selector deliberately keeps pairwise observations separate. It never sums
overlapping or gapped intervals into a cumulative displacement, and it fails
closed when release variants or incompatible orbit geometries are ambiguous.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .goff_io import GoffReadError, parse_granule_identity


class SeriesPlanError(ValueError):
    """The catalog candidate set cannot define one reproducible measurement series."""


@dataclass(frozen=True)
class PairCandidate:
    granule_name: str
    reference_start: datetime
    secondary_start: datetime
    track: str
    direction: str
    polarization: str
    release_id: str
    maturity: str
    source_sha256: str | None
    source_bytes: int | None

    @property
    def pair_key(self) -> tuple[datetime, datetime]:
        return self.reference_start, self.secondary_start

    @property
    def geometry_key(self) -> tuple[str, str, str]:
        return self.track, self.direction, self.polarization

    def to_dict(self) -> dict[str, Any]:
        return {
            "granule_name": self.granule_name,
            "reference_start_utc": self.reference_start.astimezone(timezone.utc).isoformat(),
            "secondary_start_utc": self.secondary_start.astimezone(timezone.utc).isoformat(),
            "reference_date": self.reference_start.date().isoformat(),
            "secondary_date": self.secondary_start.date().isoformat(),
            "interval_days": (self.secondary_start - self.reference_start).total_seconds() / 86400.0,
            "track": self.track,
            "direction": self.direction,
            "polarization": self.polarization,
            "release_id": self.release_id,
            "catalog_maturity": self.maturity,
            "source_sha256": self.source_sha256,
            "source_bytes": self.source_bytes,
        }


def _normalize_direction(value: Any) -> str:
    direction = str(value or "").strip().upper()
    aliases = {"ASCENDING": "A", "ASC": "A", "A": "A", "DESCENDING": "D", "DESC": "D", "D": "D"}
    try:
        return aliases[direction]
    except KeyError as exc:
        raise SeriesPlanError(f"PRODUCT_DIRECTION_INVALID:{direction or 'MISSING'}") from exc


def _parse_candidate(record: dict[str, Any], *, requested_polarization: str) -> PairCandidate:
    raw_name = record.get("granule_name") or record.get("source_filename") or record.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise SeriesPlanError("PRODUCT_GRANULE_NAME_MISSING")
    name = Path(raw_name).name
    try:
        identity = parse_granule_identity(name)
    except GoffReadError as exc:
        raise SeriesPlanError(f"PRODUCT_GRANULE_IDENTITY_INVALID:{name}:{exc}") from exc

    polarization = str(record.get("polarization", requested_polarization)).upper()
    if polarization != requested_polarization:
        raise SeriesPlanError(f"PRODUCT_POLARIZATION_MISMATCH:{name}")
    direction = _normalize_direction(record.get("direction", identity.direction))
    track = str(record.get("track", identity.track)).zfill(3)
    if track != identity.track or direction != identity.direction:
        raise SeriesPlanError(f"PRODUCT_METADATA_FILENAME_CONFLICT:{name}")
    if identity.secondary_start <= identity.reference_start:
        raise SeriesPlanError(f"PRODUCT_INTERVAL_NOT_POSITIVE:{name}")

    raw_size = record.get("source_bytes") or record.get("file_size_bytes") or record.get("size_bytes")
    source_bytes = None
    if raw_size is not None:
        if isinstance(raw_size, bool) or not isinstance(raw_size, int) or raw_size < 0:
            raise SeriesPlanError(f"PRODUCT_SOURCE_SIZE_INVALID:{name}")
        source_bytes = raw_size
    sha = record.get("source_sha256") or record.get("sha256")
    if sha is not None and (not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha)):
        raise SeriesPlanError(f"PRODUCT_SOURCE_SHA256_INVALID:{name}")

    return PairCandidate(
        granule_name=name,
        reference_start=identity.reference_start.replace(tzinfo=timezone.utc),
        secondary_start=identity.secondary_start.replace(tzinfo=timezone.utc),
        track=track,
        direction=direction,
        polarization=polarization,
        release_id=str(record.get("release_id") or identity.release_id or "UNKNOWN"),
        maturity=str(record.get("maturity") or record.get("catalog_maturity") or "UNVERIFIED").upper(),
        source_sha256=sha.lower() if isinstance(sha, str) else None,
        source_bytes=source_bytes,
    )


def build_pairwise_series_plan(
    records: Iterable[dict[str, Any]],
    *,
    start_date: date,
    end_date: date,
    polarization: str = "HH",
    track: str | None = None,
    direction: str | None = None,
    preferred_granules: Iterable[str] = (),
    adjacency_tolerance_seconds: int = 120,
) -> dict[str, Any]:
    """Build a source-provenance-preserving pairwise series from catalog records.

    Both acquisitions of each product must fall inside the requested inclusive
    date range. A single track/direction/polarization chain is required. More
    than one product release for the same acquisition pair is an explicit
    ambiguity unless the caller pins the exact granule name.
    """
    if start_date > end_date:
        raise SeriesPlanError("DATE_RANGE_START_AFTER_END")
    if polarization.upper() not in {"HH", "HV", "VV", "VH"}:
        raise SeriesPlanError("POLARIZATION_UNSUPPORTED")
    if adjacency_tolerance_seconds < 0:
        raise SeriesPlanError("ADJACENCY_TOLERANCE_MUST_BE_NONNEGATIVE")

    selected_names = {Path(name).name for name in preferred_granules}
    start_bound = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_bound = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    candidates: list[PairCandidate] = []
    for record in records:
        if not isinstance(record, dict):
            raise SeriesPlanError("PRODUCT_RECORD_MUST_BE_OBJECT")
        reported_pol = str(record.get("polarization", "")).upper()
        if reported_pol:
            represented = {part.strip() for part in reported_pol.replace(",", "+").split("+") if part.strip()}
            if polarization.upper() not in represented and reported_pol != polarization.upper():
                continue
            record = {**record, "polarization": polarization.upper()}
        candidate = _parse_candidate(record, requested_polarization=polarization.upper())
        if candidate.reference_start < start_bound or candidate.secondary_start >= end_bound:
            continue
        if selected_names and candidate.granule_name not in selected_names:
            continue
        if track is not None and candidate.track != str(track).zfill(3):
            continue
        if direction is not None and candidate.direction != _normalize_direction(direction):
            continue
        candidates.append(candidate)

    if selected_names:
        found = {c.granule_name for c in candidates}
        absent = sorted(selected_names - found)
        if absent:
            raise SeriesPlanError("PINNED_GRANULE_NOT_IN_REQUEST_WINDOW:" + ",".join(absent))
    if not candidates:
        raise SeriesPlanError("NO_GOFF_PRODUCTS_FULLY_WITHIN_REQUEST_DATE_RANGE")

    geometry_groups: dict[tuple[str, str, str], list[PairCandidate]] = {}
    for candidate in candidates:
        geometry_groups.setdefault(candidate.geometry_key, []).append(candidate)
    if len(geometry_groups) != 1:
        options = [
            {"track": key[0], "direction": key[1], "polarization": key[2], "candidate_count": len(value)}
            for key, value in sorted(geometry_groups.items())
        ]
        raise SeriesPlanError("AMBIGUOUS_ORBIT_GEOMETRY_SERIES:" + str(options))

    # Same acquisition pair may be published in multiple releases. Never choose
    # one just because it happens to reproduce a preferred statistic.
    variants: dict[tuple[datetime, datetime], list[PairCandidate]] = {}
    for candidate in candidates:
        variants.setdefault(candidate.pair_key, []).append(candidate)
    ambiguous = {
        pair: sorted(item.granule_name for item in group)
        for pair, group in variants.items() if len(group) > 1
    }
    if ambiguous:
        raise SeriesPlanError("AMBIGUOUS_PRODUCT_RELEASE_VARIANTS:" + str(ambiguous))

    ordered = sorted(candidates, key=lambda c: (c.reference_start, c.secondary_start, c.granule_name))
    rows: list[dict[str, Any]] = []
    previous: PairCandidate | None = None
    continuous = True
    for candidate in ordered:
        row = candidate.to_dict()
        if previous is None:
            row["relation_to_previous"] = "FIRST_PAIR"
            row["gap_seconds_from_previous_secondary_to_reference"] = None
            row["pair_intervals_overlap"] = False
        else:
            delta = (candidate.reference_start - previous.secondary_start).total_seconds()
            adjacent = abs(delta) <= adjacency_tolerance_seconds
            overlaps = candidate.reference_start < previous.secondary_start - timedelta(seconds=adjacency_tolerance_seconds)
            row["relation_to_previous"] = "CONTIGUOUS" if adjacent else ("OVERLAP" if overlaps else "GAP")
            row["gap_seconds_from_previous_secondary_to_reference"] = delta
            row["pair_intervals_overlap"] = overlaps
            if not adjacent:
                continuous = False
        rows.append(row)
        previous = candidate

    return {
        "schema_version": "know-place-pairwise-series-plan/1.0",
        "status": "PAIRWISE_SERIES_PLANNED",
        "date_range_inclusive": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "geometry_key": {
            "track": ordered[0].track,
            "direction": ordered[0].direction,
            "polarization": ordered[0].polarization,
        },
        "pair_count": len(rows),
        "pairs": rows,
        "pairwise_metrics_are_not_cumulative": True,
        "continuous_chain_eligible": bool(rows) and continuous,
        "cumulative_displacement_status": (
            "ELIGIBLE_FOR_SEPARATE_REVIEW" if len(rows) > 1 and continuous
            else "NOT_ELIGIBLE_GAPS_OR_OVERLAPS_OR_SINGLE_PAIR"
        ),
        "selection_policy": {
            "release_substitution": "forbidden",
            "geometry_mixing": "forbidden",
            "date_policy": "both pair acquisitions must lie inside inclusive user date range",
            "pairwise_metric_policy": "report each product interval independently; do not sum overlapping/gapped pair estimates",
        },
        "warnings": [
            "A planned pair series only establishes candidate availability and chronology. It does not establish valid pixel support, scientific reproduction, or hazard detection.",
            "A continuous acquisition chain is necessary but not sufficient for cumulative displacement; projection, reference, sign convention, grid parity and uncertainty still require validation.",
        ],
    }
