"""Versioned request contract for arbitrary polygon/date-range Know Place jobs.

This parser intentionally validates requests only. It does not assert that
catalog coverage exists, that a displacement is measurable, or that an event
has been detected. Source-adapter availability and scientific status are
reported by later pipeline stages.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from typing import Any

from .geometry import parse_polygon_wkt
from .goff_io import GoffReadError

REQUEST_SCHEMA = "know-place-aoi-request/1.0"
SUPPORTED_HAZARDS = {"landslide", "glacier_collapse", "ice_rock_avalanche", "mixed"}
SUPPORTED_ADAPTERS = {"NISAR_GOFF"}
SUPPORTED_MODES = {"retrospective_validation", "operational_monitoring", "exploratory"}


class AOIRequestError(ValueError):
    """A user AOI request is malformed, unsupported or scientifically ambiguous."""


@dataclass(frozen=True)
class AOIRequest:
    schema_version: str
    aoi_wkt: str
    aoi_crs: str
    start_date: date
    end_date: date
    hazard_mode: str
    analysis_mode: str
    source_adapters: tuple[str, ...]
    polarization: str
    reference_wkt: str | None
    min_snr: float
    max_horizontal_magnitude_m: float
    coherence_window: int
    minimum_valid_neighbours: int
    request_sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Return stable, JSON-safe normalized parameters (not raw secrets)."""
        return {
            "schema_version": self.schema_version,
            "aoi": {"type": "Polygon", "wkt": self.aoi_wkt, "crs": self.aoi_crs},
            "date_range": {
                "start": self.start_date.isoformat(),
                "end": self.end_date.isoformat(),
                "inclusive": True,
                "timezone": "UTC",
            },
            "hazard_mode": self.hazard_mode,
            "analysis_mode": self.analysis_mode,
            "source_adapters": list(self.source_adapters),
            "polarization": self.polarization,
            "reference": {
                "policy": "external_reference_polygon_component_median"
                if self.reference_wkt else "no_background_correction",
                "polygon_wkt": self.reference_wkt,
            },
            "quality_policy": {
                "name": "nisar_goff_exploratory_v1",
                "minimum_snr": self.min_snr,
                "maximum_horizontal_magnitude_m": self.max_horizontal_magnitude_m,
                "gross_outlier_policy": "reject_not_clip",
            },
            "coherence_policy": {
                "window_size": self.coherence_window,
                "minimum_valid_neighbours": self.minimum_valid_neighbours,
                "policy_status": "explicit_versioned_user_request_not_author_parity",
            },
            "request_sha256": self.request_sha256,
        }


def _strict_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise AOIRequestError(f"{field.upper()}_MUST_BE_ISO_DATE")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise AOIRequestError(f"{field.upper()}_MUST_BE_ISO_DATE") from exc
    if parsed.isoformat() != value:
        raise AOIRequestError(f"{field.upper()}_MUST_BE_CANONICAL_ISO_DATE")
    return parsed


