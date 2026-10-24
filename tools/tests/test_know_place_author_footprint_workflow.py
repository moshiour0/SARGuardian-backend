from pathlib import Path


def test_footprint_workflow_reads_acquisition_copied_derived_inputs() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github" / "workflows" / "know-place-author-exact-replay.yml").read_text(
        encoding="utf-8"
    )
    start = workflow.index("      - name: Run full-footprint screen and compare archive golden outputs")
    end = workflow.index("      - name: Remove temporary public author archive and terrain", start)
    step = workflow[start:end]

    assert '--config "$DERIVED_ROOT/know-place-inputs.json"' in step
    assert '--source-manifest "$DERIVED_ROOT/author-exact-source-manifest.json"' in step
    assert '--config "$RUN_ROOT/know-place-inputs.json"' not in step
    assert '--source-manifest "$RUN_ROOT/author-exact-source-manifest.json"' not in step
