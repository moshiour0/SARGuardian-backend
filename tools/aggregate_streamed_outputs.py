#!/usr/bin/env python3
"""Aggregate single-granule SARGuardian reader outputs and audit batch equivalence.

The workflow creates one artifact per raw product. This tool reassembles only
the small derived outputs, checks them against the pinned repository's committed
batch baselines, then runs the downstream AOI-source analysis from those outputs.
It never needs the original raw HDF5 files in the aggregation job.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

NUMERIC_REL_TOL = 2e-4
NUMERIC_ABS_TOL = 1e-4
IGNORE_STAT_FIELDS = {"export_mb"}  # file sizes can vary slightly across GDAL builds
BASELINE_DOWNSTREAM = [
    "ts_goff_source.csv",
    "local_floor_candidates.csv",
    "local_floor_phase_candidates.csv",
    "common_ref_summer.csv",
    "bound_source.csv",
]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV header missing: {path}")
        return list(reader.fieldnames), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def row_key(row: dict[str, str], fields: list[str]) -> tuple[str, ...]:
    # Each scientific table has a different natural key. Prefer the most
    # specific one so candidate-level rows never collide on their input file.
    candidates = (
        ("file", "layer"),
        ("target_id", "file", "window_px", "reading"),
        ("target_id", "file", "window_px"),
        ("target_id", "pair", "window_px"),
        ("geometry", "component", "epoch"),
        ("id",),
        ("file",),
    )
    chosen = next((group for group in candidates if all(k in fields for k in group)), tuple(fields))
    return tuple((row.get(k) or "").strip() for k in chosen)


def value_equal(expected: str, actual: str, field: str) -> bool:
    e, a = (expected or "").strip(), (actual or "").strip()
    if e == a:
        return True
    if field in IGNORE_STAT_FIELDS:
        try:
            return math.isclose(float(e), float(a), rel_tol=0.02, abs_tol=0.05)
        except (ValueError, TypeError):
            return False
    if e.lower() in {"nan", "inf", "-inf"} or a.lower() in {"nan", "inf", "-inf"}:
        return e.lower() == a.lower()
    try:
        ef, af = float(e), float(a)
    except (ValueError, TypeError):
        return False
    return math.isclose(ef, af, rel_tol=NUMERIC_REL_TOL, abs_tol=NUMERIC_ABS_TOL)


def compare_rows(
    expected_rows: list[dict[str, str]],
    actual_rows: list[dict[str, str]],
    fields: list[str],
    *,
    label: str,
    errors: list[dict[str, Any]],
    limit: int = 100,
) -> dict[str, Any]:
    expected_map: dict[tuple[str, ...], dict[str, str]] = {}
    actual_map: dict[tuple[str, ...], dict[str, str]] = {}
    for side, rows, target in (
        ("baseline", expected_rows, expected_map),
        ("streamed", actual_rows, actual_map),
    ):
        for row in rows:
            key = row_key(row, fields)
            if key in target:
                if len(errors) < limit:
                    errors.append({"table": label, "problem": f"duplicate_{side}_key", "key": key})
            target[key] = row
    missing = sorted(set(expected_map) - set(actual_map))
    extra = sorted(set(actual_map) - set(expected_map))
    if missing and len(errors) < limit:
        errors.append({"table": label, "problem": "missing_rows", "keys": missing[:20]})
    if extra and len(errors) < limit:
        errors.append({"table": label, "problem": "unexpected_rows", "keys": extra[:20]})
    field_mismatches = 0
    for key in sorted(set(expected_map) & set(actual_map)):
        er, ar = expected_map[key], actual_map[key]
        for field in fields:
            if field not in er or field not in ar:
                if len(errors) < limit:
                    errors.append({"table": label, "problem": "missing_column_value", "key": key, "field": field})
                field_mismatches += 1
                continue
            if not value_equal(er[field], ar[field], field):
                field_mismatches += 1
                if len(errors) < limit:
                    errors.append({
                        "table": label, "problem": "value_mismatch", "key": key,
                        "field": field, "baseline": er[field], "streamed": ar[field],
                    })
    return {
        "table": label,
        "baseline_rows": len(expected_rows),
        "streamed_rows": len(actual_rows),
        "row_keys_missing": len(missing),
        "row_keys_extra": len(extra),
        "field_mismatches": field_mismatches,
        "status": "PASS" if not missing and not extra and not field_mismatches else "FAIL",
    }


def safe_relative(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Artifact path escapes artifact root: {relative}") from exc
    return candidate


def locate_product_artifact(artifact_root: Path, product_id: str) -> Path:
    expected = artifact_root / f"sarguardian-granule-{product_id}"
    if expected.is_dir():
        return expected
    # Keep the lookup strict: never silently choose a similarly named product.
    raise FileNotFoundError(f"Product artifact missing: sarguardian-granule-{product_id}")


def aggregate_stats(
    manifest: dict[str, Any],
    artifact_root: Path,
    science_root: Path,
    out_root: Path,
    report: dict[str, Any],
) -> None:
    outputs = science_root / "outputs"
    errors: list[dict[str, Any]] = report["errors"]
    product_meta: dict[str, tuple[dict[str, Any], Path]] = {}
    rows_by_type: dict[str, list[dict[str, str]]] = {"GUNW": [], "GOFF": []}
    baseline_fields: dict[str, list[str]] = {}
    baseline_rows: dict[str, list[dict[str, str]]] = {}
    for family in ("GUNW", "GOFF"):
        stats_name = f"{family.lower()}_stats_source.csv"
        baseline_fields[family], baseline_rows[family] = read_csv(outputs / stats_name)

    seen_ids: set[str] = set()
    for product in manifest["products"]:
        pid = str(product["id"])
        if pid in seen_ids:
            errors.append({"problem": "duplicate_manifest_id", "id": pid})
            continue
        seen_ids.add(pid)
        try:
            artifact_dir = locate_product_artifact(artifact_root, pid)
            meta_path = artifact_dir / "product-processing.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for key, want in (
                ("id", pid),
                ("granule_name", product["granule_name"]),
                ("product_type", product["product_type"]),
                ("maturity", product["maturity"]),
                ("aoi", "source"),
                ("science_commit", manifest["science_commit"]),
                ("retention_profile", "full-lossless"),
            ):
                if meta.get(key) != want:
                    errors.append({"problem": "product_metadata_mismatch", "id": pid,
                                   "field": key, "expected": want, "actual": meta.get(key)})
            eq = meta.get("reader_equivalence_status")
            if eq not in {"PASS", "PASS_NO_VALID_AOI_PIXELS"}:
                errors.append({"problem": "reader_equivalence_not_pass", "id": pid, "actual": eq})
            if not meta.get("drive_remote_verification") == "PASS":
                errors.append({"problem": "remote_archive_not_verified", "id": pid})
            stats_rel = str(meta["stats_csv"])
            stats_path = safe_relative(artifact_dir, stats_rel)
            _, rows = read_csv(stats_path)
            if not rows:
                errors.append({"problem": "empty_reader_csv", "id": pid, "path": stats_rel})
            if not any((r.get("file") or "").strip() == product["granule_name"] for r in rows):
                errors.append({"problem": "reader_csv_wrong_granule", "id": pid,
                               "expected_file": product["granule_name"],
                               "actual_files": [r.get("file") for r in rows]})
            if meta["product_type"] == "GUNW" and len(rows) != 1:
                errors.append({"problem": "unexpected_gunw_row_count", "id": pid, "count": len(rows)})
            if meta["product_type"] == "GOFF" and (len(rows) != 1 or "layer" not in rows[0] or "layer2" not in rows[0]["layer"]):
                errors.append({"problem": "goff_not_single_layer2_row", "id": pid, "rows": len(rows),
                               "layers": [r.get("layer") for r in rows]})
            rows_by_type[meta["product_type"]].extend(rows)
            product_meta[pid] = (meta, artifact_dir)
        except Exception as exc:
            errors.append({"problem": "product_artifact_read_failed", "id": pid,
                           "type": type(exc).__name__, "detail": str(exc)[:240]})

    # Write canonical aggregate CSVs in the original batch baseline order.
    # Full profile must reproduce every row; pilot profile compares its subset only.
    for family in ("GUNW", "GOFF"):
        fields = baseline_fields[family]
        streamed = rows_by_type[family]
        available = {row_key(r, fields): r for r in streamed}
        expected_rows_all = baseline_rows[family]
        expected_products = {p["granule_name"] for p in manifest["products"] if p["product_type"] == family}
        expected_rows = [r for r in expected_rows_all if r.get("file") in expected_products]
        if manifest["run_profile"] == "full-source-baseline" and len(expected_products) != len({
            r.get("file") for r in expected_rows_all
        }):
            errors.append({"problem": "manifest_product_count_does_not_cover_baseline",
                           "family": family, "manifest_products": len(expected_products),
                           "baseline_products": len({r.get("file") for r in expected_rows_all})})
        canonical_rows = [available[row_key(r, fields)] for r in expected_rows if row_key(r, fields) in available]
        out_path = outputs / f"{family.lower()}_stats_source.csv"
        write_csv(out_path, fields, canonical_rows)
        result = compare_rows(expected_rows, streamed, fields,
                              label=f"outputs/{family.lower()}_stats_source.csv", errors=errors)
        report["comparisons"].append(result)

    # Reassemble the small, AOI-clipped geotiffs into the paths used by the
    # original downstream scripts. Only metadata-listed, root-contained files
    # from successfully validated per-granule artifacts are accepted.
    copied_exports = {"GUNW": [], "GOFF": []}
    for product in manifest["products"]:
        item = product_meta.get(str(product["id"]))
        if not item:
            continue
        meta, artifact_dir = item
        family = str(meta["product_type"])
        export_rel_dir = str(meta.get("export_dir", ""))
        if family == "GUNW":
            destination = outputs / "export_src"
        else:
            destination = outputs / "export_goff_src"
        for rel in meta.get("export_files", []):
            try:
                src = safe_relative(artifact_dir, str(rel))
                if not src.is_file() or src.suffix.lower() not in {".tif", ".tiff"}:
                    raise ValueError(f"Listed export missing or not a TIFF: {rel}")
                target = destination / src.name
                if target.exists():
                    errors.append({"problem": "duplicate_export_filename", "file": src.name})
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
                copied_exports[family].append(target.name)
            except Exception as exc:
                errors.append({"problem": "export_copy_failed", "id": product["id"],
                               "path": str(rel), "detail": str(exc)[:200]})
    report["derived_exports"] = {k: len(v) for k, v in copied_exports.items()}


def compare_output_file(path: Path, baseline_path: Path, report: dict[str, Any]) -> None:
    if not baseline_path.is_file():
        report["comparisons"].append({"table": str(path.name), "status": "SKIP_NO_COMMITTED_BASELINE"})
        return
    try:
        fields, actual = read_csv(path)
        baseline_fields, baseline = read_csv(baseline_path)
        if fields != baseline_fields:
            # DictWriter order can differ, but schema equality is required, not order.
            if set(fields) != set(baseline_fields):
                report["errors"].append({"problem": "downstream_schema_mismatch", "file": path.name,
                                         "baseline_fields": baseline_fields, "actual_fields": fields})
                report["comparisons"].append({"table": path.name, "status": "FAIL_SCHEMA"})
                return
            fields = baseline_fields
        report["comparisons"].append(compare_rows(
            baseline, actual, fields, label=f"outputs/{path.name}", errors=report["errors"]
        ))
    except Exception as exc:
        report["errors"].append({"problem": "downstream_compare_failed", "file": path.name,
                                 "type": type(exc).__name__, "detail": str(exc)[:240]})
        report["comparisons"].append({"table": path.name, "status": "FAIL_COMPARE"})


def run_downstream(science_root: Path, out_root: Path, report: dict[str, Any]) -> None:
    """Recreate the documented source-AOI summary and bound chain from compact data."""
    outputs = science_root / "outputs"
    commands: list[tuple[str, list[str]]] = [
        ("GOFF summary time series", [
            sys.executable, "src/timeseries.py", "--from-stats", "outputs/goff_stats_source.csv",
            "--product", "GOFF", "--goff-layer", "layer2", "--aoi", "source", "--invert",
            "--auto-ref", "--jackknife", "--csv", "outputs/ts_goff_source.csv",
        ]),
        ("GUNW summary time series", [
            sys.executable, "src/timeseries.py", "--from-stats", "outputs/gunw_stats_source.csv",
            "--product", "GUNW", "--aoi", "source", "--invert", "--auto-ref", "--jackknife",
            "--csv", "outputs/ts_gunw_source.csv",
        ]),
    ]
    for label, argv in commands:
        done = subprocess.run(argv, cwd=science_root, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=False)
        log_path = out_root / "logs" / (label.lower().replace(" ", "_") + ".log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(done.stdout, encoding="utf-8")
        report["commands"].append({"name": label, "argv": argv[1:], "exit_code": done.returncode,
                                   "log": str(log_path.relative_to(out_root))})
        if done.returncode:
            report["errors"].append({"problem": "downstream_command_failed", "name": label,
                                     "exit_code": done.returncode, "log_tail": done.stdout[-1200:]})
            return

    # Keep the pre-event cutoff explicit to prevent the event and post-event
    # observations from leaking into an alleged warning-time estimate.
    argv = [
        sys.executable, "src/inverse_velocity.py", "--ts", "outputs/ts_goff_source.csv",
        "--floors", "outputs/goff_stats_source.csv", "--floors-layer", "layer2",
        "--noise-floor", "18.6", "--event-date", "2026-08-26",
    ]
    done = subprocess.run(argv, cwd=science_root, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)
    log_path = out_root / "logs" / "inverse_velocity_source.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(done.stdout, encoding="utf-8")
    report["commands"].append({"name": "inverse_velocity pre-event cutoff", "argv": argv[1:],
                               "exit_code": done.returncode, "log": str(log_path.relative_to(out_root))})
    if done.returncode:
        report["errors"].append({"problem": "downstream_command_failed", "name": "inverse_velocity",
                                 "exit_code": done.returncode, "log_tail": done.stdout[-1200:]})
        return
    if "2026-08-26" not in done.stdout or "dropped" not in done.stdout.lower():
        report["errors"].append({"problem": "event_cutoff_diagnostic_missing",
                                 "log_tail": done.stdout[-1200:]})

    # These are the exact input dates/exclusions documented for Result 7.
    local_floor_commands = [
        [
            sys.executable, "src/local_floor.py", "--dir", "outputs/export_goff_src",
            "--match", "layer2", "--targets", "outputs/scar_candidates_source.csv",
            "--reading", "DETACHMENT-like", "--radius", "6", "--exclude", "20260828", "_UR_",
            "--include", "20251128", "20251210", "20251222", "20260103", "20260702",
            "20260714", "20260726", "20260819", "--csv", "outputs/local_floor_candidates.csv",
        ],
        [
            sys.executable, "src/local_floor.py", "--dir", "outputs/export_src", "--band", "1",
            "--targets", "outputs/scar_candidates_source.csv", "--reading", "DETACHMENT-like",
            "--radius", "6", "--exclude", "_UR_", "--include", "20251128", "20251210",
            "20251222", "20260103", "20260620", "20260702", "20260714", "20260726",
            "--csv", "outputs/local_floor_phase_candidates.csv",
        ],
        [
            sys.executable, "src/common_ref.py", "--dir", "outputs/export_goff_src",
            "--match", "layer2", "--include", "20260702", "20260714", "20260726",
            "--exclude", "_UR_", "--targets", "outputs/scar_candidates_source.csv",
            "--reading", "DETACHMENT-like", "--csv", "outputs/common_ref_summer.csv",
        ],
        [sys.executable, "src/bound.py"],
    ]
    labels = ["GOFF candidate floors", "GUNW candidate floors", "GOFF summer common reference", "final bound"]
    for label, argv in zip(labels, local_floor_commands):
        done = subprocess.run(argv, cwd=science_root, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=False)
        log_path = out_root / "logs" / (label.lower().replace(" ", "_") + ".log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(done.stdout, encoding="utf-8")
        report["commands"].append({"name": label, "argv": argv[1:], "exit_code": done.returncode,
                                   "log": str(log_path.relative_to(out_root))})
        if done.returncode:
            report["errors"].append({"problem": "downstream_command_failed", "name": label,
                                     "exit_code": done.returncode, "log_tail": done.stdout[-1200:]})
            return

    # Compare regenerated key outputs with the pinned repository's committed baselines.
    baseline_dir = out_root / "baseline-snapshot"
    for filename in BASELINE_DOWNSTREAM:
        baseline = baseline_dir / filename
        compare_output_file(outputs / filename, baseline, report)


def zip_run_bundle(out_root: Path, science_root: Path, manifest_path: Path) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle = out_root / f"sarguardian-{manifest.get('run_id', 'run')}-results.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        if manifest.get("run_profile") == "validation-pilot":
            # A pilot package must not silently bundle stale, committed analyses
            # and make them look like the result of a two-granule test.
            out = science_root / "outputs"
            for rel in (
                "gunw_stats_source.csv", "goff_stats_source.csv",
                "export_src", "export_goff_src",
            ):
                path = out / rel
                if path.is_file():
                    z.write(path, f"outputs/{rel}")
                elif path.is_dir():
                    for item in sorted(path.rglob("*")):
                        if item.is_file() and item.suffix.lower() in {".tif", ".tiff"}:
                            z.write(item, f"outputs/{rel}/{item.relative_to(path).as_posix()}")
        else:
            folder = science_root / "outputs"
            for path in sorted(folder.rglob("*")):
                if path.is_file() and path.suffix.lower() not in {".h5", ".hdf5"}:
                    z.write(path, f"outputs/{path.relative_to(folder).as_posix()}")
        logs = out_root / "logs"
        if logs.exists():
            for path in sorted(logs.rglob("*")):
                if path.is_file():
                    z.write(path, f"logs/{path.relative_to(logs).as_posix()}")
        z.write(manifest_path, "run-manifest.json")
        report_path = out_root / "batch-equivalence-report.json"
        if report_path.exists():
            z.write(report_path, "batch-equivalence-report.json")
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--science-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--out-root", required=True, type=Path)
    args = parser.parse_args()
    science_root, manifest_path = args.science_root.resolve(), args.manifest.resolve()
    artifact_root, out_root = args.artifact_root.resolve(), args.out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("aoi") != "source":
        raise SystemExit("ERROR=UNEXPECTED_AOI; expected the pinned source AOI")
    if manifest.get("science_commit") != "77cc9646cfa46d3aff3669d351912f984cf67aa3":
        raise SystemExit("ERROR=UNEXPECTED_SCIENCE_COMMIT")

    outputs = science_root / "outputs"
    baseline_dir = out_root / "baseline-snapshot"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    for filename in BASELINE_DOWNSTREAM:
        src = outputs / filename
        if src.exists():
            shutil.copy2(src, baseline_dir / filename)

    report: dict[str, Any] = {
        "schema_version": "sarguardian-streaming-batch-equivalence/1.0",
        "run_id": manifest.get("run_id"),
        "run_profile": manifest.get("run_profile"),
        "aoi": "source",
        "science_commit": manifest.get("science_commit"),
        "products_expected": len(manifest.get("products", [])),
        "products_validated": 0,
        "comparisons": [],
        "commands": [],
        "errors": [],
        "archive_policy": "full-lossless",
        "raw_delete_policy": "a raw runner copy is removed only after the full-lossless archive, all derived files, and remote checksums have passed; the remote full-lossless HDF5 and provenance are retained",
    }
    aggregate_stats(manifest, artifact_root, science_root, out_root, report)
    report["products_validated"] = len({
        str(p["id"]) for p in manifest["products"]
        if (artifact_root / f"sarguardian-granule-{p['id']}" / "product-processing.json").is_file()
    })

    table_failures = [c for c in report["comparisons"] if c.get("status") != "PASS"]
    # The per-product batch equivalence gate is mandatory for both profiles.
    if not report["errors"] and not table_failures:
        if manifest.get("run_profile") == "full-source-baseline":
            run_downstream(science_root, out_root, report)
    downstream_failures = [c for c in report["comparisons"] if c.get("status") not in {"PASS", "SKIP_NO_COMMITTED_BASELINE"}]
    report["status"] = "PASS" if not report["errors"] and not downstream_failures and not table_failures else "FAIL"
    report["finished_utc"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    report_path = out_root / "batch-equivalence-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    bundle = zip_run_bundle(out_root, science_root, manifest_path)
    report["bundle_file"] = bundle.name
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Refresh bundle with the completed report including its name.
    bundle.unlink(missing_ok=True)
    bundle = zip_run_bundle(out_root, science_root, manifest_path)
    print(f"BATCH_EQUIVALENCE_STATUS={report['status']}")
    print(f"PRODUCTS_VALIDATED={report['products_validated']}/{report['products_expected']}")
    print(f"COMPARISONS={len(report['comparisons'])}")
    print(f"REPORT_PATH={report_path}")
    print(f"BUNDLE_PATH={bundle}")
    if report["status"] != "PASS":
        print("ERROR=BATCH_EQUIVALENCE_FAILED", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
