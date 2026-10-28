from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from dashboard.goff_common_reference import build_goff_common_reference_report


AOI_WKT = "POLYGON ((84.90 26.90, 85.12 26.90, 85.12 27.12, 84.90 27.12, 84.90 26.90))"
TARGET = {"status": "IN_AOI_TARGET_CAPTURED", "latitude": 27.01, "longitude": 85.01}


def _fake_modules():
    timeseries = ModuleType("timeseries")

    def granule_metadata(name):
        return {
            "product": "GOFF", "cycle": 26, "path": 48, "direction": "D",
            "frame": 71, "subswath": 28, "bandwidth": 4000,
            "polarisation": "SH", "crid": "P05023", "processing": "PR",
        }

    class Pair:
        def __init__(self, *, path, direction, ref, sec, value=None, n_px=None,
                     coherence=None, source="", metadata=None):
            self.path, self.direction, self.ref, self.sec = path, direction, ref, sec
            self.value, self.n_px, self.coherence, self.source = value, n_px, coherence, source
            self.metadata = metadata or {}

        @property
        def span_days(self):
            return (self.sec - self.ref).days

    def connected_components(pairs):
        return [sorted({p.ref for p in pairs} | {p.sec for p in pairs})] if pairs else []

    def invert_component(pairs, epochs):
        count = len(epochs)
        return {
            "epochs": list(epochs),
            "dof": len(pairs) - count + 1,
            "residual_rms_mm": 0.4,
            "velocity_mm_per_day": 0.08,
            "velocity_err_mm_per_day": 0.01,
            "cumulative_mm": np.arange(count, dtype=float) * 1.25,
            "error_mm": np.arange(count, dtype=float) * 0.1 + 0.1,
        }

    timeseries.granule_metadata = granule_metadata
    timeseries.Pair = Pair
    timeseries.connected_components = connected_components
    timeseries.invert_component = invert_component
    timeseries.jackknife = lambda _label, _idx, pairs, _epochs: (
        {"testable": True, "robust": True, "velocity_mm_per_day": 0.08,
         "jackknife_min": 0.06, "jackknife_max": 0.10}
        if len(pairs) >= 5 else {"testable": False, "robust": False}
    )

    aoi_wkt = ModuleType("aoi_wkt")
    aoi_wkt.parse_polygon_wkt = lambda _wkt: [
        (84.90, 26.90), (85.12, 26.90), (85.12, 27.12),
        (84.90, 27.12), (84.90, 26.90),
    ]

    gunw_reader = ModuleType("gunw_reader")
    gunw_reader.AOIS = {}
    gunw_reader.set_aoi = lambda _name: None

    common_ref = ModuleType("common_ref")
    common_ref.MIN_COMMON = 200
    common_ref.buffer_mask = lambda shape, centres, radius: _buffer_mask(shape, centres, radius)

    def rereference(stack, stable):
        if int(stable.sum()) < common_ref.MIN_COMMON:
            raise ValueError(f"only {int(stable.sum())} common stable pixels")
        constants = [float(np.median(array[stable])) for array in stack]
        return [array - constant for array, constant in zip(stack, constants)], constants

    def window_median(array, centre, radius):
        row, col = centre
        window = array[max(0, row - radius):min(array.shape[0], row + radius + 1),
                       max(0, col - radius):min(array.shape[1], col + radius + 1)]
        values = window[np.isfinite(window)]
        return (float(np.median(values)) if values.size else float("nan"), int(values.size))

    common_ref.rereference = rereference
    common_ref.window_median = window_median

    return {
        "aoi_wkt": aoi_wkt,
        "timeseries": timeseries,
        "gunw_reader": gunw_reader,
        "common_ref": common_ref,
    }


def _buffer_mask(shape, centres, radius):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    result = np.zeros(shape, dtype=bool)
    for row, col in centres:
        result |= (yy - row) ** 2 + (xx - col) ** 2 <= radius ** 2
    return result


def _write_goff(path: Path, granule: str, offset: float) -> None:
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True)
    x, y = transformer.transform(TARGET["longitude"], TARGET["latitude"])
    transform = from_origin(x - 3200, y + 3200, 100, 100)
    rr, cc = np.mgrid[0:64, 0:64]
    rng = (0.25 * rr + 0.15 * cc + offset).astype("float32")
    azi = (-0.1 * rr + 0.2 * cc - offset * 0.5).astype("float32")
    corr = np.full((64, 64), 0.8, dtype="float32")
    with rasterio.open(
        path, "w", driver="GTiff", width=64, height=64, count=3,
        dtype="float32", crs="EPSG:32645", transform=transform, nodata=np.nan,
    ) as dst:
        dst.write(rng, 1)
        dst.write(azi, 2)
        dst.write(corr, 3)
        dst.set_band_description(1, "slant-range offset (mm)")
        dst.set_band_description(2, "along-track offset (mm)")
        dst.set_band_description(3, "correlation")
        dst.update_tags(
            source=granule, aoi_name="custom", aoi_mask_applied="true",
            grid_policy="common_aoi_lattice", correlation_min="0.3",
            crid="P05023", maturity="PROVISIONAL",
        )


