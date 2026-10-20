from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "sarguardian-streaming-batch.yml"


def test_aggregate_job_checks_out_backend_before_science_repository():
    text = WORKFLOW.read_text(encoding="utf-8")
    aggregate = text.split("  aggregate:\n", 1)[1]
    backend = aggregate.index("- name: Checkout backend aggregation tools")
    science = aggregate.index("- name: Checkout pinned science baseline")
    assert backend < science
    assert "path: science-source" in aggregate[science:science + 400]


def test_streaming_workflow_is_manual_to_avoid_unexpected_live_storage_use():
    text = WORKFLOW.read_text(encoding="utf-8")
    triggers = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in triggers
    assert "\n  push:" not in triggers
    assert "inputs.run_profile || 'validation-pilot'" in text
    assert "max-parallel: 1" in text


def test_raw_deletion_is_only_after_verified_drive_upload():
    text = WORKFLOW.read_text(encoding="utf-8")
    marker = "- name: Delete local raw/archive only after successful remote retention"
    section = text.split(marker, 1)[1].split("\n      - name:", 1)[0]
    assert "if: success()" in section
    assert "DRIVE_OUTPUTS_NOT_REMOTELY_VERIFIED" in text
    assert "FULL_LOSSLESS_ARCHIVE_NOT_FOUND_IN_DRIVE_RECEIPT" in text
    assert "REFUSING_RAW_DELETION_WITHOUT_REMOTE_VERIFICATION" in section
    assert "REFUSING_RAW_DELETION_WITHOUT_DERIVED_BASELINE_VALIDATION" in section
    assert "REMOTE_REQUIRED_DERIVED_OUTPUT_MISSING" in section


def test_product_run_diagnostics_are_explicitly_pre_cleanup():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "- name: Write a compact diagnostic receipt even when a product fails" in text
    assert "product-run-diagnostics.json" in text
    assert '"schema_version": "sarguardian-product-run-diagnostic/1.0"' in text
    assert "raw_hdf5_present_at_diagnostic_time" in text
    assert "if-no-files-found: error" in text


def test_quota_uses_actual_processed_upload_files_not_raw_estimates():
    text = WORKFLOW.read_text(encoding="utf-8")
    manifest = text.split("  manifest:", 1)[1].split("  process-one:", 1)[0]
    process = text.split("  process-one:\n", 1)[1].split("\n  aggregate:", 1)[0]
    assert "preflight_drive_quota.py" not in text
    assert "expected_source_bytes" in manifest  # disk/download estimate only
    assert "Create a full-lossless retained HDF5 copy" in process
    assert "Upload validated per-product outputs to Drive with checksum verification" in process
    assert "default: derived-only" in text
    assert "if: env.RETENTION_PROFILE == 'full-lossless'" in process
    assert "derived-output-validation.json" in process
    uploader = (WORKFLOW.parents[2] / "tools" / "drive_resumable_upload.py").read_text(encoding="utf-8")
    assert "CURATED_UPLOAD_ACTUAL_BYTES" in uploader
    assert "DRIVE_NEW_BYTES_REQUIRED_ACTUAL" in uploader
    assert "DRIVE_ACTUAL_OUTPUT_QUOTA_CHECK=PASS" in uploader
    assert "DRIVE_QUOTA_INSUFFICIENT" in uploader


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

def test_inline_json_receipts_do_not_append_literal_backslash_n():
    text = WORKFLOW.read_text(encoding="utf-8")
    # A doubled escape writes the two characters "\\n" after the JSON document,
    # which Python's json.loads rejects as "Extra data".
    assert r'json.dumps(metadata, indent=2) + "\\n"' not in text
    assert r'json.dumps(meta,indent=2)+"\\n"' not in text
    assert r'json.dumps(record,indent=2)+"\\n"' not in text

def test_failed_download_diagnostics_are_preserved_for_aggregation():
    text = WORKFLOW.read_text(encoding="utf-8")
    diagnostic = text.split(
        "- name: Write a compact diagnostic receipt even when a product fails", 1
    )[1].split("\n      - name:", 1)[0]
    assert "DOWNLOAD_LOG: ${{ runner.temp }}/sarguardian-download-${{ matrix.id }}.log" in diagnostic
    assert '"DIRECT_PRODUCT_DIAGNOSTIC="' in diagnostic
    assert '"download_diagnostics": download_diagnostics' in diagnostic
    assert '"download_error_code": download_error_code' in diagnostic
    aggregator = (WORKFLOW.parents[2] / "tools" / "aggregate_streamed_outputs.py").read_text(encoding="utf-8")
    assert "read_product_diagnostic_context(artifact_dir)" in aggregator
    assert '"download_error_code": record.get("download_error_code")' in aggregator

def test_full_baseline_preflights_urgent_response_products_before_matrix_jobs():
    text = WORKFLOW.read_text(encoding="utf-8")
    manifest = text.split("  manifest:\n", 1)[1].split("\n  process-one:", 1)[0]
    preflight = manifest.index("- name: Fail fast when a selected urgent-response baseline product is unavailable")
    preserve = manifest.index("- name: Preserve run manifest for aggregation")
    assert preserve < preflight
    assert "if: inputs.run_profile == 'full-source-baseline'" in manifest[preflight - 250:preflight + 150]
    assert "--probe-only" in manifest[preflight:]
    assert "ERROR=UR_BASELINE_SOURCE_UNAVAILABLE" in manifest[preflight:]
    assert "full-baseline processing stopped before any product downloads" in manifest[preflight:]

