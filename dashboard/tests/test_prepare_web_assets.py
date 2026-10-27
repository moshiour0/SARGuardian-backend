from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
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
            "target_measurement": {
                "status": "MEASURED",
                "measurements": {
                    "target_local_los_median_mm": 2.5, "target_local_range_median_mm": None,
                    "target_local_azimuth_median_mm": None, "mean_coherence": 0.62,
                },
            },
            "local_floor": {
                "status": "MEASURED",
                "metrics": {"radius_px": 6, "local_floor_mm_day": 8.1,
                            "local_floor_ci_lo_mm_day": 6.0, "local_floor_ci_hi_mm_day": 10.5},
            },
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
            "site_context": {
                "place": {"name": "Test ridge", "latitude": 24.7518, "longitude": 90.3864,
                          "coordinates_status": "VALID", "inside_aoi": True},
                "measurement_target": {"status": "IN_AOI_TARGET_CAPTURED", "latitude": 24.7518,
                                       "longitude": 90.3864, "used_by_reader": False, "is_measurement": False},
            },
            "target_measurement_count": 1,
            "local_floor_count": 1,
            "common_reference_timeseries": {
                "schema_version": "sarguardian-common-reference-timeseries/1.0",
                "status": "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED",
                "reason": "Test-only connected synthetic network passes structural gates; external stable-ground reference is not validated.",
                "networks": [{
                    "network": "DESC path 091 frame 01 CRID P05023 GUNW",
                    "common_pixels_outside_target_buffer": 240,
                }],
                "components": [{
                    "network": "DESC path 091 frame 01 CRID P05023 GUNW",
                    "component": 1,
                    "status": "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED",
                    "pairs_count": 4,
                    "redundancy": 1,
                    "series": [
                        {"epoch": "2026-07-21", "cumulative_los_mm": 0.0,
                         "graph_fit_ci95_low_mm": 0.0, "graph_fit_ci95_high_mm": 0.0},
                        {"epoch": "2026-08-02", "cumulative_los_mm": 1.5,
                         "graph_fit_ci95_low_mm": 0.9, "graph_fit_ci95_high_mm": 2.1},
                        {"epoch": "2026-08-14", "cumulative_los_mm": 2.8,
                         "graph_fit_ci95_low_mm": 2.0, "graph_fit_ci95_high_mm": 3.6},
                    ],
                }],
            },
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
            self.assertEqual(manifest["validation"]["visual_assets_status"], "PASS")
            self.assertEqual(manifest["observations"][0]["metrics"]["reader_median_units"], "mm")
            self.assertEqual(manifest["site_context"]["place"]["name"], "Test ridge")
            self.assertEqual(manifest["common_reference_timeseries"]["status"],
                             "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED")
            self.assertEqual(len(manifest["common_reference_timeseries"]["components"][0]["series"]), 3)
            self.assertEqual(manifest["observations"][0]["metrics"]["target_local_los_median_mm"], 2.5)
            self.assertEqual(manifest["observations"][0]["metrics"]["target_local_floor_mm_day"], 8.1)
            site_geojson = json.loads((root / "web-dashboard" / "site.geojson").read_text(encoding="utf-8"))
            self.assertEqual(len(site_geojson["features"]), 2)
            self.assertEqual(site_geojson["features"][0]["geometry"]["coordinates"], [90.3864, 24.7518])
            self.assertIn("measurement_target", site_geojson["features"][1]["properties"]["role"])
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
            collection = json.loads((root / "web-dashboard" / "stac" / "collection.json").read_text(encoding="utf-8"))
            self.assertEqual(collection["license"], "other")
            license_links = [link for link in collection["links"] if link["rel"] == "license"]
            self.assertGreaterEqual(len(license_links), 2)
            self.assertTrue(any("earthdata.nasa.gov" in link["href"] for link in license_links))
            self.assertTrue(any("nisar-docs.asf.alaska.edu" in link["href"] for link in license_links))
            self.assertTrue(collection["providers"])
            self.assertIn("does not relicense source data", collection["sarguardian:license_note"])
            item_path = root / "web-dashboard" / "stac" / "items" / "GUNW-001.json"
            native_href = item_path.parent / stac_item["assets"]["native_raster"]["href"]
            self.assertTrue(native_href.resolve().is_file(), "STAC native asset href must resolve")
            preview_asset = next(v for k, v in stac_item["assets"].items() if k.startswith("preview_band_"))
            self.assertTrue((item_path.parent / preview_asset["href"]).resolve().is_file(), "STAC preview href must resolve")
            self_href = next(link["href"] for link in stac_item["links"] if link["rel"] == "self")
            parent_href = next(link["href"] for link in stac_item["links"] if link["rel"] == "parent")
            self.assertEqual((item_path.parent / self_href).resolve(), item_path.resolve())
            self.assertTrue((item_path.parent / parent_href).resolve().is_file())
            viewer = (root / "web-dashboard" / "index.html").read_text(encoding="utf-8")
            self.assertIn("measurementChart", viewer)
            self.assertIn("measurementTrack", viewer)
            self.assertIn("selected-site-marker", viewer)
            self.assertIn("selected-target-marker", viewer)
            self.assertIn("compare-target-marker", viewer)
            self.assertIn("Target-local GUNW LOS median (mm)", viewer)
            self.assertIn("Target-local detection floor (mm/day)", viewer)
            self.assertIn("function metricUncertainty(p,key)", viewer)
            self.assertIn("target_local_floor_ci_lo_mm_day", viewer)
            self.assertIn("stroke-width','2'", viewer)
            self.assertIn('id="pairCompare"', viewer)
            self.assertIn('id="scenarioSandbox"', viewer)
            self.assertIn("function compatiblePair(a,b)", viewer)
            self.assertIn("function renderCommonReferenceChart()", viewer)
            self.assertIn("manifest.common_reference_timeseries", viewer)
            self.assertIn("DIAGNOSTIC ONLY", viewer)
            self.assertIn("No publishable cumulative diagnostic series", viewer)
            self.assertIn("White bars: fit-only 95% interval", viewer)
            self.assertIn("function renderHypotheticalScenario()", viewer)
            self.assertIn("Comparison withheld", viewer)
            self.assertIn("not a forecast", viewer.lower())
            self.assertIn("bars are not connected", viewer.lower())
            self.assertIn('<script type="module">', viewer)
            self.assertIn("maplibre-gl@6.16.0/dist/maplibre-gl.mjs", viewer)
            self.assertNotIn("dist/maplibre-gl.js", viewer)
            self.assertIn("if(maplibregl && typeof maplibregl.Map==='function')", viewer)
            self.assertNotIn("if(window.maplibregl)", viewer)
            self.assertTrue((root / "web-dashboard" / "dashboard-data.js").is_file())
            if shutil.which("node"):
                module_scripts = re.findall(r'<script type="module">(.*?)</script>', viewer, flags=re.S)
                self.assertEqual(len(module_scripts), 1)
                module_path = root / "viewer-module.mjs"
                module_path.write_text(module_scripts[0], encoding="utf-8")
                syntax = subprocess.run(["node", "--check", str(module_path)], capture_output=True, text=True)
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
            updated_html = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("web-dashboard/index.html", updated_html)


    def test_cross_utm_zones_keep_source_tiffs_and_shared_group_scale(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first_tif, first_hash = self._fixture(root)
            report_path = root / "aoi-processing-report.json"
            summary_path = root / "aoi-run-summary.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            source = report["products"][0]
            folder = root / "product-data" / "GUNW-002"
            folder.mkdir(parents=True)
            bounds = transform_bounds("EPSG:4326", "EPSG:32645", 90.38, 24.715, 90.45, 24.78)
            transform = from_bounds(*bounds, 4, 4)
            second_tif = folder / "fixture-zone45.tif"
            los = np.array([[2, 4, np.nan, -2], [3, 5, 7, 8], [9, 10, 12, 13], [14, 15, 16, 18]], dtype="float32")
            coherence = np.array([[.25, .35, .45, .55], [.65, .75, .85, .95], [.35, .45, .55, .65], [.75, .85, .95, 1.0]], dtype="float32")
            with rasterio.open(second_tif, "w", driver="GTiff", width=4, height=4, count=2,
                               dtype="float32", crs="EPSG:32645", transform=transform, nodata=np.nan) as ds:
                ds.write(los, 1)
                ds.write(coherence, 2)
                ds.set_band_description(1, "LOS displacement (mm)")
                ds.set_band_description(2, "coherence")
            import copy
            second = copy.deepcopy(source)
            second.update({
                "id": "GUNW-002", "reference_date": "2026-08-14", "secondary_date": "2026-09-07",
                "valid_pixels": 15, "metric_value": 8.0,
                "exports": [{"name": second_tif.name, "relative_path": "product-data/GUNW-002/" + second_tif.name, "quicklook": None}],
            })
            report["products"].append(second)
            summary["products_expected"] = 2
            summary["products_validated"] = 2
            summary["products_missing"] = 0
            summary["gunw_count"] = 2
            report["summary"] = summary
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            report_path.write_text(json.dumps(report), encoding="utf-8")
            second_hash = hashlib.sha256(second_tif.read_bytes()).hexdigest()

            receipt = prepare_web_dashboard(root)
            self.assertEqual(receipt["observations"], 2)
            self.assertEqual(receipt["layers"], 4)
            self.assertEqual(hashlib.sha256(first_tif.read_bytes()).hexdigest(), first_hash)
            self.assertEqual(hashlib.sha256(second_tif.read_bytes()).hexdigest(), second_hash)
            manifest = json.loads((root / "web-dashboard" / "manifest.json").read_text(encoding="utf-8"))
            first = next(layer for layer in manifest["layers"] if layer["observation_id"] == "GUNW-001" and layer["band"] == 1)
            second_layer = next(layer for layer in manifest["layers"] if layer["observation_id"] == "GUNW-002" and layer["band"] == 1)
            self.assertEqual(first["source_crs"], "EPSG:32646")
            self.assertEqual(second_layer["source_crs"], "EPSG:32645")
            self.assertEqual(first["preview_crs"], "EPSG:4326")
            self.assertEqual(second_layer["preview_crs"], "EPSG:4326")
            self.assertEqual(first["display_scale"], second_layer["display_scale"])


if __name__ == "__main__":
    unittest.main()
