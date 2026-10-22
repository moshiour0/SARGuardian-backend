#!/usr/bin/env python3
"""Discover exact-AOI NISAR L2 GUNW/GOFF products by ASF catalog and date window.

The ASF catalog is queried against the requested polygon; returned granules are
then filtered by the secondary acquisition date embedded in the granule ID.
The source-AOI committed CSVs are deliberately not used as an inventory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

ASF_API = "https://api.daac.asf.alaska.edu/services/search/param"
SCIENCE_COMMIT = "39e5a4991fe7bdb0f7a3ae41e5f38c1ba5dc53eb"
MAX_PRODUCTS = 200
MAX_RESULTS = 2000
PRODUCT_PATTERN = re.compile(
    r"^NISAR_L2_(?:(?:PR|UR|OD)_)?(GUNW|GOFF)_[A-Za-z0-9_.-]{10,250}$"
)
STAMP_PATTERN = re.compile(r"_(\d{8})T\d{6}")

def parse_date(value: str, name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{name}_MUST_BE_YYYY_MM_DD") from None

def product_dates(name: str) -> tuple[date, date] | None:
    stamps = STAMP_PATTERN.findall(name)
    if len(stamps) < 4:
        return None
    try:
        return (
            datetime.strptime(stamps[0], "%Y%m%d").date(),
            datetime.strptime(stamps[2], "%Y%m%d").date(),
        )
    except ValueError:
        return None

def query_asf_polygon(wkt: str, family: str, end_date: date,
                      *, session: requests.Session | None = None) -> list[dict[str, Any]]:
    client = session or requests.Session()
    params = {
        "intersectsWith": wkt,
        "output": "json",
        "maxResults": str(MAX_RESULTS),
        "dataset": "NISAR",
        "platform": "NISAR",
        "processingLevel": family,
        "shortName": f"NISAR_L2_{family}_V1",
        "start": "2024-01-01T00:00:00Z",
        "end": f"{end_date.isoformat()}T23:59:59Z",
    }
    last_error = None
    for attempt in range(1, 4):
        try:
            # POST avoids URL-size failures for detailed AOI polygons; ASF supports
            # POST requests for the intersectsWith query parameter.
            response = client.post(ASF_API, data=params, timeout=(30, 180))
            if response.status_code in {408, 425, 429, 500, 502, 503, 504} and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                raw = payload.get("results")
                if raw is None:
                    raw = payload.get("features")
                if raw is None and payload.get("type") == "FeatureCollection":
                    raw = payload.get("features")
                if raw is None:
                    raw = []
            elif isinstance(payload, list):
                raw = payload
            else:
                raise ValueError("ASF_RESPONSE_ROOT_INVALID")
            if not isinstance(raw, list):
                raise ValueError("ASF_RESULTS_NOT_A_LIST")
            # GeoJSON-style outputs nest metadata in properties. Normalize those
            # records once so field extraction supports both flat JSON and GeoJSON.
            normalized = []
            for record in raw:
                if not isinstance(record, dict):
                    continue
                props = record.get("properties")
                normalized.append({**record, **props} if isinstance(props, dict) else record)
            raw = normalized
            if len(raw) >= MAX_RESULTS:
                raise RuntimeError(
                    f"ASF_CATALOG_RESULT_CAP_REACHED family={family} limit={MAX_RESULTS}; "
                    "discovery is incomplete, so the run has been stopped"
                )
            return [row for row in raw if isinstance(row, dict)]
        except (requests.RequestException, ValueError) as exc:
            # Keep response bodies, URLs, credentials and long payloads out of logs.
            last_error = f"{type(exc).__name__}:{getattr(exc, 'response', None).status_code if getattr(exc, 'response', None) is not None else 'no-http-status'}"
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"ASF_CATALOG_QUERY_FAILED family={family} diagnostics={last_error}")

def record_name(row: dict[str, Any]) -> str:
    fields = {str(key).lower().replace("_", ""): value for key, value in row.items()}
    value = (fields.get("granulename") or fields.get("filename") or
             fields.get("scenename") or fields.get("productname") or
             fields.get("fileid") or fields.get("productfileid") or "")
    name = Path(str(value).strip()).name
    return name[:-3] if name.lower().endswith(".h5") else name

def product_size_bytes(row: dict[str, Any], family: str) -> int:
    for key in ("bytes", "sizeBytes", "fileSize"):
        value = row.get(key)
        try:
            n = int(float(value))
            if n > 0:
                return n
        except (TypeError, ValueError, OverflowError):
            pass
    value = row.get("sizeMB") or row.get("sizeMb")
    try:
        n = int(float(value) * 1024 * 1024)
        if n > 0:
            return n
    except (TypeError, ValueError, OverflowError):
        pass
    # Conservative operational planning defaults; actual transfer size is checked later.
    return 2_400_000_000 if family == "GUNW" else 1_000_000_000

def discover(args: argparse.Namespace) -> dict[str, Any]:
    start = parse_date(args.start_date, "START_DATE")
    end = parse_date(args.end_date, "END_DATE")
    if start > end:
        raise ValueError("START_DATE_MUST_NOT_EXCEED_END_DATE")
    wkt = os.environ.get("SARGUARDIAN_AOI_WKT", "").strip()
    if not wkt:
        raise ValueError("SARGUARDIAN_AOI_WKT_REQUIRED")
    science_src = args.science_root.resolve() / "src"
    sys.path.insert(0, str(science_src))
    try:
        engine = importlib.import_module("gunw_reader")
        from aoi_wkt import parse_polygon_wkt
        ring = parse_polygon_wkt(wkt)
        # Canonical closure/order and precision are deterministic. The exact polygon,
        # never its bounding box, is passed to ASF.
        canonical_wkt = "POLYGON ((" + ", ".join(f"{x:.17g} {y:.17g}" for x, y in ring) + "))"
        engine.set_aoi("custom")
        maturity_for_name = engine.product_maturity
    except Exception as exc:
        raise ValueError(f"AOI_OR_SCIENCE_ENGINE_INITIALIZATION_FAILED:{type(exc).__name__}:{str(exc)[:180]}") from None

    all_rows: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, str]] = []
    query_summary: dict[str, Any] = {}
    with requests.Session() as session:
        for family in ("GUNW", "GOFF"):
            rows = query_asf_polygon(canonical_wkt, family, end, session=session)
            accepted = 0
            for row in rows:
                name = record_name(row)
                match = PRODUCT_PATTERN.fullmatch(name)
                if not match or match.group(1) != family:
                    continue
                dates = product_dates(name)
                if not dates:
                    excluded.append({"granule_name": name, "reason": "UNPARSEABLE_PAIR_DATES"})
                    continue
                reference, secondary = dates
                if secondary < start or secondary > end:
                    continue
                maturity = str(row.get("dataMaturity") or row.get("maturity") or "").strip().upper()
                if maturity not in {"BETA", "PROVISIONAL"}:
                    maturity = maturity_for_name(name)
                if maturity not in {"BETA", "PROVISIONAL"}:
                    excluded.append({"granule_name": name, "reason": "MATURITY_UNKNOWN_OR_UNSUPPORTED"})
                    continue
                previous = all_rows.get(name)
                record = {
                    "product_type": family,
                    "granule_name": name,
                    "maturity": maturity,
                    "reference_date": reference.isoformat(),
                    "secondary_date": secondary.isoformat(),
                    "expected_source_bytes": product_size_bytes(row, family),
                    "asf_catalog_product_type": row.get("productType"),
                    "discovery_source": "ASF_search_API_intersectsWith_exact_polygon",
                }
                if previous and previous != record:
                    raise RuntimeError(f"ASF_DUPLICATE_PRODUCT_METADATA_CONFLICT granule={name}")
                all_rows[name] = record
                accepted += 1
            query_summary[family] = {
                "catalog_rows_returned": len(rows),
                "products_in_secondary_date_window": accepted,
            }

    inventory = sorted(all_rows.values(), key=lambda r: (r["secondary_date"], r["product_type"], r["granule_name"]))
    if not inventory:
        raise ValueError("NO_SUPPORTED_NISAR_PRODUCTS_INTERSECT_THE_AOI_AND_SECONDARY_DATE_WINDOW")
    if args.run_profile == "validation-pilot":
        selected = []
        for family in ("GUNW", "GOFF"):
            candidates = [x for x in inventory if x["product_type"] == family]
            if not candidates:
                raise ValueError(f"VALIDATION_PILOT_REQUIRES_BOTH_GUNW_AND_GOFF_FOUND={family}_MISSING")
            # Deterministically choose the newest secondary date within each family.
            selected.append(max(candidates, key=lambda r: (r["secondary_date"], r["granule_name"])))
    elif args.run_profile == "full-aoi-baseline":
        selected = inventory
    else:
        raise ValueError("RUN_PROFILE_INVALID")
    if len(selected) > MAX_PRODUCTS:
        raise ValueError(f"PRODUCT_LIMIT_EXCEEDED count={len(selected)} max={MAX_PRODUCTS}; narrow AOI/date window")
    selected.sort(key=lambda r: (r["secondary_date"], r["product_type"], r["granule_name"]))
    for index, row in enumerate(selected, 1):
        row["id"] = f'{row["product_type"]}-{index:03d}'
    wkt_hash = hashlib.sha256(canonical_wkt.encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": "sarguardian-aoi-run-manifest/1.0",
        "run_id": f"{os.environ.get('GITHUB_RUN_ID', 'local')}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}",
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "workflow_sha": os.environ.get("GITHUB_SHA"),
        "run_profile": args.run_profile,
        "requested_run_profile": args.run_profile,
        "aoi_name": "custom",
        "aoi_wkt": canonical_wkt,
        "aoi_crs": "EPSG:4326",
        "aoi_wkt_sha256": wkt_hash,
        "science_commit": SCIENCE_COMMIT,
        "time_window": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "date_basis": "secondary_acquisition_date_from_granule_identifier",
            "inclusive": True,
            "inventory_products_in_window": len(inventory),
            "selected_products": len(selected),
            "catalog_search_start": "2024-01-01",
        },
        "catalog_query": {
            "service": "ASF DAAC Search API",
            "intersects_semantics": "exact supplied WKT polygon; no bbox substitution",
            "families": query_summary,
            "excluded_products": excluded,
            "results_truncated": False,
        },
        "baseline_policy": {
            "committed_source_aoi_csv_comparison": False,
            "reason": "A user-defined AOI has different pixel support and statistics; comparing it to source-AOI numeric baselines would be invalid.",
        },
        "baseline_product_counts": {fam: sum(r["product_type"] == fam for r in inventory) for fam in ("GUNW", "GOFF")},
        "products": selected,
        "products_to_process": selected,
        "retention_profile": args.retention_profile,
        "archive_profile": args.retention_profile,
        "archive_note": ("Keep source HDF5 datasets in a lossless archive plus derived outputs."
                         if args.retention_profile == "full-lossless"
                         else "Keep validated derived outputs and provenance; delete worker raw HDF5 only after verified remote storage."),
        "scientific_claim_limit": "Processing and internal structural checks do not constitute independent geophysical validation.",
    }
    return manifest

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--science-root", required=True, type=Path)
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--run-profile", required=True, choices=("validation-pilot", "full-aoi-baseline"))
    p.add_argument("--retention-profile", required=True, choices=("derived-only", "full-lossless"))
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    try:
        manifest = discover(a)
    except Exception as exc:
        print(f"ERROR={type(exc).__name__}:{str(exc)[:500]}", file=sys.stderr)
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    matrix = [
        {k: row[k] for k in ("id", "granule_name", "product_type", "maturity", "expected_source_bytes")}
        for row in manifest["products"]
    ]
    compact = json.dumps(matrix, separators=(",", ":"))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("matrix=" + compact + "\n")
        output.write(f"product_count={len(matrix)}\n")
        output.write(f"aoi_wkt_sha256={manifest['aoi_wkt_sha256']}\n")
        output.write(f"run_profile={manifest['run_profile']}\n")
    print(f"AOI_WKT_SHA256={manifest['aoi_wkt_sha256']}")
    print(f"AOI_DISCOVERY_INVENTORY={manifest['time_window']['inventory_products_in_window']}")
    print(f"AOI_PRODUCTS_SELECTED={len(matrix)}")
    print(f"AOI_BASELINE_GUNW={manifest['baseline_product_counts']['GUNW']}")
    print(f"AOI_BASELINE_GOFF={manifest['baseline_product_counts']['GOFF']}")
    print("AOI_DISCOVERY_TRUNCATED=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
