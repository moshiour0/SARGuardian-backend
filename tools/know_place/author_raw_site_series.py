"""Author-compatible five-pair site-series replay from verified raw GOFF inputs.

This is deliberately separate from analyze.py's exploratory fixed-height path.
It follows the supplied Zenodo archive's site-series conventions: crown-local
height-axis-median radar geometry, SNR/magnitude-only source mask, conditional
ring reference, north-up extent, crown-cropped coherence, and the archive's
post-hoc polygon-null statistics. It does not implement the full-footprint
screen or certify hazard-detection skill.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .analyze import _load_and_validate_inputs, load_config
from .author_parity import (
    AuthorParityError,
    author_coherence_map,
    author_crown_geometry_median,
    author_crown_slice,
    author_inside_aoi_mask,
    author_north_up,
    author_polygon_null_statistics,
    author_project_offsets,
    author_quality_mask,
    author_reference_correct,
    author_site_series_statistics,
    author_wide_window_slices,
)
from .geometry import parse_polygon_wkt
from .goff_io import GoffReadError, read_geometry_cubes, read_raw_goff
from .paper_method import PAPER_INTERVALS

AUTHOR_CROWN_BOUNDS = (85.5245, 28.2847, 85.5400, 28.2970)
AUTHOR_WIDE_BOUNDS = (85.500, 28.265, 85.565, 28.318)
AUTHOR_CROWN_POINT = (85.52985, 28.29041)
AUTHOR_EXPECTED_EPSG = 32645
AUTHOR_POSTING_M = 80.0
AUTHOR_NULL_SEED = 20260907
AUTHOR_NULL_DRAWS = 1200
PAPER_BLOCKED = "BLOCKED_AUTHOR_CROWN_GEOMETRY_AND_METHOD_PARITY_UNVERIFIED"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(value), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _bounds_from_wkt(wkt: str, label: str) -> tuple[float, float, float, float]:
    ring = parse_polygon_wkt(wkt)
    coordinates = ring[:-1]
    bounds = (
        min(point[0] for point in coordinates),
        min(point[1] for point in coordinates),
        max(point[0] for point in coordinates),
        max(point[1] for point in coordinates),
    )
    if not bounds[0] < bounds[2] or not bounds[1] < bounds[3]:
        raise GoffReadError(f"{label}_WKT_BOUNDS_INVALID")
    return bounds


def _assert_author_bounds(config: dict[str, Any]) -> None:
    """Fail closed if the run config silently changes the archived author rectangles."""
    checks = (
        ("CROWN", _bounds_from_wkt(str(config["crown_wkt"]), "CROWN"), AUTHOR_CROWN_BOUNDS),
        ("REFERENCE_BOX", _bounds_from_wkt(str(config["reference_box_wkt"]), "REFERENCE_BOX"), AUTHOR_WIDE_BOUNDS),
    )
    for label, actual, expected in checks:
        if any(abs(float(a) - float(e)) > 1e-9 for a, e in zip(actual, expected, strict=True)):
            raise GoffReadError(
                f"AUTHOR_PROFILE_{label}_BOUNDS_MISMATCH:actual={actual}:expected={expected}"
            )


def _rounding_match(actual: float | int, expected: float | int, decimals: int | None) -> bool:
    if decimals is None:
        return int(actual) == int(expected)
    return round(float(actual), decimals) == round(float(expected), decimals)


def compare_pair_to_archive(
    site: dict[str, Any],
    polygon_null: dict[str, Any],
    pair_index: int,
    benchmark: dict[str, Any],
) -> dict[str, Any]:
    """Compare explicit, same-estimand metrics at the archive's published precision."""
    expected = benchmark["published_site_series"]
    specs: list[tuple[str, float | int, float | int, int | None]] = [
        ("displacement_valid_crown_pixels", site["displacement_valid_crown_cells"],
         expected["displacement_valid_crown_pixels"][pair_index], None),
        ("median_crown_displacement_m", site["crown_median_displacement_m"],
         expected["median_crown_displacement_m"][pair_index], 2),
        ("median_crown_rate_cm_per_day", site["crown_median_rate_cm_per_day"],
         expected["median_crown_rate_cm_per_day"][pair_index], 1),
        ("bulk_reference_crown_R", site["P1_R_crown"],
         expected["bulk_reference_crown_R"][pair_index], 3),
        ("bulk_reference_background_R", site["P1_R_background"],
         expected["bulk_reference_background_R"][pair_index], 3),
        ("polygon_null_R_valid_crown_pixels", polygon_null["crown_valid_R_cells"],
         expected["polygon_null_R_valid_crown_pixels"][pair_index], None),
        ("single_field_crown_R", polygon_null["crown_R"],
         expected["single_field_crown_R"][pair_index], 3),
        ("polygon_null_box_R", polygon_null["box_R"],
         expected["bulk_reference_background_R"][pair_index], 3),
        ("polygon_null_R_percentile", polygon_null["crown_percentile_strict_less_than"],
         expected["polygon_null_R_percentile"][pair_index], 1),
        ("polygon_null_samples_beating_box_mean_percent", polygon_null["fraction_controls_strictly_above_box"],
         expected["polygon_null_samples_beating_box_mean_percent"][pair_index], 1),
        ("polygon_null_R_5th_percentile", polygon_null["null_p5"],
         expected["polygon_null_R_5th_percentile"][pair_index], 3),
        ("polygon_null_R_95th_percentile", polygon_null["null_p95"],
         expected["polygon_null_R_95th_percentile"][pair_index], 3),
        ("polygon_null_accepted_draws", polygon_null["accepted_draws"],
         expected["polygon_null_accepted_draws"][pair_index], None),
    ]
    comparisons = []
    for metric, actual, target, decimals in specs:
        comparisons.append({
            "metric": metric,
            "actual": actual,
            "archive_target": target,
            "comparison_precision_decimals": decimals,
            "passed": _rounding_match(actual, target, decimals),
        })
    return {
        "status": "PASS_AT_ARCHIVE_ROUNDING" if all(row["passed"] for row in comparisons) else "MISMATCH",
        "checks_passed": sum(bool(row["passed"]) for row in comparisons),
        "checks_total": len(comparisons),
        "comparisons": comparisons,
    }


