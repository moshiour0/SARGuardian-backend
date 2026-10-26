from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "sarguardian-aoi-wkt-dashboard.yml"
AGGREGATOR = ROOT / "tools" / "aggregate_aoi_run.py"
BUILDER = ROOT / "dashboard" / "assets" / "prepare_web_assets.py"
EXPECTED_BUILDER_SHA = "b9cdbc66c9d317ad005b3df8131c32a034a3de53"


class DashboardWorkflowPinTests(unittest.TestCase):
    def test_workflow_pins_revision_with_interactive_builder(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        references = re.findall(r"(?m)^\s*ref:\s*([0-9a-f]{40})\s*$", workflow)
        self.assertIn(EXPECTED_BUILDER_SHA, references)
        self.assertIn(f'expected="{EXPECTED_BUILDER_SHA}"', workflow)

    def test_pinned_source_contract_has_interactive_asset_builder(self) -> None:
        aggregator = AGGREGATOR.read_text(encoding="utf-8")
        builder = BUILDER.read_text(encoding="utf-8")
        self.assertIn("prepare_web_dashboard", aggregator)
        self.assertIn('web-dashboard/manifest.json', builder)
        self.assertIn('web-dashboard/index.html', builder)


if __name__ == "__main__":
    unittest.main()
