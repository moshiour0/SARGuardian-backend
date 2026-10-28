from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from dashboard.aoi_displacement_candidates import build_aoi_spatial_candidate_report


def _write_product(
    root: Path, product_id: str, family: str, reference: str, secondary: str, seed: int,
    *, subswath: str = "023", crid: str = "X05026", product_flag: str = "N",
    hotspot_box: tuple[int, int, int, int] = (28, 40, 32, 44),
) -> dict:
    granule = (
        f"NISAR_L2_PR_{family}_022_098_A_016_{subswath}_4000_SH_"
        f"{reference.replace('-', '')}T000000_{reference.replace('-', '')}T000030_"
        f"{secondary.replace('-', '')}T000000_{secondary.replace('-', '')}T000030_"
        f"{crid}_{product_flag}_F_J_001"
    )
    folder = root / "product-data" / product_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (f"{family}_{reference.replace('-', '')}_{secondary.replace('-', '')}.tif")
    rng = np.random.default_rng(seed)
    first = rng.normal(0, 1.25, size=(80, 80)).astype("float32")
    row_start, row_end, col_start, col_end = hotspot_box
    first[row_start:row_end, col_start:col_end] += 18.0
    transform = from_origin(500000, 3000000, 80, 80)
    if family == "GUNW":
        data = np.stack([first, np.ones_like(first)])
        descriptions = ("LOS displacement (mm)", "coherence")
        band_tags = {}
        tags = {
            "aoi_name": "custom", "aoi_mask_applied": "true",
            "grid_policy": "common_aoi_lattice", "export_status": "WRITTEN",
            "source": granule + ".h5",
        }
    else:
        second = rng.normal(0, 1.25, size=(80, 80)).astype("float32")
        second[row_start:row_end, col_start:col_end] += 14.0
        correlation = np.ones_like(first, dtype="float32")
        data = np.stack([first, second, correlation])
        descriptions = ("slant-range offset (mm)", "along-track offset (mm)", "correlation")
        tags = {
            "aoi_name": "custom", "aoi_mask_applied": "true",
            "grid_policy": "common_aoi_lattice", "export_status": "WRITTEN",
            "layer": "HH/layer2", "correlation_min": "0.3",
            "source": granule + ".h5",
        }
    with rasterio.open(
        path, "w", driver="GTiff", height=80, width=80, count=data.shape[0],
        dtype="float32", crs="EPSG:32645", transform=transform, nodata=-9999.0,
    ) as dataset:
        dataset.write(data)
        dataset.descriptions = descriptions
        dataset.update_tags(**tags)
    return {
        "id": product_id, "product_type": family, "granule_name": granule,
        "reference_date": reference, "secondary_date": secondary,
        "exports": [{"name": path.name, "relative_path": path.relative_to(root).as_posix()}],
    }


