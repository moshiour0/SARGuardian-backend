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
    """Query ASF with documented NISAR dataset/product-level filters.

    ASF Search documents dataset and processingLevel as query fields for NISAR
    and recommends GeoJSON output. A platform-based query is retained as a
    fallback for catalog deployments where dataset aliasing differs.
    """
    client = session or requests.Session()
    base = {
        "intersectsWith": wkt,
        "output": "geojson",
        "maxResults": str(MAX_RESULTS),
        "start": "2024-01-01T00:00:00Z",
        "end": f"{end_date.isoformat()}T23:59:59Z",
    }
    primary_params = {
        **base,
        "dataset": "NISAR",
        "processingLevel": family,
    }

    def execute(params: dict[str, str], strategy: str) -> list[dict[str, Any]]:
        last_error = None
        for attempt in range(1, 4):
            try:
                # GET is the same transport used by SARGuardian's acquisition
                # reconnaissance; the actual WKT polygon is never replaced by a bbox.
                response = client.get(ASF_API, params=params, timeout=(30, 180))
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
                # Some ASF responses wrap all scene records in a one-level list
                # (e.g. [[{...}, {...}]]). Flatten response containers before
                # applying record-level validation; otherwise real scenes vanish.
                flattened = []
                for item in raw:
                    if isinstance(item, list):
                        flattened.extend(item)
                    else:
                        flattened.append(item)
                raw = flattened
                # Normalize GeoJSON properties into the flat representation used below.
                normalized = []
                for record in raw:
                    if not isinstance(record, dict):
                        continue
                    props = record.get("properties")
                    normalized.append({**record, **props} if isinstance(props, dict) else record)
                if len(normalized) >= MAX_RESULTS:
                    raise RuntimeError(
                        f"ASF_CATALOG_RESULT_CAP_REACHED family={family} "
                        f"strategy={strategy} limit={MAX_RESULTS}; discovery is incomplete"
                    )
                print(
                    f"ASF_CATALOG_RESPONSE family={family} strategy={strategy} "
                    f"rows={len(normalized)} "
                    f"named_products={sum(bool(record_name(row)) for row in normalized)}"
                )
                return [row for row in normalized if isinstance(row, dict)]
            except RuntimeError:
                raise
            except (requests.RequestException, ValueError) as exc:
                status = getattr(exc, "response", None)
                last_error = f"{type(exc).__name__}:{status.status_code if status is not None else 'no-http-status'}"
                if attempt < 3:
                    time.sleep(2 ** attempt)
        raise RuntimeError(
            f"ASF_CATALOG_QUERY_FAILED family={family} strategy={strategy} diagnostics={last_error}"
        )

    rows = execute(primary_params, "dataset_processingLevel")
    if rows:
        return rows

    # Try the equivalent documented platform form only after a zero-row result.
    # Keep the AOI, time interval and product family identical during fallback.
    fallback_params = {
        **base,
        "platform": "NISAR",
        "processingLevel": family,
    }
    print(
        f"ASF_CATALOG_FALLBACK family={family} "
        "reason=dataset_processingLevel_returned_zero_rows"
    )
    return execute(fallback_params, "platform_processingLevel")
def record_name(row: dict[str, Any]) -> str:
    fields = {str(key).lower().replace("_", ""): value for key, value in row.items()}
    value = (fields.get("granulename") or fields.get("filename") or
             fields.get("scenename") or fields.get("productname") or
             fields.get("fileid") or fields.get("productfileid") or "")
    name = Path(str(value).strip()).name
    return name[:-3] if name.lower().endswith(".h5") else name

def product_size_bytes(row: dict[str, Any], family: str, granule_name: str) -> tuple[int, str]:
    """Resolve the exact HDF5 size from ASF's per-file byte map when supplied."""
    wanted = Path(granule_name).name
    if not wanted.lower().endswith(".h5"):
        wanted += ".h5"
    byte_map = row.get("bytes")
    if isinstance(byte_map, dict):
        for key, metadata in byte_map.items():
            if Path(str(key)).name.lower() != wanted.lower():
                continue
            raw = metadata.get("bytes") if isinstance(metadata, dict) else metadata
            try:
                n = int(float(raw))
                if n > 0:
                    return n, "ASF_catalog_bytes_map_exact_granule_HDF5"
            except (TypeError, ValueError, OverflowError):
                pass
    for key in ("sizeBytes", "fileSize", "granuleSizeBytes"):
        value = row.get(key)
        try:
            n = int(float(value))
            if n > 0:
                return n, f"ASF_catalog_{key}"
        except (TypeError, ValueError, OverflowError):
            pass
    value = row.get("sizeMB") or row.get("sizeMb")
    try:
        n = int(float(value) * 1024 * 1024)
        if n > 0:
            return n, "ASF_catalog_sizeMB"
    except (TypeError, ValueError, OverflowError):
        pass
    # Conservative operational estimate only when the catalog has no exact size.
    return (2_400_000_000 if family == "GUNW" else 1_000_000_000), "family_fallback_estimate"