def process_author_pair_arrays(
    *,
    along_track_m: Any,
    slant_range_m: Any,
    snr: Any,
    x_coordinates_m: Any,
    y_coordinates_m: Any,
    epsg: int,
    geometry_cubes: Any,
    interval_days: int,
    polygon_null_rng: np.random.Generator,
) -> dict[str, Any]:
    """Compute archived author site-series metrics from one raw GOFF window."""
    x = np.asarray(x_coordinates_m, dtype=float)
    y = np.asarray(y_coordinates_m, dtype=float)
    at = np.asarray(along_track_m, dtype=float)
    sr = np.asarray(slant_range_m, dtype=float)
    snr_array = np.asarray(snr, dtype=float)
    if at.ndim != 2 or sr.shape != at.shape or snr_array.shape != at.shape:
        raise GoffReadError("AUTHOR_RAW_PAIR_ARRAY_SHAPE_MISMATCH")
    if at.shape != (y.size, x.size):
        raise GoffReadError("AUTHOR_RAW_PAIR_COORDINATE_SHAPE_MISMATCH")
    if int(epsg) != AUTHOR_EXPECTED_EPSG:
        raise GoffReadError(f"AUTHOR_RAW_PAIR_EPSG_MISMATCH:{epsg}")
    geometry = author_crown_geometry_median(
        geometry_cubes, crown_lonlat=AUTHOR_CROWN_POINT, expected_epsg=AUTHOR_EXPECTED_EPSG
    )
    east, north = author_project_offsets(at, sr, geometry)
    valid = author_quality_mask(east, north, snr_array, minimum_snr=5.0, maximum_magnitude_m=10.0)
    inside = author_inside_aoi_mask(
        x, y, int(epsg), aoi_bounds_lonlat=AUTHOR_CROWN_BOUNDS
    )
    corrected_east, corrected_north, reference = author_reference_correct(
        east, north, valid, inside, minimum_ring_count_exclusive=200
    )
    extent, oriented = author_north_up(
        x, y, int(epsg), [corrected_east, corrected_north, valid, inside]
    )
    east_up, north_up = np.asarray(oriented[0], dtype=float), np.asarray(oriented[1], dtype=float)
    valid_up, inside_up = np.asarray(oriented[2], dtype=bool), np.asarray(oriented[3], dtype=bool)
    magnitude = np.hypot(east_up, north_up)
    magnitude[~(np.isfinite(east_up) & np.isfinite(north_up))] = np.nan
    coherence = author_coherence_map(east_up, north_up)
    crop = author_crown_slice(east_up.shape, extent, AUTHOR_CROWN_BOUNDS)
    crown_mask = np.zeros(east_up.shape, dtype=bool)
    crown_mask[crop] = True
    site = author_site_series_statistics(
        east_up, north_up, extent, interval_days, crown_bounds_lonlat=AUTHOR_CROWN_BOUNDS
    )
    polygon_null = author_polygon_null_statistics(
        east_up, north_up, extent, rng=polygon_null_rng,
        n_draw=AUTHOR_NULL_DRAWS, acceptance_fraction=0.60,
        crown_bounds_lonlat=AUTHOR_CROWN_BOUNDS,
    )
    return {
        "geometry": geometry,
        "quality": {
            "total_window_cells": int(valid.size),
            "author_valid_cells_after_snr_and_magnitude_gates": int(valid.sum()),
            "correlation_field_is_not_used_by_author_quality_gate": True,
            "minimum_snr": 5.0,
            "maximum_horizontal_magnitude_m": 10.0,
            "rejected_pixels_are_masked_not_clipped": True,
        },
        "reference_correction": reference,
        "extent_lonlat": list(extent),
        "site_series": site,
        "polygon_null": polygon_null,
        "arrays": {
            "east_m": east_up.astype(np.float32),
            "north_m": north_up.astype(np.float32),
            "horizontal_magnitude_m": magnitude.astype(np.float32),
            "directional_coherence_R": coherence.astype(np.float32),
            "valid_mask": valid_up.astype(np.uint8),
            "inside_aoi_mask": inside_up.astype(np.uint8),
            "crown_mask": crown_mask.astype(np.uint8),
        },
    }


