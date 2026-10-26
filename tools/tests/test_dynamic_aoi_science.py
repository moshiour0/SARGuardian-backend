from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from tools.run_dynamic_aoi_science import point_in_ring, parse_wkt_ring, run_engine


ROOT_WKT = "POLYGON ((85.45 28.35, 85.45 28.25, 85.55 28.25, 85.55 28.35, 85.45 28.35))"


def _granule(ref: str, sec: str) -> str:
    return (
        "NISAR_L2_PR_GUNW_001_048_D_074_026_2000_SH_"
        f"{ref}T120000_{ref}T120030_{sec}T120000_{sec}T120030_P05023_N_F_J_001"
    )


def _build_fixture(root: Path, science_root: Path, target: bool = False) -> None:
    target_x, target_y = Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True).transform(85.5, 28.3)
    size = 64 if target else 16
    transform = from_origin(target_x - (size // 2) * 80, target_y + (size // 2) * 80, 80, 80)
    records = []
    pairs = [
        ("20260101", "20260113", 8.0),
        ("20260113", "20260125", 14.0),
    ]
    yy, xx = np.mgrid[:size, :size]
    base = 0.4 * np.sin(xx / 3.0) + 0.25 * np.cos(yy / 4.0)
    target_blob = np.exp(-((xx - size // 2) ** 2 + (yy - size // 2) ** 2) / 30.0)
    (root / "product-data").mkdir(parents=True)
    for idx, (ref, sec, scale) in enumerate(pairs, start=1):
        granule = _granule(ref, sec)
        pid = f"GUNW-{idx:03d}"
        rel = f"product-data/{pid}/GUNW_{ref}_{sec}_PR.tif"
        out = root / rel
        out.parent.mkdir(parents=True)
        data = (base + scale * target_blob).astype("float32")
        coherence = np.full((size, size), 0.85, dtype="float32")
        with rasterio.open(
            out, "w", driver="GTiff", height=size, width=size, count=2,
            dtype="float32", crs="EPSG:32645", transform=transform, nodata=np.nan,
        ) as ds:
            ds.write(data, 1)
            ds.write(coherence, 2)
            ds.set_band_description(1, "LOS displacement (mm)")
            ds.set_band_description(2, "coherence")
            ds.update_tags(
                aoi_mask_applied="true", aoi_name="custom", source=granule + ".h5",
                coherence_min="0.3", valid_pixel_count=str(size * size),
                reference=ref, secondary=sec, crid="P05023",
            )
        rec = {
            "id": pid, "product_type": "GUNW", "granule_name": granule,
            "reference_date": date(int(ref[:4]), int(ref[4:6]), int(ref[6:] )).isoformat(),
            "secondary_date": date(int(sec[:4]), int(sec[4:6]), int(sec[6:] )).isoformat(),
            "status": "PASS", "valid_pixels": size * size,
            "source_sha256": hashlib.sha256((granule + "-source").encode()).hexdigest(),
            "exports": [{"relative_path": rel, "name": Path(rel).name}],
            "stats": {"track": "DESC 048", "mean_coherence": 0.85},
        }
        rec_path = root / "product-data" / pid / "product-record.json"
        rec_path.write_text(json.dumps(rec), encoding="utf-8")
        records.append(rec)
    rev = subprocess.run(
        ["git", "-C", str(science_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    summary = {
        "schema_version": "sarguardian-aoi-dashboard-summary/1.0",
        "run_id": "science-engine-fixture",
        "science_commit": rev,
        "aoi_name": "custom",
        "aoi_wkt": ROOT_WKT,
        "aoi_wkt_sha256": hashlib.sha256(ROOT_WKT.encode()).hexdigest(),
        "products_expected": len(records),
        "products_validated": len(records),
        "analysis_target": {"latitude": 28.3, "longitude": 85.5} if target else None,
        "science_diagnostics": {"pixel_stack": {"status": "COMPLETED_NO_DETECTION"}},
    }
    (root / "aoi-run-summary.json").write_text(json.dumps(summary), encoding="utf-8")


def test_ring_membership_is_wgs84_lon_lat_and_rejects_outside_point() -> None:
    ring = parse_wkt_ring(ROOT_WKT)
    assert point_in_ring(85.5, 28.3, ring)
    assert not point_in_ring(86.0, 28.3, ring)


def test_dynamic_engine_uses_pinned_inversion_and_keeps_exactly_determined_warning(tmp_path: Path) -> None:
    science_root = Path(__file__).resolve().parents[2] / "science-source"
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    _build_fixture(fixture, science_root, target=False)

    report = run_engine(fixture, science_root)

    assert report["status"] == "PASS_WITH_LIMITATIONS"
    assert report["stages"]["timeseries"]["status"] == "COMPUTED_DIAGNOSTIC_ONLY"
    assert report["network_components"][0]["n_pairs"] == 2
    assert report["network_components"][0]["n_epochs"] == 3
    assert report["network_components"][0]["redundancy_dof"] == 0
    assert report["network_components"][0]["status"] == "EXACTLY_DETERMINED_NO_ERROR_ESTIMATE"
    assert report["stages"]["inverse_velocity"]["status"] == "SKIPPED_NO_VALIDATED_TARGET_COORDINATES"
    assert report["stages"]["bound"]["status"] == "SKIPPED_NOT_A_GENERIC_AOI_BOUND"
    assert (fixture / "science-engine" / "timeseries-network.csv").is_file()
    assert (fixture / "science-engine" / "timeseries-pixel-series.csv").is_file()


def test_optional_target_runs_local_floor_but_does_not_fabricate_geometry_or_forecast(tmp_path: Path) -> None:
    science_root = Path(__file__).resolve().parents[2] / "science-source"
    fixture = tmp_path / "target-fixture"
    fixture.mkdir()
    _build_fixture(fixture, science_root, target=True)

    report = run_engine(fixture, science_root)

    assert report["analysis_target"]["inside_aoi"] is True
    assert report["stages"]["local_floor"]["status"] == "TARGET_LOCAL_FLOOR_COMPUTED"
    assert len(report["target_series"]) == 1
    assert report["target_series"][0]["redundancy_dof"] == 0
    assert report["stages"]["inverse_velocity"]["status"] == "INSUFFICIENT_TEMPORAL_REDUNDANCY"
    assert report["stages"]["geometry_merge"]["status"] == "SKIPPED_NO_PRODUCT_LOS_UNIT_VECTORS"
    with (fixture / "science-engine" / "local-floor.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows and any(row["target_local_floor_mm_day"] for row in rows)
