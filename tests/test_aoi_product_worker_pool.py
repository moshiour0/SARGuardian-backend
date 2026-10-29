from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "sarguardian-aoi-wkt-dashboard.yml"
sys.path.insert(0, str(ROOT / "tools"))

from drive_resumable_upload import DriveError
from prepare_aoi_drive_folders import prepare_drive_folders


class FakeDrive:
    def __init__(self):
        self.created = []

    def ensure_folder(self, parent, name):
        self.created.append((parent, name))
        return f"folder-{len(self.created)}"


def sample_manifest():
    return {
        "products": [
            {"id": "GUNW-001", "product_type": "GUNW", "maturity": "PROVISIONAL",
             "granule_name": "NISAR_L2_PR_GUNW_AAAAAAAAAAAA.h5"},
            {"id": "GUNW-002", "product_type": "GUNW", "maturity": "PROVISIONAL",
             "granule_name": "NISAR_L2_PR_GUNW_BBBBBBBBBBBB.h5"},
            {"id": "GOFF-003", "product_type": "GOFF", "maturity": "BETA",
             "granule_name": "NISAR_L2_PR_GOFF_CCCCCCCCCCCC.h5"},
        ]
    }


def test_aoi_workflow_bounds_initial_and_retry_workers_at_fifteen():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("max-parallel: 15") == 2
    assert "max-parallel: 1" not in text


def test_drive_shared_folders_are_prepared_before_parallel_matrix():
    text = WORKFLOW.read_text(encoding="utf-8")
    manifest = text.split("  manifest:\n", 1)[1].split("  process-products:\n", 1)[0]
    assert "path: workflow-support" in manifest
    assert "ref: ${{ github.sha }}" in manifest
    assert "Prepare shared Drive folder hierarchy before parallel product workers" in manifest
    assert manifest.index("Validate WKT, search ASF exact polygon and build input manifest") < manifest.index(
        "Prepare shared Drive folder hierarchy before parallel product workers"
    )
    assert manifest.index("Prepare shared Drive folder hierarchy before parallel product workers") < manifest.index(
        "Publish the selected-product manifest"
    )
    assert "DRIVE_VERSION_TAG: ${{ github.run_id }}-${{ github.run_attempt }}" in manifest


def test_folder_preflight_creates_each_shared_edge_only_once():
    drive = FakeDrive()
    count = prepare_drive_folders(
        sample_manifest(), drive, parent_id="root-parent", version_tag="12345-1"
    )
    assert count == 3
    assert len(drive.created) == 5
    assert drive.created == [
        ("root-parent", "SARGuardian-DataArchive"),
        ("folder-1", "GUNW"),
        ("folder-2", "PROVISIONAL"),
        ("folder-1", "GOFF"),
        ("folder-4", "BETA"),
    ]


def test_folder_preflight_rejects_duplicate_product_before_drive_mutation():
    manifest = sample_manifest()
    manifest["products"].append(dict(manifest["products"][0], id="GUNW-004"))
    drive = FakeDrive()
    with pytest.raises(ValueError, match="AOI_MANIFEST_DUPLICATE_OR_INCOMPLETE_PRODUCT"):
        prepare_drive_folders(manifest, drive, parent_id="root-parent", version_tag="12345-1")
    assert drive.created == []


def test_folder_preflight_rejects_empty_manifest_before_drive_mutation():
    drive = FakeDrive()
    with pytest.raises(ValueError, match="AOI_MANIFEST_HAS_NO_SELECTED_PRODUCTS"):
        prepare_drive_folders({"products": []}, drive, parent_id="root-parent", version_tag="12345-1")
    assert drive.created == []
