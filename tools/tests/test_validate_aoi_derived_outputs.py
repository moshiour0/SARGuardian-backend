from __future__ import annotations

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validate_aoi_derived_outputs import canonical_granule_name, validate


def test_canonical_granule_name_accepts_reader_filename_with_h5_suffix():
    base = (
        "NISAR_L2_PR_GUNW_022_098_A_016_023_4000_SH_"
        "20260608T233922_20260608T233956_20260620T233921_"
        "20260620T233956_X05026_N_F_J_001"
    )

    assert canonical_granule_name(base) == base
    assert canonical_granule_name(base + ".h5") == base
    assert canonical_granule_name("/tmp/source/" + base + ".h5") == base
    assert canonical_granule_name(base + ".H5") == base


def test_canonical_granule_name_does_not_match_different_product():
    assert canonical_granule_name("NISAR_L2_PR_GUNW_PRODUCT_A.h5") != canonical_granule_name(
        "NISAR_L2_PR_GUNW_PRODUCT_B"
    )


def test_validator_matches_reader_csv_when_only_h5_suffix_differs(tmp_path):
    granule = "NISAR_L2_PR_GUNW_PRODUCT_SUFFIX_REGRESSION"
    stats_csv = tmp_path / "stats.csv"
    with stats_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "layer"])
        writer.writeheader()
        writer.writerow({"file": granule + ".h5", "layer": "frequencyA"})

    report = validate(SimpleNamespace(
        stats_csv=stats_csv,
        granule_name=granule,
        product_type="GUNW",
        export_dir=tmp_path / "empty_exports",
        product_id="GUNW-TEST",
        aoi_name="custom",
    ))

    assert report["product_rows"] == 1
    assert "EXPECTED_ONE_READER_ROW_FOR_PRODUCT" not in {
        error["problem"] for error in report["errors"]
    }


def _write_goff_screen_export(path: Path, *, robust: int = 7, rejected: int = 2):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    band1 = np.arange(9, dtype="float32").reshape(3, 3) + 100.0
    band2 = band1 * 0.5
    band3 = np.full((3, 3), 0.9, dtype="float32")
    flag = np.array([[1, 1, 1], [1, 1, 0], [1, 0, 1]], dtype="float32")
    with rasterio.open(
        path, "w", driver="GTiff", width=3, height=3, count=4,
        dtype="float32", crs="EPSG:32645",
        transform=from_origin(500000, 3200240, 80, 80), nodata=np.nan,
    ) as dst:
        for index, values in enumerate((band1, band2, band3, flag), 1):
            dst.write(values, index)
        dst.set_band_description(1, "slant-range offset (mm)")
        dst.set_band_description(2, "along-track offset (mm)")
        dst.set_band_description(3, "correlation")
        dst.set_band_description(4, "robust inlier flag (1=inlier, 0=global-MAD outlier retained for review)")
        dst.update_tags(
            outliers_preserved_for_screening="true",
            screen_valid_pixels="9",
            robust_inlier_pixels=str(robust),
            robust_outlier_pixels=str(rejected),
        )


def test_validator_reconciles_screen_inliers_and_outliers(tmp_path):
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    granule = "NISAR_L2_PR_GOFF_001_098_A_016_023_4000_SH_20260101"
    _write_goff_screen_export(export_dir / "GOFF_20260101_20260113_PR_HH-layer2.tif")
    stats_csv = tmp_path / "stats.csv"
    with stats_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "layer"])
        writer.writeheader()
        writer.writerow({"file": granule + ".h5", "layer": "HH/layer2"})

    report = validate(SimpleNamespace(
        stats_csv=stats_csv, granule_name=granule, product_type="GOFF",
        export_dir=export_dir, product_id="GOFF-TEST", aoi_name="custom",
    ))
    assert report["status"] == "PASS"
    row = report["exports"][0]
    assert row["screen_valid_pixels"] == 9
    assert row["robust_inlier_pixels"] == 7
    assert row["screen_outlier_pixels"] == 2
    assert row["outlier_flag_inlier_pixels"] == 7
    assert row["outlier_flag_rejected_pixels"] == 2


def test_validator_fails_if_goff_outlier_flag_counts_do_not_reconcile(tmp_path):
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    granule = "NISAR_L2_PR_GOFF_001_098_A_016_023_4000_SH_20260101"
    _write_goff_screen_export(export_dir / "GOFF_20260101_20260113_PR_HH-layer2.tif", robust=6, rejected=3)
    stats_csv = tmp_path / "stats.csv"
    with stats_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "layer"])
        writer.writeheader()
        writer.writerow({"file": granule + ".h5", "layer": "HH/layer2"})

    report = validate(SimpleNamespace(
        stats_csv=stats_csv, granule_name=granule, product_type="GOFF",
        export_dir=export_dir, product_id="GOFF-TEST", aoi_name="custom",
    ))
    assert report["status"] == "FAIL"
    assert "GOFF_ROBUST_INLIER_TAG_MISMATCH" in {
        error["problem"] for error in report["errors"]
    }