def run_author_raw_site_series(config_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Read exactly five validated raw author granules and write reproducible site-series evidence."""
    config, config_dir = load_config(config_path)
    _assert_author_bounds(config)
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    products = _load_and_validate_inputs(config, config_dir)
    benchmark_path = Path(__file__).resolve().parents[2] / "docs" / "know-place" / "reference" / "author_benchmark_v1.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    rng = np.random.default_rng(AUTHOR_NULL_SEED)
    pair_reports: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []

    for pair_index, (item, interval) in enumerate(zip(products, PAPER_INTERVALS, strict=True)):
        start, end = interval
        if (item["reference_date"], item["secondary_date"]) != interval:
            raise GoffReadError("AUTHOR_PROFILE_PAIR_ORDER_MISMATCH")
        grid = item["grid"]
        row_slice, col_slice = author_wide_window_slices(
            grid.x_coordinates_m, grid.y_coordinates_m, grid.epsg,
            wide_bounds_lonlat=AUTHOR_WIDE_BOUNDS,
        )
        raw = read_raw_goff(
            item["path"], polarization="HH", layer=2,
            expected_track="098", expected_direction="A", expected_processing="PR",
            window_slices=(row_slice, col_slice), expected_grid=grid,
        )
        cubes = read_geometry_cubes(item["path"], expected_epsg=raw.epsg)
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        result = process_author_pair_arrays(
            along_track_m=raw.along_track_m,
            slant_range_m=raw.slant_range_m,
            snr=raw.snr,
            x_coordinates_m=raw.x_coordinates_m,
            y_coordinates_m=raw.y_coordinates_m,
            epsg=raw.epsg,
            geometry_cubes=cubes,
            interval_days=days,
            polygon_null_rng=rng,
        )
        comparison = compare_pair_to_archive(
            result["site_series"], result["polygon_null"], pair_index, benchmark
        )
        pair_key = f"{start.replace('-', '')}__{end.replace('-', '')}"
        array_path = out / f"{pair_key}_author_site_series_arrays.npz"
        np.savez_compressed(array_path, **result["arrays"])
        pair_report = {
            "pair": f"{start}->{end}",
            "interval_days": days,
            "granule_name": raw.identity.granule_name,
            "release_id": raw.identity.release_id,
            "source_sha256": raw.source_sha256,
            "source_bytes": int(grid.file_size_bytes),
            "source_grid": {
                "epsg": int(raw.epsg),
                "original_width": int(grid.grid_shape[1]),
                "original_height": int(grid.grid_shape[0]),
                "window_shape": list(raw.along_track_m.shape),
                "window_slices": raw.metadata["read_window"],
                "x_posting_m": float(np.median(np.diff(grid.x_coordinates_m))),
                "y_posting_m": float(np.median(np.diff(grid.y_coordinates_m))),
            },
            "geometry": {
                **result["geometry"],
                "height_policy": "nearest crown radarGrid XY cell; nan-median across the full valid height axis",
                "vertical_datum_correction_applied": False,
                "unit_evidence": cubes.unit_evidence,
            },
            "quality": result["quality"],
            "reference_correction": result["reference_correction"],
            "extent_lonlat": result["extent_lonlat"],
            "site_series": result["site_series"],
            "polygon_null": result["polygon_null"],
            "archive_table_comparison": comparison,
            "diagnostic_npz": array_path.name,
            "diagnostic_arrays_sha256": _sha256_file(array_path),
        }
        pair_reports.append(pair_report)
        csv_rows.append({
            "pair": pair_report["pair"],
            "source_sha256": pair_report["source_sha256"],
            "valid_crown_displacement_pixels": result["site_series"]["displacement_valid_crown_cells"],
            "crown_median_displacement_m": result["site_series"]["crown_median_displacement_m"],
            "crown_median_rate_cm_per_day": result["site_series"]["crown_median_rate_cm_per_day"],
            "bulk_reference_crown_R": result["site_series"]["P1_R_crown"],
            "bulk_reference_background_R": result["site_series"]["P1_R_background"],
            "polygon_null_crown_R": result["polygon_null"]["crown_R"],
            "polygon_null_crown_percentile": result["polygon_null"]["crown_percentile_strict_less_than"],
            "archive_checks_passed": comparison["checks_passed"],
            "archive_checks_total": comparison["checks_total"],
            "archive_table_comparison_status": comparison["status"],
        })
        del cubes, raw

    comparison_count = sum(row["archive_table_comparison"]["checks_total"] for row in pair_reports)
    comparison_passed = sum(row["archive_table_comparison"]["checks_passed"] for row in pair_reports)
    mismatches = [
        {"pair": row["pair"], **check}
        for row in pair_reports
        for check in row["archive_table_comparison"]["comparisons"]
        if not check["passed"]
    ]
    report = {
        "schema_version": "know-place-author-raw-site-series/1.0",
        "status": "SCIENTIFIC_METRICS_COMPUTED",
        "structural_status": "PASS" if len(pair_reports) == 5 else "FAIL",
        "method_profile": "ARCHIVED_AUTHOR_SITE_SERIES_COMPATIBLE",
        "method_source": "Zenodo 10.5281/zenodo.22730419: code/make_pot_figure.py, code/make_fig_timeseries.py, code/reconcile_scale.py, code/polygon_null.py",
        "source_products_expected": 5,
        "source_products_processed": len(pair_reports),
        "author_site_series_table_comparison": {
            "status": "PASS_AT_ARCHIVE_ROUNDING" if comparison_count == 65 and comparison_passed == 65 else "MISMATCH",
            "checks_passed": comparison_passed,
            "checks_total": comparison_count,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches,
        },
        "author_profile": {
            "wide_bounds_lonlat": list(AUTHOR_WIDE_BOUNDS),
            "crown_bounds_lonlat": list(AUTHOR_CROWN_BOUNDS),
            "crown_reference_point_lonlat": list(AUTHOR_CROWN_POINT),
            "geometry_estimator": "median of each geometry component along height at nearest radarGrid XY cell to crown reference point",
            "quality_gate": "finite projected dE/dN and SNR >= 5 and horizontal magnitude <= 10 m; correlation is not a gate",
            "bulk_reference": "component medians of valid pixels outside crown; apply only if valid outside-crown count > 200",
            "site_R": "5x5 mean resultant length with reflected edges and strict finite support > 0.5; crown R is recomputed on the crown-cropped field",
            "polygon_null": "post-hoc archive analysis; shared default_rng(20260907), 1200 candidates per pair, strict percentile inequalities and at least 60% valid target-crown cells",
            "geometry_height_m_from_exploratory_config_ignored": config.get("geometry_height_m"),
            "vertical_datum_correction_applied": False,
        },
        "paper_reproduction_status": PAPER_BLOCKED,
        "hazard_detection_status": "NOT_EVALUATED",
        "pair_reports": pair_reports,
        "limitations": [
            "A match to exported site-field summaries is not source-grid pixelwise parity.",
            "The exact author crown rectangle is bounds-defined; this profile verifies the config bounds, but does not prove pixel-for-pixel raster mask parity on the original source grid.",
            "The processed-field polygon null is an archive post-hoc analysis, not a published-paper metric.",
            "The footprint-wide candidate screen and its per-pair rasters are not computed by this site-series runner.",
            "No hazard-detection precision, recall, false-alarm rate, lead time or operational value is inferred.",
        ],
    }
    _write_json(out / "author-raw-site-series-report.json", report)
    if csv_rows:
        with (out / "author-raw-site-series.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
            writer.writeheader()
            writer.writerows(csv_rows)
    return report


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_author_raw_site_series(args.config, args.out)
    except (GoffReadError, AuthorParityError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({
            "status": "AUTHOR_SITE_SERIES_ANALYSIS_FAILED",
            "error_type": type(exc).__name__,
            "error_code": str(exc).split(":", maxsplit=1)[0][:160],
            "paper_reproduction_status": PAPER_BLOCKED,
            "hazard_detection_status": "NOT_EVALUATED",
        }, ensure_ascii=False))
        return 1
    print(f"AUTHOR_RAW_SITE_SERIES_STATUS={report['status']}")
    print(f"STRUCTURAL_STATUS={report['structural_status']}")
    print(f"ARCHIVE_TABLE_PARITY={report['author_site_series_table_comparison']['status']}")
    print(f"ARCHIVE_TABLE_COMPARISONS={report['author_site_series_table_comparison']['checks_passed']}/{report['author_site_series_table_comparison']['checks_total']}")
    print("PAPER_REPRODUCTION_STATUS=" + report["paper_reproduction_status"])
    print("HAZARD_DETECTION_STATUS=NOT_EVALUATED")
    return 0 if report["structural_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
