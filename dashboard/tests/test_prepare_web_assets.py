from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds

from dashboard.assets.prepare_web_assets import prepare_web_dashboard


class PrepareWebAssetsTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, str]:
        (root / "product-data" / "GUNW-001").mkdir(parents=True)
        ring = [
            [90.3864, 24.7518], [90.41565, 24.77163],
            [90.4433, 24.7479], [90.4024, 24.7211],
            [90.3864, 24.7518],
        ]
        wkt = "POLYGON ((" + ", ".join(f"{x} {y}" for x, y in ring) + "))"
        bounds = transform_bounds("EPSG:4326", "EPSG:32646", 90.38, 24.715, 90.45, 24.78)
        transform = from_bounds(*bounds, 4, 4)
        tif = root / "product-data" / "GUNW-001" / "fixture.tif"
        los = np.array([[1, 2, np.nan, -3], [4, 5, 6, 7], [8, 9, 10, 11], [12, 13, 14, 15]], dtype="float32")
        coherence = np.array([[.2, .3, .4, .5], [.6, .7, .8, .9], [.3, .4, .5, .6], [.7, .8, .9, 1.0]], dtype="float32")
        with rasterio.open(
            tif, "w", driver="GTiff", width=4, height=4, count=2,
            dtype="float32", crs="EPSG:32646", transform=transform, nodata=np.nan,
        ) as ds:
            ds.write(los, 1)
            ds.write(coherence, 2)
            ds.set_band_description(1, "LOS displacement (mm)")
            ds.set_band_description(2, "coherence")
            ds.update_tags(aoi_mask_applied="true", source="synthetic test fixture")
        tif_hash = hashlib.sha256(tif.read_bytes()).hexdigest()
        product = {
            "id": "GUNW-001", "product_type": "GUNW", "granule_name": "fixture-product",
            "reference_date": "2026-07-21", "secondary_date": "2026-08-14",
            "maturity": "PROVISIONAL", "crid": "P05023", "status": "PASS",
            "valid_pixels": 15, "grid_pixels_inside_aoi": 16, "metric_name": "median", "metric_value": 6.0,
            "source_sha256": "a" * 64, "warnings": [],
            "stats": {"track": "DESC 091", "mean_coherence": 0.6},
            "exports": [{"name": "fixture.tif", "relative_path": "product-data/GUNW-001/fixture.tif", "quicklook": None}],
            "validation_scope": "structural_and_provenance_not_independent_geophysical_validation",
        }
        summary = {
            "schema_version": "sarguardian-aoi-dashboard-summary/1.0", "status": "PASS",
            "run_id": "fixture-run", "science_commit": "b" * 40, "orchestration_sha": "c" * 40,
            "aoi_name": "custom", "aoi_crs": "EPSG:4326", "aoi_wkt": wkt,
            "aoi_wkt_sha256": "d" * 64, "date_start": "2026-08-01", "date_end": "2026-08-20",
            "date_basis": "secondary_acquisition_date_from_granule_identifier",
            "date_filter_mode": "secondary-acquisition-in-window", "products_expected": 1,
            "products_validated": 1, "products_missing": 0, "gunw_count": 1, "goff_count": 0,
            "science_diagnostics": {"pixel_stack": {"status": "COMPLETED"}, "candidate_checks": {"status": "SKIPPED_UNSUPPORTED_CUSTOM_AOI", "detail": "test fixture"}},
            "science_claim_limit": "Structural validation does not independently validate geophysical accuracy.",
        }
        (root / "aoi-run-summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (root / "aoi-processing-report.json").write_text(json.dumps({"summary": summary, "products": [product], "processing_report": {"status": "PASS"}}), encoding="utf-8")
        (root / "index.html").write_text("<!doctype html><html><body><main>report</main></body></html>", encoding="utf-8")
        return tif, tif_hash

    def test_builds_pair_aware_manifest_layers_and_stac_without_mutating_tiff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tif, before_hash = self._fixture(root)
            receipt = prepare_web_dashboard(root)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(receipt["observations"], 1)
            self.assertEqual(receipt["layers"], 2)
            self.assertEqual(hashlib.sha256(tif.read_bytes()).hexdigest(), before_hash)

            manifest = json.loads((root / "web-dashboard" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["validation"]["independent_geophysical_validation"], "NOT_PERFORMED")
            self.assertEqual(manifest["observations"][0]["reference_date"], "2026-07-21")
            los = next(layer for layer in manifest["layers"] if layer["band"] == 1)
            coh = next(layer for layer in manifest["layers"] if layer["band"] == 2)
            self.assertEqual(los["units"], "mm")
            self.assertEqual(coh["display_scale"]["min"], 0.0)
            self.assertEqual(coh["display_scale"]["max"], 1.0)
            corners = los["corners"]
            self.assertEqual(len(corners), 4)
            self.assertTrue(all(-180 <= p[0] <= 180 and -90 <= p[1] <= 90 for p in corners))

            preview = root / "web-dashboard" / los["preview_asset"]
            with Image.open(preview) as image:
                self.assertEqual(image.mode, "RGBA")
                alpha = np.asarray(image)[..., 3]
                self.assertTrue((alpha == 0).any(), "NoData must remain transparent")
                self.assertTrue((alpha > 0).any(), "Valid pixels must render")

            stac_item = json.loads((root / "web-dashboard" / "stac" / "items" / "GUNW-001.json").read_text(encoding="utf-8"))
            self.assertEqual(stac_item["stac_version"], "1.1.0")
            self.assertEqual(stac_item["properties"]["datetime"], "2026-08-14T00:00:00Z")
            self.assertTrue((root / "web-dashboard" / "dashboard-data.js").is_file())
            updated_html = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("web-dashboard/index.html", updated_html)


if __name__ == "__main__":
    unittest.main()