def _canonical_wkt(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AOIRequestError(f"{field.upper()}_WKT_REQUIRED")
    try:
        ring = parse_polygon_wkt(value)
    except GoffReadError as exc:
        raise AOIRequestError(f"{field.upper()}_GEOMETRY_INVALID:{exc}") from exc
    return "POLYGON ((" + ", ".join(f"{lon:.9f} {lat:.9f}" for lon, lat in ring) + "))"


def validate_aoi_request(payload: dict[str, Any]) -> AOIRequest:
    """Validate and normalize a v1 request; fail closed on unsupported geometry."""
    if not isinstance(payload, dict):
        raise AOIRequestError("REQUEST_MUST_BE_JSON_OBJECT")
    if payload.get("schema_version") != REQUEST_SCHEMA:
        raise AOIRequestError("REQUEST_SCHEMA_VERSION_UNSUPPORTED")

    aoi = payload.get("aoi")
    if not isinstance(aoi, dict):
        raise AOIRequestError("AOI_OBJECT_REQUIRED")
    crs = str(aoi.get("crs", "EPSG:4326")).upper()
    if crs not in {"EPSG:4326", "OGC:CRS84"}:
        raise AOIRequestError("AOI_CRS_MUST_BE_EPSG4326_OR_CRS84")
    aoi_wkt = _canonical_wkt(aoi.get("wkt"), "aoi")

    dates = payload.get("date_range")
    if not isinstance(dates, dict):
        raise AOIRequestError("DATE_RANGE_OBJECT_REQUIRED")
    start_date = _strict_date(dates.get("start"), "start_date")
    end_date = _strict_date(dates.get("end"), "end_date")
    if start_date > end_date:
        raise AOIRequestError("DATE_RANGE_START_AFTER_END")
    if dates.get("inclusive", True) is not True:
        raise AOIRequestError("DATE_RANGE_MUST_BE_INCLUSIVE")

    hazard_mode = str(payload.get("hazard_mode", "mixed")).lower()
    if hazard_mode not in SUPPORTED_HAZARDS:
        raise AOIRequestError("HAZARD_MODE_UNSUPPORTED")
    analysis_mode = str(payload.get("analysis_mode", "exploratory")).lower()
    if analysis_mode not in SUPPORTED_MODES:
        raise AOIRequestError("ANALYSIS_MODE_UNSUPPORTED")

    adapters = payload.get("source_adapters", ["NISAR_GOFF"])
    if not isinstance(adapters, list) or not adapters:
        raise AOIRequestError("AT_LEAST_ONE_SOURCE_ADAPTER_REQUIRED")
    normalized_adapters = tuple(sorted({str(item).upper() for item in adapters}))
    unsupported = sorted(set(normalized_adapters) - SUPPORTED_ADAPTERS)
    if unsupported:
        raise AOIRequestError("SOURCE_ADAPTER_UNSUPPORTED:" + ",".join(unsupported))

    polarization = str(payload.get("polarization", "HH")).upper()
    if polarization not in {"HH", "HV", "VV", "VH"}:
        raise AOIRequestError("POLARIZATION_UNSUPPORTED")

    reference = payload.get("reference")
    reference_wkt = None
    if reference is not None:
        if not isinstance(reference, dict):
            raise AOIRequestError("REFERENCE_MUST_BE_OBJECT")
        policy = reference.get("policy", "external_reference_polygon_component_median")
        if policy != "external_reference_polygon_component_median":
            raise AOIRequestError("REFERENCE_POLICY_UNSUPPORTED")
        reference_wkt = _canonical_wkt(reference.get("polygon_wkt"), "reference")
        # Full geometric containment/intersection is revalidated when the ROI is
        # rasterized on the actual source grid; this request parser checks syntax.

    quality = payload.get("quality_policy", {})
    if not isinstance(quality, dict):
        raise AOIRequestError("QUALITY_POLICY_MUST_BE_OBJECT")
    try:
        min_snr = float(quality.get("minimum_snr", 5.0))
        max_magnitude = float(quality.get("maximum_horizontal_magnitude_m", 10.0))
    except (TypeError, ValueError, OverflowError) as exc:
        raise AOIRequestError("QUALITY_THRESHOLDS_MUST_BE_NUMERIC") from exc
    if not math.isfinite(min_snr) or min_snr < 0:
        raise AOIRequestError("MINIMUM_SNR_INVALID")
    if not math.isfinite(max_magnitude) or max_magnitude <= 0:
        raise AOIRequestError("MAXIMUM_HORIZONTAL_MAGNITUDE_INVALID")

    coherence = payload.get("coherence_policy", {})
    if not isinstance(coherence, dict):
        raise AOIRequestError("COHERENCE_POLICY_MUST_BE_OBJECT")
    window = coherence.get("window_size", 5)
    neighbours = coherence.get("minimum_valid_neighbours", 1)
    if isinstance(window, bool) or not isinstance(window, int) or window < 1 or window % 2 == 0:
        raise AOIRequestError("COHERENCE_WINDOW_MUST_BE_POSITIVE_ODD_INTEGER")
    if isinstance(neighbours, bool) or not isinstance(neighbours, int) or not (1 <= neighbours <= window * window):
        raise AOIRequestError("COHERENCE_NEIGHBOURS_OUT_OF_RANGE")

    normalized = {
        "schema_version": REQUEST_SCHEMA,
        "aoi": {"wkt": aoi_wkt, "crs": "EPSG:4326"},
        "date_range": {"start": start_date.isoformat(), "end": end_date.isoformat(), "inclusive": True},
        "hazard_mode": hazard_mode,
        "analysis_mode": analysis_mode,
        "source_adapters": list(normalized_adapters),
        "polarization": polarization,
        "reference": {"polygon_wkt": reference_wkt, "policy": "external_reference_polygon_component_median" if reference_wkt else "no_background_correction"},
        "quality_policy": {"minimum_snr": min_snr, "maximum_horizontal_magnitude_m": max_magnitude},
        "coherence_policy": {"window_size": window, "minimum_valid_neighbours": neighbours},
    }
    digest = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    return AOIRequest(
        schema_version=REQUEST_SCHEMA,
        aoi_wkt=aoi_wkt,
        aoi_crs="EPSG:4326",
        start_date=start_date,
        end_date=end_date,
        hazard_mode=hazard_mode,
        analysis_mode=analysis_mode,
        source_adapters=normalized_adapters,
        polarization=polarization,
        reference_wkt=reference_wkt,
        min_snr=min_snr,
        max_horizontal_magnitude_m=max_magnitude,
        coherence_window=window,
        minimum_valid_neighbours=neighbours,
        request_sha256=digest,
    )
