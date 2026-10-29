from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "sarguardian-aoi-wkt-dashboard.yml"
AGGREGATOR = ROOT / "tools" / "aggregate_aoi_run.py"
BUILDER = ROOT / "dashboard" / "assets" / "prepare_web_assets.py"
EXPECTED_BUILDER_SHA = "ecd125f68ed61c276406f73a1d77eb27979e204e"


class DashboardWorkflowPinTests(unittest.TestCase):
    def test_workflow_pins_revision_with_interactive_builder(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        references = re.findall(r"(?m)^\s*ref:\s*([0-9a-f]{40})\s*$", workflow)
        self.assertIn(EXPECTED_BUILDER_SHA, references)
        self.assertIn(f'expected="{EXPECTED_BUILDER_SHA}"', workflow)

    def test_pinned_source_contract_has_interactive_asset_builder(self) -> None:
        aggregator = AGGREGATOR.read_text(encoding="utf-8")
        builder = BUILDER.read_text(encoding="utf-8")
        worker = (ROOT / ".github" / "workflows" / "sarguardian-aoi-product-worker.yml").read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("prepare_web_dashboard", aggregator)
        self.assertIn('web-dashboard/manifest.json', builder)
        self.assertIn('web-dashboard/index.html', builder)
        self.assertIn("target_latitude:", workflow)
        self.assertIn("TARGET_LATITUDE: ${{ inputs.target_latitude }}", worker)
        self.assertIn("measure_target_from_raster.py", worker)
        self.assertIn('--aoi-wkt "$SARGUARDIAN_AOI_WKT"', worker)
        self.assertIn("--minimum-valid-pixels 6", worker)
        self.assertIn("science-source/src/local_floor.py", worker)
        self.assertIn('find "$CURATED_DIR/derived" -type f -print | sort', worker)
        self.assertIn("LOCAL_FLOOR_STATUS=", worker)
        self.assertIn("TARGET_MEASUREMENT_STATUS=", worker)
        self.assertIn('SITE_PLACE_NAME: ${{ inputs.place_name }}', workflow)
        self.assertIn('SITE_TARGET_LATITUDE: ${{ inputs.target_latitude }}', workflow)
        self.assertIn('place_name:', workflow)
        self.assertIn('target_longitude:', workflow)
        self.assertIn("def build_site_context(ring:", aggregator)
        self.assertIn('"site_context": summary.get("site_context") or {}', builder)
        self.assertIn("def collect_target_evidence(artifact:", aggregator)


if __name__ == "__main__":
    unittest.main()
