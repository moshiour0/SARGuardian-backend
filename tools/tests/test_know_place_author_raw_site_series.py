from __future__ import annotations

from types import SimpleNamespace
import json
from pathlib import Path

import numpy as np
import pytest
from pyproj import Transformer

from tools.know_place.author_raw_site_series import (
    AUTHOR_CROWN_BOUNDS,
    AUTHOR_WIDE_BOUNDS,
    _assert_author_bounds,
    compare_pair_to_archive,
    process_author_pair_arrays,
)
from tools.know_place.author_parity import AuthorParityError


def _wkt(bounds):
    west, south, east, north = bounds
    return (
        f"POLYGON (({west} {south}, {east} {south}, {east} {north}, "
        f"{west} {north}, {west} {south}))"
    )


def _synthetic_pair():
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True)
    corners = [
        transformer.transform(AUTHOR_WIDE_BOUNDS[0], AUTHOR_WIDE_BOUNDS[1]),
        transformer.transform(AUTHOR_WIDE_BOUNDS[0], AUTHOR_WIDE_BOUNDS[3]),
        transformer.transform(AUTHOR_WIDE_BOUNDS[2], AUTHOR_WIDE_BOUNDS[1]),
        transformer.transform(AUTHOR_WIDE_BOUNDS[2], AUTHOR_WIDE_BOUNDS[3]),
    ]
    xmin = min(point[0] for point in corners)
    xmax = max(point[0] for point in corners)
    ymin = min(point[1] for point in corners)
    ymax = max(point[1] for point in corners)

    # North-up row order (descending Y), analogous to the GOFF grid.
    x = np.linspace(xmin, xmax, 91)
    y = np.linspace(ymax, ymin, 81)
    xx, yy = np.meshgrid(x, y)
    at = (
        0.35
        + 0.45 * np.sin((xx - xmin) / 410.0)
        + 0.20 * np.cos((yy - ymin) / 370.0)
    )
    sr = 0.08 * np.sin((xx + yy) / 900.0)
    snr = np.full(at.shape, 12.0)

    gx = np.linspace(xmin - 1000.0, xmax + 1000.0, 31)
    gy = np.linspace(ymin - 1000.0, ymax + 1000.0, 29)  # increasing axes
    heights = np.array([4500.0, 5000.0, 5500.0])
    shape = (heights.size, gy.size, gx.size)
    incidence = np.empty(shape, dtype=float)
    incidence[0] = 34.0
    incidence[1] = 35.0
    incidence[2] = 36.0
    cubes = SimpleNamespace(
        metadata_epsg=32645,
        group_path="mock/radarGrid",
        x_m=gx,
        y_m=gy,
        height_m=heights,
        incidence_deg=incidence,
        los_x=np.full(shape, 0.6),
        los_y=np.full(shape, 0.8),
        along_track_x=np.full(shape, 0.4),
        along_track_y=np.full(shape, 0.9),
        unit_evidence={"incidence": "degrees", "vectors": "unitless"},
    )
    return at, sr, snr, x, y, cubes


def test_author_profile_rejects_changed_crown_or_reference_bounds():
    config = {
        "crown_wkt": _wkt(AUTHOR_CROWN_BOUNDS),
        "reference_box_wkt": _wkt(AUTHOR_WIDE_BOUNDS),
    }
    _assert_author_bounds(config)

    config["crown_wkt"] = _wkt((85.5240, 28.2847, 85.5400, 28.2970))
    with pytest.raises(ValueError, match="AUTHOR_PROFILE_CROWN_BOUNDS_MISMATCH"):
        _assert_author_bounds(config)