class AOISpatialCandidateTests(unittest.TestCase):
    def test_target_free_single_pair_screen_reports_unconfirmed_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            product = _write_product(root, "GUNW-001", "GUNW", "2026-06-08", "2026-06-20", 7)
            report = build_aoi_spatial_candidate_report([product], root, "a" * 64)

            self.assertFalse(report["target_required"])
            self.assertEqual(report["products_examined"], 1)
            self.assertGreaterEqual(report["candidate_features"], 1)
            self.assertEqual(report["status"], "SINGLE_PAIR_CANDIDATES_NEED_TEMPORAL_CONFIRMATION")
            self.assertFalse(report["movement_confirmed"])
            self.assertFalse(report["hazard_detected"])
            feature = report["features"][0]
            self.assertEqual(feature["properties"]["status"], "SINGLE_PAIR_CANDIDATE_UNCONFIRMED")
            self.assertEqual(feature["properties"]["support_pairs"], 1)
            saved = json.loads((root / "aoi-displacement-candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["candidate_features"], report["candidate_features"])
            geojson = json.loads((root / "aoi-displacement-candidates.geojson").read_text(encoding="utf-8"))
            self.assertEqual(len(geojson["features"]), report["candidate_features"])

    def test_same_candidate_in_two_compatible_pairs_gets_repeated_support_not_hazard_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = _write_product(root, "GUNW-001", "GUNW", "2026-06-08", "2026-06-20", 7)
            # A different sub-swath on the same exact projected AOI lattice is
            # eligible as another spatial support source; its interval still gets
            # only one vote per pixel. The F/F processing suffix is valid too.
            second = _write_product(
                root, "GUNW-002", "GUNW", "2026-06-20", "2026-07-02", 19,
                subswath="024", crid="X05026", product_flag="F",
            )
            report = build_aoi_spatial_candidate_report([first, second], root, "b" * 64)

            # A one-pair region must not inherit a recurrence label merely because
            # it touches a small repeated patch. The actual same-pixel support is
            # the criterion, not the maximum support anywhere in a polygon.
            for feature in report["features"]:
                props = feature["properties"]
                if props["status"] == "SINGLE_PAIR_CANDIDATE_UNCONFIRMED":
                    self.assertLess(props["support_pairs"], 2)

            repeated = [f for f in report["features"] if f["properties"]["status"] == "REPEATED_SPATIAL_CANDIDATE"]
            self.assertTrue(repeated)
            self.assertGreaterEqual(repeated[0]["properties"]["support_pairs"], 2)
            self.assertGreaterEqual(repeated[0]["properties"]["max_pixel_pair_support"], 2)
            self.assertIn("subswaths 023,024", repeated[0]["properties"]["network"])
            self.assertIn("REPEATED_SPATIAL_CANDIDATES", report["status"])
            self.assertFalse(report["movement_confirmed"])
            self.assertFalse(report["hazard_detected"])

    def test_small_recurrent_patch_is_not_mislabelled_as_single_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = _write_product(root, "GUNW-001", "GUNW", "2026-06-08", "2026-06-20", 11)
            second = _write_product(
                root, "GUNW-002", "GUNW", "2026-06-20", "2026-07-02", 22,
                subswath="024", hotspot_box=(30, 32, 34, 36),
            )
            report = build_aoi_spatial_candidate_report(
                [first, second], root, "d" * 64, minimum_component_pixels=5,
            )
            self.assertFalse(report["movement_confirmed"])
            self.assertFalse(report["hazard_detected"])
            for feature in report["features"]:
                props = feature["properties"]
                if props["status"] == "SINGLE_PAIR_CANDIDATE_UNCONFIRMED":
                    self.assertEqual(props["support_pairs"], 1)

    def test_goff_offsets_are_explicitly_classified_as_non_movement_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            product = _write_product(root, "GOFF-001", "GOFF", "2026-06-08", "2026-06-20", 31)
            report = build_aoi_spatial_candidate_report([product], root, "e" * 64)
            self.assertTrue(report["features"])
            for feature in report["features"]:
                props = feature["properties"]
                self.assertEqual(props["evidence_class"], "GOFF_OFFSET_ANOMALY_NOT_GROUND_MOTION")
                self.assertIn("not ground displacement", props["interpretation"].lower())
            self.assertFalse(report["movement_confirmed"])
            self.assertFalse(report["hazard_detected"])

    def test_bad_export_contract_is_withheld_instead_of_inventing_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            product = _write_product(root, "GUNW-001", "GUNW", "2026-06-08", "2026-06-20", 7)
            raster_path = root / product["exports"][0]["relative_path"]
            with rasterio.open(raster_path, "r+") as dataset:
                dataset.update_tags(aoi_mask_applied="false")
            report = build_aoi_spatial_candidate_report([product], root, "c" * 64)

            self.assertEqual(report["status"], "NO_ELIGIBLE_RASTER_EXPORTS")
            self.assertEqual(report["candidate_features"], 0)
            self.assertFalse(report["movement_confirmed"])
            self.assertTrue(any(r["status"] == "REJECTED_RASTER_CONTRACT" for r in report["rejected_products"]))


if __name__ == "__main__":
    unittest.main()
