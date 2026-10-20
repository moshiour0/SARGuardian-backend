from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "sarguardian-streaming-batch.yml"


def test_aggregate_job_checks_out_backend_before_science_repository():
    text = WORKFLOW.read_text(encoding="utf-8")
    aggregate = text.split("  aggregate:\n", 1)[1]
    backend = aggregate.index("- name: Checkout backend aggregation tools")
    science = aggregate.index("- name: Checkout pinned science baseline")
    assert backend < science
    assert "path: science-source" in aggregate[science:science + 400]


def test_streaming_workflow_runs_low_cost_pilot_after_main_changes():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "push:\n    branches: [main]" in text
    assert "inputs.run_profile || 'validation-pilot'" in text
    assert "max-parallel: 1" in text


def test_raw_deletion_is_only_after_verified_drive_upload():
    text = WORKFLOW.read_text(encoding="utf-8")
    marker = "- name: Delete local raw/archive only after successful remote retention"
    section = text.split(marker, 1)[1].split("\n      - name:", 1)[0]
    assert "if: success()" in section
    assert "DRIVE_ARCHIVE_NOT_REMOTELY_VERIFIED" in text
    assert "REFUSING_RAW_DELETION_WITHOUT_REMOTE_VERIFICATION" in section


def test_product_run_diagnostics_are_explicitly_pre_cleanup():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "- name: Write a compact diagnostic receipt even when a product fails" in text
    assert "product-run-diagnostics.json" in text
    assert '"schema_version": "sarguardian-product-run-diagnostic/1.0"' in text
    assert "raw_hdf5_present_at_diagnostic_time" in text
    assert "if-no-files-found: error" in text


def test_drive_quota_is_checked_before_any_product_download():
    text = WORKFLOW.read_text(encoding="utf-8")
    manifest = text.split("  manifest:\\n", 1)[1].split("\\n  process-one:", 1)[0]
    assert "Preflight Drive quota before starting any product downloads" in manifest
    assert "python tools/preflight_drive_quota.py" in manifest
    assert manifest.index("preflight_drive_quota.py") < manifest.index("Preserve run manifest for aggregation")


def test_cleanup_receipt_is_uploaded_and_aggregator_requires_it():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "LOCAL_CLEANUP_RECEIPT_GATE_FAILED" in text
    assert "LOCAL_CLEANUP_RECEIPT_NOT_REMOTELY_VERIFIED" in text
    assert "local-cleanup-receipt.json" in text
    assert "drive-cleanup-upload-receipt.json" in text
    assert 'pattern: sarguardian-cleanup-*' in text
    assert '--cleanup-artifact-root "$root/cleanup-artifacts"' in text


def test_download_reuses_the_pinned_source_acquisition_code_in_both_workflows():
    root = Path(__file__).resolve().parents[1]
    downloader = (root / "tools" / "download_nisar_product.py").read_text(encoding="utf-8")
    stream = WORKFLOW.read_text(encoding="utf-8")
    live = (root / ".github" / "workflows" / "sarguardian-live-validation.yml").read_text(encoding="utf-8")
    assert "src" in downloader and "nisar_acquisition.py" in downloader
    assert "def direct_product_url(" in downloader
    assert "def probe_direct_product(" in downloader
    assert "acquisition.build_session()" in downloader
    assert "asf_search.download_url" in downloader
    assert "query_by_year(" not in downloader
    assert "earthaccess" not in downloader.lower()
    for workflow in (stream, live):
        assert "python tools/download_nisar_product.py" in workflow
        assert '--science-root "$PWD/science-source" --aoi "$AOI_NAME"' in workflow


def test_granule_drive_uploads_are_scoped_to_a_unique_run_folder():
    root = Path(__file__).resolve().parents[1]
    uploader = (root / "tools" / "drive_resumable_upload.py").read_text(encoding="utf-8")
    assert 'names.extend(["Runs", version_tag])' in uploader
    for filename in (
        "sarguardian-streaming-batch.yml",
        "sarguardian-live-validation.yml",
        "sarguardian-retention-pilot.yml",
    ):
        workflow = (root / ".github" / "workflows" / filename).read_text(encoding="utf-8")
        assert "DRIVE_VERSION_TAG: ${{ github.run_id }}-${{ github.run_attempt }}" in workflow
        assert '--version-tag "$DRIVE_VERSION_TAG"' in workflow