def product_processing_type(granule_name: str) -> str:
    parts = granule_name.split("_")
    return parts[2] if len(parts) > 2 and parts[2] in {"PR", "UR", "OD"} else "UNKNOWN"


def acquisition_pair_key(granule_name: str) -> tuple[str, ...]:
    """Key pair variants by sensor, product, track/frame/mode, timestamps and CRID."""
    parts = granule_name.split("_")
    if len(parts) >= 20 and parts[2] in {"PR", "UR", "OD"}:
        # Fields before CRID identify the acquisition-pair geometry; token 2 is
        # only processing type, while suffix fields after CRID are quality/coverage/
        # location/counter variants rather than independent acquisitions.
        normalized = parts[:16]
        normalized[2] = "<PROCESSING_TYPE>"
        return tuple(normalized)
    return (granule_name,)


def processing_variant_rank(granule_name: str) -> tuple[int, int, int, str]:
    """Prefer standard production, then explicit quality/coverage where otherwise tied."""
    parts = granule_name.split("_")
    proc_rank = {"PR": 0, "OD": 1, "UR": 2}.get(product_processing_type(granule_name), 9)
    accuracy_rank = {"P": 0, "M": 1, "N": 2, "F": 3}.get(parts[16] if len(parts) > 16 else "", 9)
    coverage_rank = {"F": 0, "P": 1}.get(parts[17] if len(parts) > 17 else "", 9)
    return proc_rank, accuracy_rank, coverage_rank, granule_name


