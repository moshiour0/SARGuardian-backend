#!/usr/bin/env python3
"""Resolve a safe SARGuardian full-baseline resume source.

A blank resume_from_run_id means: for full-source-baseline runs only, find the
newest completed failed/cancelled run from this same workflow whose manifest is
compatible with this request and whose checkpoint artifacts still exist.
Type "none" to force a cold run, or provide a numeric run ID to select it
explicitly. Authentication tokens are never printed.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable

# GitHub Actions executes this file as `python tools/resolve_resume_run.py`.
# In that mode Python puts tools/ (not the repository root) on sys.path, so
# namespace-package imports such as `from tools.time_window ...` otherwise fail.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.resume_streamed_run import validate_resume_compatibility
from tools.time_window import filter_products_by_time_window

SCIENCE_COMMIT = "ab547ecc82bcc4d6ccef545a59852536c2beacc6"
WORKFLOW_ID = 390313691
WORKFLOW_PATH = ".github/workflows/sarguardian-streaming-batch.yml"
API_ROOT = "https://api.github.com"
TRANSIENT_HTTP = {429, 500, 502, 503, 504}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward an API bearer token to an artifact CDN redirect host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def build_target_manifest(
    science_root: Path, run_profile: str, start_date: str, end_date: str,
    retention_profile: str,
) -> dict[str, Any] | None:
    """Build only the compatibility-critical fields using the pinned source CSVs."""
    if run_profile != "full-source-baseline":
        return None
    if retention_profile not in {"derived-only", "full-lossless"}:
        raise ValueError("RETENTION_PROFILE_INVALID")

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for family in ("GUNW", "GOFF"):
        path = science_root / "outputs" / f"{family.lower()}_stats_source.csv"
        if not path.is_file():
            raise ValueError(f"BASELINE_CSV_MISSING family={family}")
        import csv

        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames or not {"file", "maturity"}.issubset(reader.fieldnames):
                raise ValueError(f"BASELINE_SCHEMA_INVALID family={family}")
            for item in reader:
                name = Path((item.get("file") or "").strip()).name
                maturity = (item.get("maturity") or "").strip().upper()
                if not re.fullmatch(
                    r"NISAR_L2_(?:(?:PR|UR|OD)_)?"
                    + family + r"_[A-Za-z0-9_.-]{10,250}\.h5",
                    name,
                ):
                    raise ValueError(f"BASELINE_PRODUCT_NAME_INVALID family={family}")
                if maturity not in {"BETA", "PROVISIONAL"}:
                    raise ValueError(f"BASELINE_MATURITY_INVALID family={family}")
                key = (family, name)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "product_type": family,
                    "granule_name": name,
                    "maturity": maturity,
                    "expected_source_bytes": 2_400_000_000 if family == "GUNW" else 1_000_000_000,
                })

    counts = {family: sum(r["product_type"] == family for r in rows) for family in ("GUNW", "GOFF")}
    if counts != {"GUNW": 15, "GOFF": 18}:
        raise ValueError(f"PINNED_BASELINE_PRODUCT_COUNTS_CHANGED counts={counts}")

    window_rows = filter_products_by_time_window(rows, start_date, end_date)
    all_names = {r["granule_name"] for r in rows}
    window_names = {r["granule_name"] for r in window_rows}
    # A resume is deliberately limited to the exact 33-product baseline. Partial
    # date selections need their own independent manifest and never auto-resume.
    if not window_rows or window_names != all_names:
        return None

    selected = [dict(r) for r in window_rows]
    for idx, row in enumerate(selected, 1):
        row["id"] = f'{row["product_type"]}-{idx:03d}'
    return {
        "run_profile": "full-source-baseline",
        "aoi": "source",
        "science_commit": SCIENCE_COMMIT,
        "retention_profile": retention_profile,
        "time_window": {
            "start_date": start_date,
            "end_date": end_date,
            "date_basis": "secondary_acquisition_date",
            "inclusive": True,
            "baseline_products_in_window": len(window_rows),
            "baseline_products_total": len(rows),
            "covers_full_baseline": True,
        },
        "products": selected,
    }


def _request(url: str, token: str, *, allow_redirect: bool = False) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SARGuardian-resume-resolver",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    if allow_redirect:
        opener = urllib.request.build_opener(NoRedirect())
        try:
            with opener.open(request, timeout=25) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise
            location = exc.headers.get("Location")
            if not location:
                raise RuntimeError("ARTIFACT_REDIRECT_WITHOUT_LOCATION") from exc
            # The signed redirect URL is sufficient; intentionally omit the API token.
            with urllib.request.urlopen(location, timeout=60) as response:
                return response.read()
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def request_bytes(url: str, token: str, *, allow_redirect: bool = False) -> bytes:
    """Retry transient API/network errors with bounded backoff."""
    for attempt in range(3):
        try:
            return _request(url, token, allow_redirect=allow_redirect)
        except urllib.error.HTTPError as exc:
            if exc.code not in TRANSIENT_HTTP or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
        time.sleep(1 + attempt)
    raise RuntimeError("GITHUB_API_REQUEST_EXHAUSTED")


def api_json(url: str, token: str) -> dict[str, Any]:
    payload = json.loads(request_bytes(url, token).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GITHUB_API_RESPONSE_NOT_OBJECT")
    return payload


def get_run(repo: str, run_id: str, token: str) -> dict[str, Any]:
    return api_json(f"{API_ROOT}/repos/{repo}/actions/runs/{run_id}", token)


def list_workflow_runs(repo: str, branch: str, token: str) -> list[dict[str, Any]]:
    # Include main-run checkpoints while testing this flow on a feature branch.
    # Candidate eligibility below still limits reuse to the current branch or main.
    query = urllib.parse.urlencode({"event": "workflow_dispatch", "per_page": 50})
    result = api_json(f"{API_ROOT}/repos/{repo}/actions/workflows/{WORKFLOW_ID}/runs?{query}", token)
    runs = result.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("GITHUB_WORKFLOW_RUN_LIST_INVALID")
    return [x for x in runs if isinstance(x, dict)]


def get_run_manifest(repo: str, run_id: str, token: str) -> tuple[dict[str, Any] | None, bool]:
    """Return the run manifest and whether at least one product checkpoint exists."""
    result = api_json(
        f"{API_ROOT}/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100", token
    )
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        return None, False
    manifest_artifact = next((
        x for x in artifacts
        if isinstance(x, dict) and x.get("name") == "sarguardian-stream-run-manifest"
        and not x.get("expired")
    ), None)
    has_checkpoint = any(
        isinstance(x, dict) and not x.get("expired")
        and str(x.get("name", "")).startswith(("sarguardian-granule-", "sarguardian-cleanup-"))
        for x in artifacts
    )
    if not manifest_artifact:
        return None, has_checkpoint
    artifact_id = manifest_artifact.get("id")
    if not artifact_id:
        return None, has_checkpoint
    archive_url = f"{API_ROOT}/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    archive_bytes = request_bytes(archive_url, token, allow_redirect=True)
    if len(archive_bytes) > 10 * 1024 * 1024:
        return None, has_checkpoint
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            names = [n for n in archive.namelist() if Path(n).name == "manifest.json"]
            if len(names) != 1:
                return None, has_checkpoint
            parsed = json.loads(archive.read(names[0]).decode("utf-8"))
    except (OSError, ValueError, zipfile.BadZipFile, KeyError, UnicodeDecodeError):
        return None, has_checkpoint
    return (parsed if isinstance(parsed, dict) else None), has_checkpoint


def _eligible_failed_run(
    run: dict[str, Any], *, current_run_id: str, branch: str, workflow_path: str,
) -> bool:
    allowed_branches = {branch, "main"}
    return (
        str(run.get("id", "")) != str(current_run_id)
        and run.get("status") == "completed"
        and run.get("conclusion") in {"failure", "cancelled", "timed_out"}
        and run.get("event") == "workflow_dispatch"
        and run.get("head_branch") in allowed_branches
        and run.get("path") == workflow_path
    )


def choose_compatible_failed_run(
    runs: list[dict[str, Any]], current_manifest: dict[str, Any], *,
    current_run_id: str, branch: str, workflow_path: str,
    manifest_loader: Callable[[str], tuple[dict[str, Any] | None, bool]],
) -> tuple[str, int]:
    """Choose the newest compatible failed run that still has checkpoint artifacts."""
    compatible: list[tuple[str, str]] = []
    scanned = 0
    candidates = sorted(
        (r for r in runs if _eligible_failed_run(
            r, current_run_id=current_run_id, branch=branch, workflow_path=workflow_path
        )),
        key=lambda r: str(r.get("created_at", "")),
        reverse=True,
    )
    for run in candidates:
        run_id = str(run.get("id", ""))
        scanned += 1
        previous, has_checkpoint = manifest_loader(run_id)
        if not previous or not has_checkpoint:
            continue
        if not str(previous.get("run_id", "")).startswith(run_id + "-"):
            continue
        try:
            validate_resume_compatibility(current_manifest, previous)
        except ValueError:
            continue
        compatible.append((str(run.get("created_at", "")), run_id))
        # Candidates are in descending created_at order; first compatible wins.
        return run_id, scanned
    return "", scanned


def resolve(
    requested: str, *, run_profile: str, current_manifest: dict[str, Any] | None,
    repo: str, branch: str, current_run_id: str, workflow_path: str,
    token: str, runs_loader: Callable[[], list[dict[str, Any]]] | None = None,
    manifest_loader: Callable[[str], tuple[dict[str, Any] | None, bool]] | None = None,
) -> tuple[str, str, int]:
    """Return (run_id, selection mode, candidate runs inspected)."""
    value = (requested or "").strip().lower()
    if value == "none":
        return "", "disabled-by-user", 0
    if value:
        if not value.isdigit():
            raise ValueError("RESUME_RUN_ID_MUST_BE_NUMERIC_OR_NONE")
        if run_profile != "full-source-baseline" or current_manifest is None:
            raise ValueError("RESUME_REQUIRES_FULL_SOURCE_BASELINE")
        return value, "manual", 0
    if run_profile != "full-source-baseline":
        return "", "not-applicable-to-pilot", 0
    if current_manifest is None:
        return "", "not-applicable-to-partial-window", 0
    if not token:
        raise ValueError("GITHUB_TOKEN_REQUIRED_FOR_AUTO_RESUME_DISCOVERY")
    runs_loader = runs_loader or (lambda: list_workflow_runs(repo, branch, token))
    manifest_loader = manifest_loader or (lambda rid: get_run_manifest(repo, rid, token))
    runs = runs_loader()
    run_id, scanned = choose_compatible_failed_run(
        runs, current_manifest, current_run_id=current_run_id, branch=branch,
        workflow_path=workflow_path, manifest_loader=manifest_loader,
    )
    return run_id, ("auto-compatible-failure" if run_id else "auto-no-compatible-checkpoints"), scanned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--science-root", required=True, type=Path)
    parser.add_argument("--run-profile", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--retention-profile", required=True)
    parser.add_argument("--requested-run-id", default="")
    parser.add_argument("--workflow-path", default=WORKFLOW_PATH)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", "main"))
    parser.add_argument("--current-run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    args = parser.parse_args()
    try:
        target = build_target_manifest(
            args.science_root, args.run_profile, args.start_date, args.end_date, args.retention_profile
        )
        run_id, mode, scanned = resolve(
            args.requested_run_id, run_profile=args.run_profile, current_manifest=target,
            repo=args.repo, branch=args.branch, current_run_id=args.current_run_id,
            workflow_path=args.workflow_path, token=args.token,
        )
    except Exception as exc:
        print(f"ERROR=RESUME_SOURCE_RESOLUTION_FAILED type={type(exc).__name__} detail={str(exc)[:300]}")
        return 2

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as gh:
            gh.write(f"run_id={run_id}\n")
            gh.write(f"mode={mode}\n")
    print(f"RESUME_SELECTION_MODE={mode}")
    print(f"RESUME_SELECTED_RUN_ID={run_id or 'none'}")
    print(f"RESUME_FAILED_RUN_CANDIDATES_INSPECTED={scanned}")
    print("RESUME_SECRET_VALUES_PRINTED=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
