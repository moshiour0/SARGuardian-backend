"""AOI-specific scientific stage eligibility and network diagnostics.

This module reports which pinned SARGuardian analyses actually ran and which
must be withheld for the current dynamic-AOI contract. It deliberately does not
turn pairwise reader medians into a common-reference time series.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path
import sys
from typing import Any


def _valid_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def build_science_pipeline_report(
    products: list[dict[str, Any]],
    science_root: Path,
    science_diagnostics: dict[str, Any] | None,
    site_context: dict[str, Any] | None = None,
    common_reference_report: dict[str, Any] | None = None,
    movement_measurement_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run time-series network topology analysis and gate downstream methods.

    Network topology uses the pinned timeseries.py implementation. Numeric
    inversion is intentionally withheld because pair-wise exports do not prove
    that each acquisition pair used the same stable-ground reference datum.
    """
    report: dict[str, Any] = {
        "schema_version": "sarguardian-science-pipeline-readiness/1.0",
        "science_commit_expected": None,
        "structural_validation_is_geophysical_validation": False,
        "network_assessment_status": "NOT_STARTED",
        "networks": [],
        "modules": [],
        "warnings": [
            "This is a stage-eligibility report, not a hazard declaration.",
            "Pairwise medians from independently referenced products are not a common-datum time series.",
        ],
    }
    diagnostics = science_diagnostics if isinstance(science_diagnostics, dict) else {}
    stack = diagnostics.get("pixel_stack") if isinstance(diagnostics.get("pixel_stack"), dict) else {}
    candidate = diagnostics.get("candidate_checks") if isinstance(diagnostics.get("candidate_checks"), dict) else {}

    gunw_count = sum(str(row.get("product_type", "")).upper() == "GUNW" for row in products)
    goff_count = sum(str(row.get("product_type", "")).upper() == "GOFF" for row in products)
    report["product_counts"] = {"GUNW": gunw_count, "GOFF": goff_count, "total": len(products)}
    report["modules"].extend([
        {
            "name": "gunw_reader.py",
            "status": "EXECUTED_PER_PRODUCT" if gunw_count else "NO_GUNW_PRODUCTS",
            "products": gunw_count,
            "produces": "LOS displacement and coherence rasters/statistics",
            "limitation": "LOS displacement is relative to the product's reference; it is not direct 3-D motion.",
        },
        {
            "name": "goff_reader.py",
            "status": "EXECUTED_PER_PRODUCT" if goff_count else "NO_GOFF_PRODUCTS",
            "products": goff_count,
            "produces": "range/along-track offsets, correlation/quality metrics and pair-specific detection floors where available",
            "limitation": "Offsets require geometry-aware interpretation and are not interchangeable with GUNW phase measurements.",
        },
    ])

    src = str((Path(science_root).resolve() / "src"))
    if src not in sys.path:
        sys.path.insert(0, src)

    pairs = []
    invalid = []
    structures: dict[str, Any] = {}
    network_error = None
    try:
        import timeseries
        for row in products:
            name = str(row.get("granule_name") or "")
            meta = timeseries.granule_metadata(name)
            ref = _valid_date(row.get("reference_date"))
            sec = _valid_date(row.get("secondary_date"))
            if meta is None or ref is None or sec is None or sec <= ref:
                invalid.append({
                    "product_id": row.get("id"),
                    "granule_name": name,
                    "reason": "Granule identity or acquisition dates are not parseable by the pinned time-series engine.",
                })
                continue
            pairs.append(timeseries.Pair(
                path=meta["path"],
                direction=meta["direction"],
                ref=ref,
                sec=sec,
                value=None,
                n_px=row.get("valid_pixels"),
                coherence=(row.get("stats") or {}).get("mean_coherence"),
                source=name,
                metadata=meta,
            ))
        if pairs:
            captured = StringIO()
            with redirect_stdout(captured):
                structures = timeseries.describe_network(pairs)
            report["network_assessment_status"] = "COMPLETED"
        else:
            report["network_assessment_status"] = "NO_PARSEABLE_PAIRS"
    except Exception as exc:
        network_error = type(exc).__name__ + ":" + str(exc)[:250]
        report["network_assessment_status"] = "UNAVAILABLE"
    report["invalid_pair_rows"] = invalid
    report["site_context"] = site_context or {}
    common_reference_report = common_reference_report if isinstance(common_reference_report, dict) else {}
    movement_measurement_report = movement_measurement_report if isinstance(movement_measurement_report, dict) else {}
    report["common_reference_timeseries"] = common_reference_report
    report["observed_movement_measurements"] = movement_measurement_report
    report["movement_measurement_status"] = str(movement_measurement_report.get("status") or "NOT_REPORTED")
    report["network_assessment_log_excerpt"] = captured.getvalue()[-8000:] if "captured" in locals() else ""
    report["network_error"] = network_error

    for label, components in sorted(structures.items()):
        for index, component in enumerate(components, 1):
            epochs = component.get("epochs", [])
            pairs_n = int(component.get("n_pairs", 0))
            redundancy = int(component.get("redundancy", pairs_n - max(0, len(epochs) - 1)))
            report["networks"].append({
                "geometry": label,
                "component": index,
                "first_epoch": epochs[0] if epochs else None,
                "last_epoch": epochs[-1] if epochs else None,
                "epochs": epochs,
                "n_epochs": len(epochs),
                "n_pairs": pairs_n,
                "redundancy": redundancy,
                "formal_residual_error_estimable": redundancy > 0,
                "topology_status": "REDUNDANT" if redundancy > 0 else "EXACTLY_DETERMINED_NO_REDUNDANCY",
            })

    target_info = (site_context or {}).get("measurement_target", {})
    target_status = (target_info.get("status") or "NOT_PROVIDED") if isinstance(target_info, dict) else "NOT_PROVIDED"
    measured_targets = sum(
        isinstance(row.get("target_measurement"), dict)
        and row["target_measurement"].get("status") == "MEASURED"
        for row in products
    )
    measured_floors = sum(
        isinstance(row.get("local_floor"), dict)
        and row["local_floor"].get("status") == "MEASURED"
        for row in products
    )
    if target_status == "IN_AOI_TARGET_CAPTURED":
        local_floor_status = "PAIRWISE_LOCAL_FLOOR_MEASURED" if measured_floors else "TARGET_CAPTURED_FLOOR_UNAVAILABLE"
        local_floor_reason = (
            f"An in-AOI point was supplied. {measured_targets} product(s) have target-window measurements and "
            f"{measured_floors} have a measured radius-6 local noise floor. These are pair-specific values in each reader's "
            "reference frame; they do not provide a shared stable-ground datum or authorize cumulative inversion."
        )
    elif target_status == "NOT_PROVIDED":
        local_floor_status = "BLOCKED_NO_EXPLICIT_MEASUREMENT_TARGET"
        local_floor_reason = "No in-AOI target coordinate was provided. No target-local measurement or floor is inferred."
    else:
        local_floor_status = "BLOCKED_INVALID_OR_OUTSIDE_TARGET"
        local_floor_reason = f"Target context was rejected or incomplete ({target_status}); no target-specific inference is allowed."

    has_diagnostic_series = common_reference_report.get("status") == "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED"
    has_common_datum = common_reference_report.get("status") in {
        "COMMON_DATUM_PAIRWISE_ONLY", "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED",
    }
    if has_diagnostic_series:
        timeseries_status = "DIAGNOSTIC_CUMULATIVE_LOS_SERIES_COMPUTED_REFERENCE_UNVALIDATED"
        timeseries_reason = (
            "A common-grid, common-pixel GUNW stack was re-referenced and at least one connected, redundant component passed the pinned graph solver and leave-one-out velocity-sign check. "
            "This is still diagnostic only: its zero is the median of common-valid AOI pixels outside the target buffer, not an independently surveyed stable-ground reference."
        )
    elif has_common_datum:
        timeseries_status = "COMMON_DATUM_PAIRWISE_ONLY_NO_PUBLISHABLE_CUMULATIVE_SERIES"
        timeseries_reason = str(common_reference_report.get("reason") or "Common datum was computed but no component met cumulative-series publication gates.")
    else:
        timeseries_status = "NETWORK_TOPOLOGY_ONLY_INVERSION_WITHHELD" if pairs else report["network_assessment_status"]
        timeseries_reason = (
            "The pinned engine assessed pair/epoch connectivity, but the retained rasters did not satisfy the common-grid, >=200 common-reference-pixel, target-support and/or robust redundant-network gate. No cumulative values were inferred."
            if pairs else "Pair topology could not be assessed from the supplied product identities and acquisition dates."
        )
    common_status = str(common_reference_report.get("status") or "NOT_REPORTED")
    report["modules"].extend([
        {
            "name": "common_ref.py",
            "status": common_status,
            "reason": str(common_reference_report.get("reason") or "See common-reference-timeseries.json for per-network grid, mask, target-support and common-pixel checks."),
            "stable_ground_independently_validated": False,
            "interpretation": "The pinned common-datum calculation uses the all-pair valid AOI median outside the target buffer. It does not independently establish geological stability.",
        },
        {
            "name": "timeseries.py",
            "status": timeseries_status,
            "pairs_parsed": len(pairs),
            "networks": len(structures),
            "reason": timeseries_reason,
            "minimum_next_evidence": "For an independently validated movement series, supply/validate a stable-ground reference or external stable-area evidence and verify the AOI-derived datum sensitivity; do not use a diagnostic line as a hazard alert.",
        },
        {
            "name": "local_floor.py",
            "status": local_floor_status,
            "reason": local_floor_reason,
            "products_with_measured_local_floor": measured_floors,
            "products_with_target_window_measurement": measured_targets,
            "available_related_metrics": "A local floor is a pair-specific detectability/noise estimate, not observed motion or a common-reference time series.",
        },
        {
            "name": "inverse_velocity.py",
            "status": "BLOCKED_NO_VERIFIED_COMMON_DATUM_SERIES",
            "reason": "Inverse velocity requires a defensible displacement series and matched noise floors. Running it on independently referenced pair medians would manufacture a trend.",
        },
        {
            "name": "geometry_merge.py",
            "status": "BLOCKED_NO_COMPARABLE_ASC_DESC_SERIES",
            "reason": "The current custom-AOI artifact does not establish matched, common-datum ascending/descending time series with sufficient overlap. Geometry sensitivity alone is not measured 3-D fusion.",
        },
        {
            "name": "bound.py",
            "status": "NOT_APPLICABLE_GENERIC_AOI",
            "reason": "This module contains fixed source-event/candidate priors and cannot be applied to an arbitrary place without a separately validated event-specific configuration.",
        },
        {
            "name": "observed_movement_measurements.py",
            "status": str(movement_measurement_report.get("status") or "NOT_REPORTED"),
            "measurements": int(movement_measurement_report.get("measurement_count") or 0),
            "reason": (
                "Summarizes only graph-inverted GUNW LOS and GOFF range/along-track components that passed their existing common-grid, support, network-redundancy and jackknife gates. "
                "It reports net change and endpoint rate over actual observed epochs; the AOI-derived datum is not independently validated."
                if movement_measurement_report.get("status") == "OBSERVED_MOVEMENT_MEASUREMENTS_AVAILABLE"
                else "No cumulative movement series met the pinned scientific gates; pairwise medians are not promoted into a synthetic time series."
            ),
            "independent_geophysical_validation": False,
            "interpretation": "Movement values are target-relative diagnostics in their own measurement families; they are not absolute or 3-D displacement, a hazard alarm, or a forecast.",
        },
        {
            "name": "pixel_stack.py",
            "status": str(stack.get("status") or "NOT_REPORTED"),
            "interpretation": str(stack.get("interpretation") or "Inspect the saved science-diagnostics.json and pixel-stack log."),
        },
        {
            "name": "candidate_check.py",
            "status": str(candidate.get("status") or "NOT_REPORTED"),
            "reason": str(candidate.get("detail") or "Inspect saved candidate diagnostics."),
        },
    ])
    movement_available = movement_measurement_report.get("status") == "OBSERVED_MOVEMENT_MEASUREMENTS_AVAILABLE"
    report["overall_status"] = (
        "REFERENCE_UNVALIDATED_DIAGNOSTIC_SERIES_COMPUTED"
        if has_diagnostic_series else (
            "REFERENCE_UNVALIDATED_DIAGNOSTIC_MOVEMENT_MEASUREMENTS_AVAILABLE"
            if movement_available else (
                "NETWORK_ASSESSED_WITH_DOWNSTREAM_STAGES_WITHHELD"
                if report["network_assessment_status"] == "COMPLETED"
                else "PARTIAL_STAGE_ASSESSMENT"
            )
        )
    )
    return report
