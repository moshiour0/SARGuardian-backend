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

    report["modules"].extend([
        {
            "name": "timeseries.py",
            "status": "NETWORK_TOPOLOGY_ONLY_INVERSION_WITHHELD" if pairs else report["network_assessment_status"],
            "pairs_parsed": len(pairs),
            "networks": len(structures),
            "reason": (
                "The pinned engine assessed pair/epoch connectivity. Numeric inversion is withheld because the dynamic exports do not persist and verify a common stable-ground reference point/datum across pairs."
                if pairs else "Pair topology could not be assessed from the supplied product identities and acquisition dates."
            ),
            "minimum_next_evidence": "Export and verify common-reference provenance for every pair, then require enough connected and redundant observations before publishing a cumulative series.",
        },
        {
            "name": "local_floor.py",
            "status": "BLOCKED_NO_EXPLICIT_MEASUREMENT_TARGET",
            "reason": "The current Dynamic request sends AOI WKT and dates but no explicit measurement target/reference point. A place-search marker is not forwarded as a validated target in the scientific job contract.",
            "available_related_metrics": "The product reader may already emit GOFF detect_floor_mm_day; this is not a successful execution of local_floor.py.",
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
    report["overall_status"] = (
        "NETWORK_ASSESSED_WITH_DOWNSTREAM_STAGES_WITHHELD"
        if report["network_assessment_status"] == "COMPLETED"
        else "PARTIAL_STAGE_ASSESSMENT"
    )
    return report
