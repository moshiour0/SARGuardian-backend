from __future__ import annotations

import csv
import io
import math
from pathlib import Path
import zipfile

import numpy as np
import rasterio
import pytest
from affine import Affine

from tools.know_place.author_footprint_replay import (
    CANDIDATE_METRIC_COLUMNS,
    _angle_difference_degrees,
    _candidate_table,
    _compare_raster_arrays,
    compare_candidate_inventory,
)


def test_raster_comparison_requires_finite_mask_and_numeric_parity():
    expected = np.array([[0.0, np.nan], [2.0, 3.0]], dtype=np.float32)
    assert _compare_raster_arrays(expected.copy(), expected.copy(), tolerance=0.0)["status"] == "PASS"
    wrong_mask = np.array([[0.0, 1.0], [2.0, 3.0]], dtype=np.float32)
    assert _compare_raster_arrays(wrong_mask, expected, tolerance=0.0)["finite_mask_mismatch_count"] == 2
    wrong_value = expected.copy()
    wrong_value[1, 0] += 0.001
    assert _compare_raster_arrays(wrong_value, expected, tolerance=0.0001)["status"] == "FAIL"


def test_circular_angle_difference_wraps_at_zero():
    assert _angle_difference_degrees(359.0, 1.0) == 2.0
    assert _angle_difference_degrees(280.0, 280.0) == 0.0
    assert _angle_difference_degrees(90.0, 270.0) == 180.0


def _write_candidate_pair_tif(path: Path, transform: Affine, shape: tuple[int, int]) -> None:
    east = np.full(shape, math.sin(math.radians(280.0)), dtype=np.float32)
    north = np.full(shape, math.cos(math.radians(280.0)), dtype=np.float32)
    bands = [
        np.ones(shape, dtype=np.float32),
        np.full(shape, 0.6, dtype=np.float32),
        np.full(shape, 0.9, dtype=np.float32),
        np.full(shape, 5.0, dtype=np.float32),
        east,
        north,
        np.full(shape, 0.95, dtype=np.float32),
        np.full(shape, 1.2, dtype=np.float32),
    ]
    with rasterio.open(
        path, "w", driver="GTiff", height=shape[0], width=shape[1],
        count=8, dtype="float32", crs="EPSG:32645", transform=transform,
        nodata=-9999.0,
    ) as dst:
        for idx, values in enumerate(bands, 1):
            dst.write(values, idx)


def test_candidate_component_summary_uses_pixel_area_centroid_and_directional_gate(tmp_path):
    shape = (4, 4)
    transform = Affine(80.0, 0.0, 126720.0, 0.0, -80.0, 3347280.0)
    labels = np.ones(shape, dtype=np.int32)
    epochs = np.full(shape, 3, dtype=np.uint8)
    anomaly = np.full(shape, 0.6, dtype=np.float32)
    coherence = np.full(shape, 0.8, dtype=np.float32)
    terrain = {
        "elev_m.tif": np.full(shape, 5000.0, dtype=np.float32),
        "slope_deg.tif": np.full(shape, 20.0, dtype=np.float32),
        "downslope_az_deg.tif": np.full(shape, 280.0, dtype=np.float32),
    }
    range_az = 250.0
    coefficient = {
        "kE": np.full(shape, math.sin(math.radians(range_az)), dtype=np.float32),
        "kN": np.full(shape, math.cos(math.radians(range_az)), dtype=np.float32),
    }
    pair_tif = tmp_path / "pair.tif"
    _write_candidate_pair_tif(pair_tif, transform, shape)
    rows, summary = _candidate_table(
        labels, epochs, anomaly, coherence, terrain, coefficient,
        [pair_tif] * 5, transform,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["n_px"] == 16
    assert row["area_km2"] == 0.1024
    assert row["n_epochs"] == 3
    assert row["anom_m"] == 0.6
    assert row["R"] == 0.8
    assert row["disp_az"] == pytest.approx(280.0, abs=1e-4)
    assert row["d_downslope"] == pytest.approx(0.0, abs=1e-4)
    assert row["d_range"] == pytest.approx(30.0, abs=1e-4)
    assert row["valid_directional"] is True
    assert summary["directional_pass_count"] == 1


def _expected_inventory_csv(rows: list[dict[str, object]]) -> str:
    stream = io.StringIO()
    columns = ["lon", "lat", *CANDIDATE_METRIC_COLUMNS]
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row[column] for column in columns})
    return stream.getvalue()


def test_archived_candidate_inventory_comparison_checks_all_101_rows(tmp_path):
    rows: list[dict[str, object]] = []
    for i in range(101):
        rows.append({
            "component_id": i + 1,
            "lon": round(80.0 + i * 0.003, 5),
            "lat": round(27.0 + i * 0.002, 5),
            "area_km2": 0.1024,
            "n_px": 16,
            "n_epochs": 3,
            "anom_m": 0.6,
            "R": 0.8,
            "score": 1.44,
            "disp_az": 280.0,
            "res_mag_m": 1.0,
            "R_raw": 0.95,
            "R_res": 0.9,
            "mag_m": 1.2,
            "elev_m": 5000.0,
            "slope_deg": 20.0,
            "downslope_az": 280.0,
            "range_az": 250.0,
            "d_downslope": 0.0,
            "d_range": 30.0,
            "valid_directional": True,
        })
    source_csv = _expected_inventory_csv(rows)
    archive_path = tmp_path / "author.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("inventory/candidates_attributed.csv", source_csv)

    result = compare_candidate_inventory(rows, archive_path, numeric_tolerance=1e-9)
    assert result["status"] == "PASS"
    assert result["expected_zone_count"] == result["computed_directional_zone_count"] == 101
    assert result["matched_centroid_count"] == 101
    assert result["mismatch_count"] == 0

    modified = [dict(row) for row in rows]
    modified[50]["R_res"] = 0.91
    mismatch = compare_candidate_inventory(modified, archive_path, numeric_tolerance=1e-9)
    assert mismatch["status"] == "MISMATCH"
    assert mismatch["mismatch_count"] == 1