def collapse_duplicate_variants(products: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Retain one declared, mature product per unique acquisition pair."""
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for product in products:
        groups.setdefault(acquisition_pair_key(product["granule_name"]), []).append(product)
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for key, variants in groups.items():
        ordered = sorted(variants, key=lambda r: processing_variant_rank(r["granule_name"]))
        chosen = dict(ordered[0])
        chosen["pair_variant_count"] = len(variants)
        chosen["pair_variants"] = [
            {
                "granule_name": v["granule_name"],
                "processing_type": product_processing_type(v["granule_name"]),
                "selected": v["granule_name"] == chosen["granule_name"],
                "selection_rank": list(processing_variant_rank(v["granule_name"])),
            }
            for v in ordered
        ]
        selected.append(chosen)
        for variant in ordered[1:]:
            rejected.append({
                "granule_name": variant["granule_name"],
                "reason": "DUPLICATE_ACQUISITION_PAIR_LOWER_VARIANT_PRIORITY",
                "selected_granule_name": chosen["granule_name"],
                "product_type": variant["product_type"],
                "reference_date": variant["reference_date"],
                "secondary_date": variant["secondary_date"],
                "processing_type": product_processing_type(variant["granule_name"]),
            })
    selected.sort(key=lambda r: (r["secondary_date"], r["product_type"], r["granule_name"]))
    rejected.sort(key=lambda r: (r["secondary_date"], r["product_type"], r["granule_name"]))
    return selected, rejected

def product_maturity_evidence(
    row: dict[str, Any], granule_name: str, maturity_from_crid: Any
) -> tuple[str, str, str | None]:
    """Require recognized CRID maturity and reject catalog/CRID contradictions.

    Date and processing-type tokens are not maturity labels. ASF documents
    P05023+ as PROVISIONAL and the earlier X-release CRIDs as BETA; unknown
    CRIDs are not relabelled from acquisition dates alone.
    """
    parsed = str(maturity_from_crid(granule_name) or "UNKNOWN").upper()
    explicit = str(row.get("dataMaturity") or row.get("maturity") or "").strip().upper()
    collection = str(row.get("collectionName") or row.get("shortName") or "").strip()
    collection_upper = collection.upper()
    collection_maturity = (
        "PROVISIONAL" if "PROVISIONAL" in collection_upper
        else "BETA" if "BETA" in collection_upper
        else ""
    )
    explicit_maturity = explicit if explicit in {"BETA", "PROVISIONAL"} else ""
    declared = explicit_maturity or collection_maturity
    evidence = (
        f"CRID={re.search(r'_[A-Z]\\d{5}_', granule_name).group(0).strip('_') if re.search(r'_[A-Z]\\d{5}_', granule_name) else 'unparsed'}"
        f"; parsed={parsed}; catalog_maturity={declared or 'not_explicit'}"
        f"; collection={collection or 'not_reported'}"
    )
    if parsed not in {"BETA", "PROVISIONAL"}:
        return "UNKNOWN", evidence, "MATURITY_UNKNOWN_OR_UNSUPPORTED_CRID"
    if declared and declared != parsed:
        return "UNKNOWN", evidence, "CATALOG_COLLECTION_CRID_MATURITY_CONFLICT"
    return parsed, evidence, None


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
            stats = {
                "catalog_rows_returned": len(rows),
                "named_products": 0,
                "family_name_matches": 0,
                "parseable_pair_dates": 0,
                "reference_dates_in_window": 0,
                "secondary_dates_in_window": 0,
                "date_window_matches": 0,
                "supported_maturity": 0,
                "products_after_date_and_maturity_policy": 0,
                "sample_granule_names": [],
            }
            accepted = 0
            for row in rows:
                name = record_name(row)
                if name and len(stats["sample_granule_names"]) < 3:
                    stats["sample_granule_names"].append(name)
                if not name:
                    continue
                stats["named_products"] += 1
                match = PRODUCT_PATTERN.fullmatch(name)
                if not match or match.group(1) != family:
                    continue
                stats["family_name_matches"] += 1
                dates = product_dates(name)
                if not dates:
                    excluded.append({"granule_name": name, "reason": "UNPARSEABLE_PAIR_DATES"})
                    continue
                stats["parseable_pair_dates"] += 1
                reference, secondary = dates
                reference_in_window = start <= reference <= end
                secondary_in_window = start <= secondary <= end
                if reference_in_window:
                    stats["reference_dates_in_window"] += 1
                if secondary_in_window:
                    stats["secondary_dates_in_window"] += 1
                if args.date_filter_mode == "both-acquisitions-in-window":
                    date_matches = reference_in_window and secondary_in_window
                elif args.date_filter_mode == "secondary-acquisition-in-window":
                    date_matches = secondary_in_window
                else:
                    raise ValueError("DATE_FILTER_MODE_INVALID")
                if not date_matches:
                    if not reference_in_window and not secondary_in_window:
                        reason = "BOTH_ACQUISITIONS_OUTSIDE_DATE_WINDOW"
                    elif not reference_in_window:
                        reason = "REFERENCE_ACQUISITION_OUTSIDE_DATE_WINDOW"
                    else:
                        reason = "SECONDARY_ACQUISITION_OUTSIDE_DATE_WINDOW"
                    excluded.append({
                        "granule_name": name,
                        "reason": reason,
                        "reference_date": reference.isoformat(),
                        "secondary_date": secondary.isoformat(),
                        "date_filter_mode": args.date_filter_mode,
                    })
                    continue
                stats["date_window_matches"] += 1

                maturity, maturity_evidence, maturity_error = product_maturity_evidence(
                    row, name, maturity_for_name
                )
                if maturity_error:
                    excluded.append({
                        "granule_name": name,
                        "reason": maturity_error,
                        "crid": (re.search(r"_([A-Z]\\d{5})_", name).group(1)
                                 if re.search(r"_([A-Z]\\d{5})_", name) else "unparsed"),
                        "catalog_collection_name": row.get("collectionName"),
                        "catalog_data_maturity": row.get("dataMaturity") or row.get("maturity"),
                        "maturity_evidence": maturity_evidence,
                        "reference_date": reference.isoformat(),
                        "secondary_date": secondary.isoformat(),
                    })
                    continue
                stats["supported_maturity"] += 1
                size_bytes, size_basis = product_size_bytes(row, family, name)
                parts = name.split("_")
                record = {
                    "product_type": family,
                    "granule_name": name,
                    "processing_type": product_processing_type(name),
                    "product_accuracy": parts[16] if len(parts) > 16 else None,
                    "frame_coverage": parts[17] if len(parts) > 17 else None,
                    "crid": re.search(r"_([A-Z]\\d{5})_", name).group(1)
                            if re.search(r"_([A-Z]\\d{5})_", name) else None,
                    "catalog_collection_name": row.get("collectionName"),
                    "maturity": maturity,
                    "maturity_evidence": maturity_evidence,
                    "reference_date": reference.isoformat(),
                    "secondary_date": secondary.isoformat(),
                    "expected_source_bytes": size_bytes,
                    "expected_source_bytes_basis": size_basis,
                    "asf_catalog_product_type": row.get("productType"),
                    "discovery_source": "ASF_search_API_intersectsWith_exact_polygon",
                }
                if previous and previous != record:
                    raise RuntimeError(f"ASF_DUPLICATE_PRODUCT_METADATA_CONFLICT granule={name}")
                all_rows[name] = record
                accepted += 1
            stats["products_in_secondary_date_window"] = accepted
            query_summary[family] = stats
            print(
                "AOI_DISCOVERY_COUNTS "
                f"family={family} catalog_rows={stats['catalog_rows_returned']} "
                f"named_products={stats['named_products']} "
                f"family_matches={stats['family_name_matches']} "
                f"parseable_pair_dates={stats['parseable_pair_dates']} "
                f"reference_dates_in_window={stats['reference_dates_in_window']} "
                f"secondary_dates_in_window={stats['secondary_dates_in_window']} "
                f"date_window_matches={stats['date_window_matches']} "
                f"supported_maturity={stats['supported_maturity']} accepted={accepted}"
            )
            stats["products_after_date_and_maturity_policy"] = accepted

    supported_variants = sorted(
        all_rows.values(),
        key=lambda r: (r["secondary_date"], r["product_type"], r["granule_name"])
    )
    inventory, duplicate_variants_excluded = collapse_duplicate_variants(supported_variants)
    if not inventory:
        diagnostic = json.dumps(query_summary, ensure_ascii=False, separators=(",", ":"))
        raise ValueError(
            "NO_SUPPORTED_NISAR_PRODUCTS_INTERSECT_THE_AOI_AND_DATE_POLICY "
            f"catalog_diagnostics={diagnostic}"
        )
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
        # In a called reusable workflow, github.workflow_ref / github.sha identify
        # the dispatcher caller. Preserve that identity separately from the exact
        # feature-branch orchestrator code checked out on the runner.
        "dispatcher_workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "dispatcher_workflow_sha": os.environ.get("GITHUB_SHA"),
        "workflow_ref": os.environ.get("AOI_ORCHESTRATION_BRANCH", os.environ.get("GITHUB_WORKFLOW_REF")),
        "workflow_sha": os.environ.get("AOI_ORCHESTRATION_SHA", os.environ.get("GITHUB_SHA")),
        "orchestration_branch": os.environ.get("AOI_ORCHESTRATION_BRANCH"),
        "orchestration_sha": os.environ.get("AOI_ORCHESTRATION_SHA"),
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
            "date_filter_mode": args.date_filter_mode,
            "date_basis": (
                "both_reference_and_secondary_acquisition_dates_in_inclusive_window"
                if args.date_filter_mode == "both-acquisitions-in-window"
                else "secondary_acquisition_date_from_granule_identifier"
            ),
            "inclusive": True,
            "catalog_products_matching_date_policy_before_maturity": sum(
                s["date_window_matches"] for s in query_summary.values()
            ),
            "supported_product_variants_after_maturity_policy": len(supported_variants),
            "unique_acquisition_pair_products_in_window": len(inventory),
            "selected_products": len(selected),
            "catalog_search_start": "2024-01-01",
        },
        "catalog_query": {
            "service": "ASF DAAC Search API",
            "intersects_semantics": "exact supplied WKT polygon; no bbox substitution",
            "maturity_policy": (
                "Require a recognized CRID maturity; P05023+ is PROVISIONAL and recognized earlier X-release CRIDs are BETA. "
                "If an explicit ASF collection/dataMaturity label conflicts with CRID policy, reject rather than infer maturity from acquisition date."
            ),
            "families": query_summary,
            "excluded_products": excluded,
            "results_truncated": False,
        },
        "processing_variant_selection": {
            "policy": (
                "One product per product-family, acquisition-pair geometry/mode, reference-secondary timestamps and CRID. "
                "Prefer standard PR production, then OD science-on-demand, then UR urgent-response. "
                "Only if processing type ties, prefer P/M/N/F product-accuracy rank and full frame over partial frame."
            ),
            "supported_variants_before_deduplication": len(supported_variants),
            "unique_acquisition_pair_products": len(inventory),
            "excluded_duplicate_variants": duplicate_variants_excluded,
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
    p.add_argument(
        "--date-filter-mode",
        required=False,
        choices=("both-acquisitions-in-window", "secondary-acquisition-in-window"),
        default="both-acquisitions-in-window",
        help="Use both pair acquisition dates inside the window by default; secondary-only mode is explicit compatibility behavior.",
    )
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
    print(f"AOI_DISCOVERY_INVENTORY={manifest['time_window']['unique_acquisition_pair_products_in_window']}")
    print(f"AOI_SUPPORTED_VARIANTS={manifest['time_window']['supported_product_variants_after_maturity_policy']}")
    print(f"AOI_DUPLICATE_VARIANTS_EXCLUDED={len(manifest['processing_variant_selection']['excluded_duplicate_variants'])}")
    print(f"AOI_PRODUCTS_SELECTED={len(matrix)}")
    print(f"AOI_BASELINE_GUNW={manifest['baseline_product_counts']['GUNW']}")
    print(f"AOI_BASELINE_GOFF={manifest['baseline_product_counts']['GOFF']}")
    print("AOI_DISCOVERY_TRUNCATED=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
