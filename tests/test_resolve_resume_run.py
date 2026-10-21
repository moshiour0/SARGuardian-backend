from __future__ import annotations

import csv
from pathlib import Path

import pytest

from tools.resolve_resume_run import (
    build_target_manifest,
    choose_compatible_failed_run,
    resolve,
)


def _manifest(run_id: str = "100-1") -> dict:
    return {
        "run_id": run_id,
        "run_profile": "full-source-baseline",
        "aoi": "source",
        "science_commit": "abc123",
        "retention_profile": "derived-only",
        "time_window": {
            "start_date": "2025-01-01",
            "end_date": "2026-12-31",
            "date_basis": "secondary_acquisition_date",
            "inclusive": True,
            "baseline_products_in_window": 2,
            "baseline_products_total": 2,
            "covers_full_baseline": True,
        },
        "products": [
            {"id": "GUNW-001", "granule_name": "g1.h5", "product_type": "GUNW", "maturity": "PROVISIONAL"},
            {"id": "GOFF-002", "granule_name": "g2.h5", "product_type": "GOFF", "maturity": "BETA"},
        ],
    }


def _run(run_id: str, created: str, *, conclusion="failure", path=None, branch="main") -> dict:
    return {
        "id": int(run_id),
        "created_at": created,
        "status": "completed",
        "conclusion": conclusion,
        "event": "workflow_dispatch",
        "head_branch": branch,
        "path": path or ".github/workflows/sarguardian-streaming-batch.yml",
    }


def test_auto_resume_picks_newest_compatible_failed_run_and_skips_invalid_candidates():
    current = _manifest("999-1")
    runs = [
        _run("103", "2026-10-21T10:00:00Z"),  # newest but incompatible manifest
        _run("102", "2026-10-21T09:00:00Z", path=".github/workflows/other.yml"),
        _run("101", "2026-10-21T08:00:00Z", conclusion="success"),
        _run("100", "2026-10-21T07:00:00Z"),  # newest compatible eligible failure
    ]

    def load_manifest(run_id: str):
        if run_id == "103":
            incompatible = _manifest("103-1")
            incompatible["aoi"] = "other"
            return incompatible, True
        if run_id == "100":
            return _manifest("100-1"), True
        return _manifest(f"{run_id}-1"), True

    chosen, scanned = choose_compatible_failed_run(
        runs,
        current,
        current_run_id="999",
        branch="main",
        workflow_path=".github/workflows/sarguardian-streaming-batch.yml",
        manifest_loader=load_manifest,
    )
    assert chosen == "100"
    assert scanned == 2


def test_auto_resume_returns_none_when_no_compatible_checkpoint_exists():
    current = _manifest("999-1")
    run_id, mode, scanned = resolve(
        "",
        run_profile="full-source-baseline",
        current_manifest=current,
        repo="owner/repo",
        branch="main",
        current_run_id="999",
        workflow_path=".github/workflows/sarguardian-streaming-batch.yml",
        token="test-token",
        runs_loader=lambda: [_run("100", "2026-10-21T07:00:00Z")],
        manifest_loader=lambda _rid: (None, False),
    )
    assert run_id == ""
    assert mode == "auto-no-compatible-checkpoints"
    assert scanned == 1


def test_explicit_none_disables_resume_discovery():
    run_id, mode, scanned = resolve(
        "none",
        run_profile="full-source-baseline",
        current_manifest=_manifest("999-1"),
        repo="owner/repo",
        branch="main",
        current_run_id="999",
        workflow_path=".github/workflows/sarguardian-streaming-batch.yml",
        token="",
    )
    assert (run_id, mode, scanned) == ("", "disabled-by-user", 0)


def test_pilot_does_not_trigger_auto_resume_search():
    run_id, mode, scanned = resolve(
        "",
        run_profile="validation-pilot",
        current_manifest=None,
        repo="owner/repo",
        branch="main",
        current_run_id="999",
        workflow_path=".github/workflows/sarguardian-streaming-batch.yml",
        token="",
    )
    assert (run_id, mode, scanned) == ("", "not-applicable-to-pilot", 0)


def test_auto_resume_requires_token_only_for_full_baseline_auto_discovery():
    with pytest.raises(ValueError, match="GITHUB_TOKEN_REQUIRED_FOR_AUTO_RESUME_DISCOVERY"):
        resolve(
            "",
            run_profile="full-source-baseline",
            current_manifest=_manifest("999-1"),
            repo="owner/repo",
            branch="main",
            current_run_id="999",
            workflow_path=".github/workflows/sarguardian-streaming-batch.yml",
            token="",
            runs_loader=lambda: [],
        )


def test_build_target_manifest_requires_entire_pinned_33_product_window(tmp_path: Path):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    for family, count in (("GUNW", 15), ("GOFF", 18)):
        with (outputs / f"{family.lower()}_stats_source.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["file", "maturity"])
            writer.writeheader()
            for i in range(count):
                # The third timestamp is the secondary acquisition date.
                month = i % 12 + 1
                name = (
                    f"NISAR_L2_PR_{family}_001_098_A_016_{i + 1:03d}_4000_SH_"
                    f"20250101T123456_20250101T123500_2025{month:02d}15T123456_"
                    f"2025{month:02d}15T123500_P00001_F_F_J_001.h5"
                )
                writer.writerow({"file": name, "maturity": "PROVISIONAL"})

    result = build_target_manifest(
        tmp_path,
        "full-source-baseline",
        "2025-01-01",
        "2026-12-31",
        "derived-only",
    )
    assert result is not None
    assert result["time_window"]["covers_full_baseline"] is True
    assert result["time_window"]["baseline_products_total"] == 33
    assert len(result["products"]) == 33
    assert result["products"][0]["id"] == "GUNW-001"
    assert result["products"][15]["id"] == "GOFF-016"

    partial = build_target_manifest(
        tmp_path,
        "full-source-baseline",
        "2025-03-01",
        "2026-12-31",
        "derived-only",
    )
    assert partial is None
