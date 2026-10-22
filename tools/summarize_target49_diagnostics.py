#!/usr/bin/env python3
"""Validate and index a completed Target 4/9 raw-HDF5 diagnostic artifact.

No raw HDF5 is read or retained here. The inputs are per-product download
manifests and read-only JSON diagnostics produced while each raw file existed
on the ephemeral Actions runner. The script exits non-zero if any expected
product/report is missing or the identity/checksum/size differs.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "target49_products.tsv"
BASE_AOIS = ("source", "langtang")
GUNW_MODES = ("source_no_iono_gate", "langtang_no_iono_gate")


def read_products(path: Path) -> list[dict[str, str]]:
    products = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) != 4:
            raise ValueError(f"Invalid target49 product manifest row: {raw!r}")
        product_type, maturity, label, granule = fields
        if product_type not in {"GUNW", "GOFF"} or maturity not in {"BETA", "PROVISIONAL"}:
            raise ValueError(f"Unsupported product manifest value: {raw!r}")
        if Path(granule).name != granule or not granule.endswith(".h5"):
            raise ValueError(f"Granule must be an exact HDF5 basename: {granule!r}")
        products.append({"product_type": product_type, "maturity": maturity,
                         "label": label, "granule": granule})
    if not products:
        raise ValueError(f"No products found in {path}")
    labels = [p["label"] for p in products]
    granules = [p["granule"] for p in products]
    if len(labels) != len(set(labels)) or len(granules) != len(set(granules)):
        raise ValueError("Duplicate labels or granule basenames in product manifest.")
    return products


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def count_targets(item: dict[str, Any]) -> int:
    count = 0
    if isinstance(item.get("targets"), dict):
        count += len(item["targets"])
    for layer in item.get("layers", []):
        if isinstance(layer.get("targets"), dict):
            count += len(layer["targets"])
    return count


def flatten_report(report: dict[str, Any], path: Path, label: str,
                   expected: dict[str, str], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    report_errors = report.get("errors") or []
    if report_errors:
        raise ValueError(f"{path.name} reports diagnostic errors: {report_errors}")
    results = report.get("results")
    if not isinstance(results, list) or len(results) != 1:
        raise ValueError(f"{path.name} must contain exactly one product result.")
    item = results[0]
    expected_name = expected["granule"]
    actual_name = Path(str(item.get("file", ""))).name
    if actual_name != expected_name:
        raise ValueError(f"{path.name}: expected product {expected_name}, got {actual_name}")
    sha = str(item.get("sha256", "")).lower()
    expected_sha = str(manifest.get("source_sha256", "")).lower()
    if len(sha) != 64 or sha != expected_sha:
        raise ValueError(f"{path.name}: report SHA-256 does not match download manifest.")
    try:
        actual_bytes = int(item.get("bytes"))
        expected_bytes = int(manifest.get("source_bytes"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{path.name}: missing or invalid byte count.") from exc
    if actual_bytes != expected_bytes or actual_bytes <= 0:
        raise ValueError(f"{path.name}: report bytes do not match manifest.")
    target_count = count_targets(item)
    if target_count == 0:
        raise ValueError(f"{path.name}: no target windows were reported.")

    common = {
        "product_label": label,
        "product": expected_name,
        "type": expected["product_type"],
        "maturity_requested": expected["maturity"],
        "crid": item.get("crid") or "",
        "sha256": sha,
        "bytes": actual_bytes,
        "diagnostic_file": path.name,
        "aoi": report.get("aoi", ""),
        "mode": path.stem.rsplit("__", 1)[-1],
        "phase_dataset": item.get("phase_dataset", ""),
        "coherence_dataset": item.get("coherence_dataset", ""),
        "components_dataset": item.get("components_dataset", ""),
        "mask_dataset": item.get("mask_dataset", ""),
        "mask_dtype": item.get("mask_dtype", ""),
        "epsg": item.get("epsg", ""),
        "shape": json.dumps(item.get("shape", ""), separators=(",", ":")),
        "global_stage_counts": json.dumps(item.get("global_stage_counts", {}), sort_keys=True),
        "global_raw_mask_histogram": json.dumps(item.get("global_raw_mask_histogram", {}), sort_keys=True),
        "warnings": " | ".join(str(x) for x in report.get("warnings", [])),
    }
    rows: list[dict[str, Any]] = []

    def local_row(target_id: str, target: dict[str, Any], layer: dict[str, Any] | None = None) -> None:
        rows.append({
            **common,
            "layer": (layer or {}).get("group", ""),
            "target": str(target_id),
            "inside_grid_extent": target.get("inside_grid_extent", ""),
            "inside_requested_aoi_polygon": target.get("inside_requested_aoi_polygon", ""),
            "nearest_grid_cell_distance_m": target.get("nearest_grid_cell_distance_m", ""),
            "window_cell_count": target.get("window_cell_count", ""),
            "cumulative_stage_counts": json.dumps(target.get("cumulative_stage_counts", {}), sort_keys=True),
            "raw_mask_value_histogram": json.dumps(target.get("raw_mask_value_histogram", {}), sort_keys=True),
        })

    if isinstance(item.get("targets"), dict):
        for target_id, target in sorted(item["targets"].items(), key=lambda p: str(p[0])):
            local_row(target_id, target)
    for layer in item.get("layers", []):
        for target_id, target in sorted(layer.get("targets", {}).items(), key=lambda p: str(p[0])):
            local_row(target_id, target, layer)

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True,
                        help="folder with diagnostics/ and download_manifests/")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help="authoritative product list (defaults to sibling TSV)")
    parser.add_argument("--expected-products", type=int, default=None,
                        help="optional assertion for expected product count")
    args = parser.parse_args()

    root = args.root.resolve()
    manifest_path = args.manifest.resolve()
    diagnostics_dir = root / "diagnostics"
    downloads_dir = root / "download_manifests"
    products = read_products(manifest_path)
    if args.expected_products is not None and len(products) != args.expected_products:
        raise SystemExit(f"Expected manifest to contain {args.expected_products} products; found {len(products)}.")

    all_rows: list[dict[str, Any]] = []
    errors = []
    total_bytes = 0
    checked_reports = 0

    for product in products:
        label = product["label"]
        granule = product["granule"]
        manifest_file = downloads_dir / f"{label}.json"
        if not manifest_file.is_file():
            errors.append(f"Missing download manifest: {manifest_file.name}")
            continue
        try:
            download = read_json(manifest_file)
            if Path(str(download.get("source_filename", ""))).name != granule:
                raise ValueError(f"{manifest_file.name}: source_filename does not match manifest TSV.")
            if download.get("product_type") != product["product_type"]:
                raise ValueError(f"{manifest_file.name}: product_type mismatch.")
            if download.get("maturity_requested") != product["maturity"]:
                raise ValueError(f"{manifest_file.name}: maturity mismatch.")
            if download.get("source_deleted") is not False:
                raise ValueError(f"{manifest_file.name}: unexpected source deletion state.")
            source_bytes = int(download.get("source_bytes"))
            source_sha = str(download.get("source_sha256", "")).lower()
            if source_bytes <= 0 or len(source_sha) != 64:
                raise ValueError(f"{manifest_file.name}: invalid byte count or SHA-256.")
            total_bytes += source_bytes
        except (OSError, ValueError, TypeError, OverflowError) as exc:
            errors.append(str(exc))
            continue

        modes = list(BASE_AOIS) + (list(GUNW_MODES) if product["product_type"] == "GUNW" else [])
        for mode in modes:
            report_path = diagnostics_dir / f"{label}__{mode}.json"
            if not report_path.is_file():
                errors.append(f"Missing diagnostic report: {report_path.name}")
                continue
            try:
                report = read_json(report_path)
                if report.get("aoi") != ("langtang" if mode.startswith("langtang") else "source"):
                    raise ValueError(f"{report_path.name}: AOI metadata does not match filename/mode.")
                rows = flatten_report(report, report_path, label, product, download)
                targets = {row["target"] for row in rows}
                if targets != {"4", "9"}:
                    raise ValueError(f"{report_path.name}: expected Target 4 and Target 9 rows; found {sorted(targets)}.")
                all_rows.extend(rows)
                checked_reports += 1
            except (OSError, ValueError, TypeError, KeyError) as exc:
                errors.append(str(exc))

    expected_reports = sum(4 if p["product_type"] == "GUNW" else 2 for p in products)
    expected_labels = {p["label"] for p in products}
    seen_labels = {str(row["product_label"]) for row in all_rows}
    expected_rows = sum(8 if p["product_type"] == "GUNW" else 12 for p in products)
    if checked_reports != expected_reports:
        errors.append(f"Expected {expected_reports} diagnostic reports, validated {checked_reports}.")
    if seen_labels != expected_labels:
        errors.append(f"Product coverage mismatch: expected {sorted(expected_labels)}, saw {sorted(seen_labels)}.")
    if len(all_rows) != expected_rows:
        errors.append(f"Expected {expected_rows} target/layer rows, produced {len(all_rows)}.")

    if all_rows:
        fields = sorted({field for row in all_rows for field in row})
        csv_path = root / "target4_9_summary.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(all_rows)

    status = {
        "status": "completed" if not errors else "failed_validation",
        "source_run": "SARGuardian-backend Run #55 / 39657764262",
        "science_manifest": manifest_path.name,
        "raw_hdf5_retained": False,
        "expected_products": len(products),
        "products_with_verified_download_and_diagnostics": len(seen_labels),
        "downloaded_source_bytes_total": total_bytes,
        "downloaded_source_gib_total": round(total_bytes / (1024 ** 3), 3),
        "diagnostic_reports_expected": expected_reports,
        "diagnostic_reports_validated": checked_reports,
        "target_layer_rows_expected": expected_rows,
        "target_layer_rows_written": len(all_rows),
        "errors": errors,
        "notes": [
            "Download identity, size and SHA-256 are checked against every diagnostic JSON.",
            "An execution pass validates tooling and evidence integrity, not geophysical truth.",
            "Raw HDF5 is never copied into the artifact; only manifests and summaries are retained."
        ],
    }
    (root / "diagnostic_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "TARGET49_DIAGNOSTIC_SUMMARY "
        f"status={status['status']} products={len(seen_labels)}/{len(products)} "
        f"reports={checked_reports}/{expected_reports} "
        f"rows={len(all_rows)}/{expected_rows} errors={len(errors)}"
    )
    if errors:
        for error in errors:
            print(f"VALIDATION_ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