def test_raw_pair_uses_author_geometry_gate_reference_and_null_policy():
    at, sr, snr, x, y, cubes = _synthetic_pair()
    result = process_author_pair_arrays(
        along_track_m=at,
        slant_range_m=sr,
        snr=snr,
        x_coordinates_m=x,
        y_coordinates_m=y,
        epsg=32645,
        geometry_cubes=cubes,
        interval_days=24,
        polygon_null_rng=np.random.default_rng(20260907),
    )

    assert result["geometry"]["incidence_deg"] == pytest.approx(35.0)
    assert result["geometry"]["sample_policy"] == (
        "nearest radarGrid XY cell; nanmedian over height-axis samples"
    )
    assert result["quality"]["correlation_field_is_not_used_by_author_quality_gate"] is True
    assert result["quality"]["author_valid_cells_after_snr_and_magnitude_gates"] > 0
    assert result["reference_correction"]["ring_valid_cells"] > 200
    assert result["reference_correction"]["correction_applied"] is True

    arrays = result["arrays"]
    shape = at.shape
    for name in (
        "east_m", "north_m", "horizontal_magnitude_m",
        "directional_coherence_R", "valid_mask", "inside_aoi_mask", "crown_mask",
    ):
        assert arrays[name].shape == shape
    assert result["site_series"]["displacement_valid_crown_cells"] > 0
    assert 0.0 <= result["site_series"]["P1_R_crown"] <= 1.0
    assert result["polygon_null"]["candidate_centres_examined"] <= 1200
    assert result["polygon_null"]["accepted_draws"] > 0


def test_five_pair_archive_comparison_covers_thirteen_same_estimand_checks():
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "docs" / "know-place" / "reference" / "author_benchmark_v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    expected = fixture["published_site_series"]
    for index in range(5):
        site = {
            "displacement_valid_crown_cells": expected["displacement_valid_crown_pixels"][index],
            "crown_median_displacement_m": expected["median_crown_displacement_m"][index],
            "crown_median_rate_cm_per_day": expected["median_crown_rate_cm_per_day"][index],
            "P1_R_crown": expected["bulk_reference_crown_R"][index],
            "P1_R_background": expected["bulk_reference_background_R"][index],
        }
        null = {
            "crown_valid_R_cells": expected["polygon_null_R_valid_crown_pixels"][index],
            "crown_R": expected["single_field_crown_R"][index],
            "box_R": expected["bulk_reference_background_R"][index],
            "crown_percentile_strict_less_than": expected["polygon_null_R_percentile"][index],
            "fraction_controls_strictly_above_box": expected["polygon_null_samples_beating_box_mean_percent"][index],
            "null_p5": expected["polygon_null_R_5th_percentile"][index],
            "null_p95": expected["polygon_null_R_95th_percentile"][index],
            "accepted_draws": expected["polygon_null_accepted_draws"][index],
        }
        comparison = compare_pair_to_archive(site, null, index, fixture)
        assert comparison["status"] == "PASS_AT_ARCHIVE_ROUNDING"
        assert comparison["checks_passed"] == comparison["checks_total"] == 13


def test_archive_comparison_flags_a_real_mismatch():
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "docs" / "know-place" / "reference" / "author_benchmark_v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    expected = fixture["published_site_series"]
    site = {
        "displacement_valid_crown_cells": expected["displacement_valid_crown_pixels"][0],
        "crown_median_displacement_m": expected["median_crown_displacement_m"][0] + 0.02,
        "crown_median_rate_cm_per_day": expected["median_crown_rate_cm_per_day"][0],
        "P1_R_crown": expected["bulk_reference_crown_R"][0],
        "P1_R_background": expected["bulk_reference_background_R"][0],
    }
    null = {
        "crown_valid_R_cells": expected["polygon_null_R_valid_crown_pixels"][0],
        "crown_R": expected["single_field_crown_R"][0],
        "box_R": expected["bulk_reference_background_R"][0],
        "crown_percentile_strict_less_than": expected["polygon_null_R_percentile"][0],
        "fraction_controls_strictly_above_box": expected["polygon_null_samples_beating_box_mean_percent"][0],
        "null_p5": expected["polygon_null_R_5th_percentile"][0],
        "null_p95": expected["polygon_null_R_95th_percentile"][0],
        "accepted_draws": expected["polygon_null_accepted_draws"][0],
    }
    comparison = compare_pair_to_archive(site, null, 0, fixture)
    assert comparison["status"] == "MISMATCH"
    assert comparison["checks_passed"] == 12
    assert comparison["checks_total"] == 13
