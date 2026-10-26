from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from tools.measure_target_from_raster import measure_target


def write_fixture(path: Path, *, nodata: float = -9999.0) -> None:
    los = np.arange(49, dtype="float32").reshape(7, 7)
    coherence = np.full((7, 7), 0.75, dtype="float32")
    range_offset = np.arange(49, dtype="float32").reshape(7, 7) - 24
    azimuth = np.arange(49, dtype="float32").reshape(7, 7) * 2
    correlation = np.full((7, 7), 0.8, dtype="float32")
    with rasterio.open(path, "w", driver="GTiff", width=7, height=7, count=3,
                       dtype="float32", crs="EPSG:4326",
                       transform=from_origin(85.0, 27.007, 0.001, 0.001), nodata=nodata) as ds:
        ds.write(los if False else range_offset, 1)
        ds.write(azimuth, 2)
        ds.write(correlation, 3)
        ds.set_band_description(1, "Slant-range offset (mm)")
        ds.update_tags(reference="2026-08-01", secondary="2026-08-13", aoi_name="custom", aoi_mask_applied="true")


def test_goff_target_metric_is_local_and_not_time_series(tmp_path: Path) -> None:
    raster = tmp_path / "GOFF_20260801_20260813_layer2.tif"
    write_fixture(raster)
    result = measure_target(raster, "GOFF", longitude=85.0035, latitude=27.0035, radius_px=1)
    assert result["status"] == "MEASURED"
    assert result["measurements"]["target_local_range_median_mm"] == 0.0
    assert result["measurements"]["target_local_azimuth_median_mm"] == 24.0
    assert result["measurements"]["mean_correlation"] == 0.8
    assert "common datum" in result["interpretation"]


def test_target_outside_raster_and_insufficient_support_are_explicit(tmp_path: Path) -> None:
    raster = tmp_path / "GUNW_20260801_20260813.tif"
    write_fixture(raster)
    outside = measure_target(raster, "GUNW", longitude=87.0, latitude=29.0)
    assert outside["status"] == "TARGET_OUTSIDE_RASTER"
    few = measure_target(raster, "GUNW", longitude=85.0035, latitude=27.0035, radius_px=0, minimum_valid_pixels=3)
    assert few["status"] == "INSUFFICIENT_TARGET_SUPPORT"
    assert few["measurements"]["target_local_los_median_mm"] is None
