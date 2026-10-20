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


def test_failed_product_always_emits_machine_readable_diagnostics():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "- name: Write a compact diagnostic receipt even when a product fails" in text
    assert "failure-diagnostics.json" in text
    assert "if-no-files-found: error" in text