def _write_products(root: Path):
    intervals = [
        ("2026-08-01", "2026-08-13"),
        ("2026-08-13", "2026-08-25"),
        ("2026-08-25", "2026-09-06"),
        ("2026-08-01", "2026-08-25"),
        ("2026-08-13", "2026-09-06"),
    ]
    products = []
    for idx, (reference, secondary) in enumerate(intervals, 1):
        folder = root / "product-data" / f"GOFF-{idx:03d}"
        folder.mkdir(parents=True)
        granule = (
            "NISAR_L2_PR_GOFF_026_048_D_071_028_4000_SH_"
            f"{reference.replace('-', '')}T000000_{reference.replace('-', '')}T000000_"
            f"{secondary.replace('-', '')}T000000_{secondary.replace('-', '')}T000000_"
            "P05023_N_F_J_001.h5"
        )
        raster = folder / f"GOFF_{reference.replace('-', '')}_{secondary.replace('-', '')}_PR_layer2.tif"
        _write_goff(raster, granule, float(idx))
        products.append({
            "id": f"GOFF-{idx:03d}", "product_type": "GOFF",
            "granule_name": granule, "reference_date": reference,
            "secondary_date": secondary,
            "exports": [{
                "name": raster.name,
                "relative_path": raster.relative_to(root).as_posix(),
            }],
        })
    return products


def test_no_explicit_target_blocks_goff_reference_without_fabricated_values(tmp_path: Path) -> None:
    (tmp_path / "science" / "src").mkdir(parents=True)
    report = build_goff_common_reference_report(
        [], tmp_path, tmp_path / "science", AOI_WKT, "a" * 64,
        {"measurement_target": {"status": "NOT_PROVIDED"}},
    )
    assert report["status"] == "BLOCKED_NO_VALID_IN_AOI_TARGET"
    assert report["pairwise_measurements"] == []
    saved = json.loads((tmp_path / "goff-common-reference-timeseries.json").read_text(encoding="utf-8"))
    assert saved["status"] == report["status"]


def test_goff_range_and_azimuth_use_common_reference_and_gated_graph_inversion(tmp_path: Path) -> None:
    science_root = tmp_path / "science"
    (science_root / "src").mkdir(parents=True)
    products = _write_products(tmp_path)
    with patch.dict(sys.modules, _fake_modules()):
        report = build_goff_common_reference_report(
            products, tmp_path, science_root, AOI_WKT, "b" * 64,
            {"measurement_target": TARGET},
        )

    assert report["status"] == "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED"
    assert report["common_reference_is_independently_validated_stable_ground"] is False
    assert len(report["pairwise_measurements"]) == 10
    assert {row["component"] for row in report["pairwise_measurements"]} == {
        "range_offset", "azimuth_offset"
    }
    assert len(report["components"]) == 2
    assert all(row["status"] == "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED"
               for row in report["components"])
    assert all(len(row["series"]) == 4 for row in report["components"])
    assert (tmp_path / "goff-common-reference-pairs.csv").is_file()
    assert (tmp_path / "goff-common-reference-series.csv").is_file()


def test_goff_duplicate_intervals_are_withheld_not_silently_deduplicated(tmp_path: Path) -> None:
    science_root = tmp_path / "science"
    (science_root / "src").mkdir(parents=True)
    products = _write_products(tmp_path)
    duplicate = dict(products[0])
    duplicate["id"] = "GOFF-DUPLICATE"
    duplicate["granule_name"] = products[0]["granule_name"].replace("_P05023_", "_P05023_")
    duplicate["exports"] = [dict(products[0]["exports"][0])]
    duplicate_folder = tmp_path / "product-data" / "GOFF-DUPLICATE"
    duplicate_folder.mkdir()
    duplicate_raster = duplicate_folder / products[0]["exports"][0]["name"]
    _write_goff(duplicate_raster, duplicate["granule_name"], 99.0)
    duplicate["exports"][0]["relative_path"] = duplicate_raster.relative_to(tmp_path).as_posix()
    products.append(duplicate)

    with patch.dict(sys.modules, _fake_modules()):
        report = build_goff_common_reference_report(
            products, tmp_path, science_root, AOI_WKT, "c" * 64,
            {"measurement_target": TARGET},
        )
    networks = report["networks"]
    assert len(networks) == 1
    assert networks[0]["status"] == "WITHHELD_AMBIGUOUS_DUPLICATE_INTERVALS"
    assert report["pairwise_measurements"] == []
