"""Summarize observed target-relative movement from eligible graph-inverted series.

This stage only transforms already-gated GUNW/GOFF component series. It never
fills gaps, interpolates epochs, mixes measurement families, converts LOS to
3-D motion, or interprets a diagnostic series as a hazard declaration.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path
from typing import Any


SERIES_AVAILABLE = "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED"
REPORT_SCHEMA = "sarguardian-observed-movement-measurements/1.0"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _component_records(
    report: dict[str, Any],
    *,
    family: str,
    value_field: str,
    measurement_label: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    components = report.get("components")
    if not isinstance(components, list):
        return records

    for component in components:
        if not isinstance(component, dict) or component.get("status") != SERIES_AVAILABLE:
            continue
        raw_series = component.get("series")
        if not isinstance(raw_series, list):
            continue

        parsed: list[dict[str, Any]] = []
        valid = True
        for point in raw_series:
            if not isinstance(point, dict):
                valid = False
                break
            epoch = _iso_date(point.get("epoch"))
            value = _finite(point.get(value_field))
            if epoch is None or value is None:
                valid = False
                break
            error = _finite(point.get("graph_fit_standard_error_mm"))
            parsed.append({
                "epoch": epoch.isoformat(),
                "value_mm": value,
                "graph_fit_standard_error_mm": error,
            })

        # Reject duplicate/out-of-order epochs rather than silently sort or
        # collapse them; the source graph output must already be well formed.
        if not valid or len(parsed) < 3:
            continue
        if any(
            _iso_date(parsed[i]["epoch"]) is None
            or _iso_date(parsed[i + 1]["epoch"]) <= _iso_date(parsed[i]["epoch"])
            for i in range(len(parsed) - 1)
        ):
            continue

        first_day = _iso_date(parsed[0]["epoch"])
        last_day = _iso_date(parsed[-1]["epoch"])
        if first_day is None or last_day is None:
            continue
        span_days = (last_day - first_day).days
        if span_days <= 0:
            continue

        first_value = parsed[0]["value_mm"]
        last_value = parsed[-1]["value_mm"]
        delta = last_value - first_value
        relative_series = [{
            "epoch": item["epoch"],
            "cumulative_value_mm": item["value_mm"],
            "relative_to_first_epoch_mm": item["value_mm"] - first_value,
            "graph_fit_standard_error_mm": item["graph_fit_standard_error_mm"],
        } for item in parsed]

        network = str(component.get("network") or "UNLABELLED_NETWORK")
        component_label = str(component.get("component") or component.get("component_index") or "1")
        graph_velocity = _finite(component.get("velocity_mm_per_day"))
        graph_velocity_error = _finite(component.get("velocity_fit_error_mm_per_day"))
        records.append({
            "measurement_id": f"{family}:{network}:component-{component_label}",
            "measurement_family": family,
            "measurement_label": measurement_label,
            "units": "mm",
            "network": network,
            "component": component_label,
            "source_report_status": report.get("status"),
            "source_component_status": component.get("status"),
            "first_epoch": first_day.isoformat(),
            "last_epoch": last_day.isoformat(),
            "epoch_count": len(parsed),
            "pairs_count": int(component.get("pairs_count") or 0),
            "redundancy": int(component.get("redundancy") or 0),
            "duration_days": span_days,
            "first_value_mm": first_value,
            "last_value_mm": last_value,
            "net_change_from_first_epoch_mm": delta,
            "endpoint_rate_mm_per_day": delta / span_days,
            "graph_fit_velocity_mm_per_day": graph_velocity,
            "graph_fit_velocity_standard_error_mm_per_day": graph_velocity_error,
            "reference_status": "AOI_DERIVED_REFERENCE_NOT_INDEPENDENTLY_VALIDATED",
            "independent_geophysical_validation": False,
            "series": relative_series,
            "interpretation": (
                "Observed target-relative graph-inverted series using an AOI-derived common reference; "
                "not absolute ground motion, a 3-D solution, a hazard alarm, or a forecast."
            ),
        })
    return records


def _write_outputs(output_root: Path, report: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "observed-movement-measurements.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    rows: list[dict[str, Any]] = []
    for measurement in report.get("measurements", []):
        for point in measurement.get("series", []):
            rows.append({
                "measurement_id": measurement.get("measurement_id"),
                "measurement_family": measurement.get("measurement_family"),
                "measurement_label": measurement.get("measurement_label"),
                "network": measurement.get("network"),
                "component": measurement.get("component"),
                "epoch": point.get("epoch"),
                "cumulative_value_mm": point.get("cumulative_value_mm"),
                "relative_to_first_epoch_mm": point.get("relative_to_first_epoch_mm"),
                "graph_fit_standard_error_mm": point.get("graph_fit_standard_error_mm"),
                "reference_status": measurement.get("reference_status"),
                "independent_geophysical_validation": measurement.get("independent_geophysical_validation"),
            })
    if rows:
        with (output_root / "observed-movement-measurements.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    else:
        # A header-only table is a useful explicit output; it cannot be
        # mistaken for measured values.
        with (output_root / "observed-movement-measurements.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=[
                "measurement_id", "measurement_family", "measurement_label", "network",
                "component", "epoch", "cumulative_value_mm", "relative_to_first_epoch_mm",
                "graph_fit_standard_error_mm", "reference_status", "independent_geophysical_validation",
            ])
            writer.writeheader()


def build_observed_movement_report(
    gunw_report: dict[str, Any] | None,
    goff_report: dict[str, Any] | None,
    output_root: Path,
    *,
    aoi_wkt_sha256: str | None = None,
) -> dict[str, Any]:
    """Publish eligible observed movement summaries without inventing missing epochs."""
    gunw = gunw_report if isinstance(gunw_report, dict) else {}
    goff = goff_report if isinstance(goff_report, dict) else {}
    measurements = _component_records(
        gunw, family="GUNW_LOS", value_field="cumulative_los_mm",
        measurement_label="Cumulative line-of-sight displacement",
    )
    # GOFF range and azimuth are independent measurement families. Keep their
    # labels and component identity; never combine these values with GUNW LOS.
    measurements.extend(_component_records(
        goff, family="GOFF_OFFSET", value_field="cumulative_offset_mm",
        measurement_label="Cumulative range or along-track offset",
    ))
    measurements.sort(key=lambda row: (row["measurement_family"], row["network"], str(row["component"])))

    status = "OBSERVED_MOVEMENT_MEASUREMENTS_AVAILABLE" if measurements else "NO_QUALIFYING_DIAGNOSTIC_MOVEMENT_SERIES"
    report = {
        "schema_version": REPORT_SCHEMA,
        "status": status,
        "aoi_wkt_sha256": aoi_wkt_sha256 or gunw.get("aoi_wkt_sha256") or goff.get("aoi_wkt_sha256"),
        "measurement_count": len(measurements),
        "epoch_count": sum(len(row["series"]) for row in measurements),
        "measurements": measurements,
        "source_reports": {
            "GUNW": {
                "status": gunw.get("status", "NOT_REPORTED"),
                "report": "common-reference-timeseries.json",
            },
            "GOFF": {
                "status": goff.get("status", "NOT_REPORTED"),
                "report": "goff-common-reference-timeseries.json",
            },
        },
        "requirements": [
            "Only source components already marked DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED are summarized.",
            "Each component must contain at least three strictly increasing actual acquisition epochs.",
            "No temporal interpolation, cross-track mixing, or conversion to 3-D motion is performed.",
        ],
        "warnings": [
            "The common reference is derived from AOI pixels and is not independently validated stable ground.",
            "Net change and endpoint rate are diagnostic relative measurements; they are not absolute displacement or hazard predictions.",
            "GUNW LOS, GOFF range, and GOFF along-track values remain separate and must not be combined without independently validated geometry.",
            "Graph-fit errors omit systematic reference, atmosphere, orbital ramp, and correlated measurement uncertainty.",
        ],
    }
    _write_outputs(output_root, report)
    return report


__all__ = ["build_observed_movement_report"]
