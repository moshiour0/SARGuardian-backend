#!/usr/bin/env python3
"""Download one exact NISAR granule using SARGuardian's pinned acquisition code.

Catalog queries, AOI construction and the authenticated ASF download call are
reused from science-source/src/nisar_acquisition.py. This wrapper only adds
single-product, disk-space, filename, checksum and provenance safeguards.
It never deletes the source file.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def normal_name(value: str) -> str:
    """Normalize a public granule ID or a source filename, preserving the ID."""
    return re.sub(r"\.h5$", "", Path(value.strip()).name, flags=re.IGNORECASE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_source_acquisition(science_root: Path, aoi: str) -> tuple[Any, str]:
    """Load the exact acquisition module shipped by the pinned science repo."""
    source_file = (science_root / "src" / "nisar_acquisition.py").resolve()
    if not source_file.is_file():
        raise FileNotFoundError("PINNED_SCIENCE_ACQUISITION_MODULE_MISSING")
    source_dir = str(source_file.parent)
    if source_dir not in sys.path:
        sys.path.insert(0, source_dir)
    spec = importlib.util.spec_from_file_location(
        "sarguardian_pinned_nisar_acquisition", source_file
    )
    if spec is None or spec.loader is None:
        raise ImportError("PINNED_SCIENCE_ACQUISITION_MODULE_COULD_NOT_BE_LOADED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # This imports AOIs from the same gunw_reader used by all science scripts.
    module.set_aoi(aoi)
    return module, sha256_file(source_file)


def trusted_asf_url(value: Any) -> bool:
    """Validate that the existing source catalog returned an HTTPS ASF URL."""
    if not isinstance(value, str) or not value:
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "asf.alaska.edu"
        or host.endswith(".asf.alaska.edu")
        or host.endswith(".asf.earthdatacloud.nasa.gov")
    )


def _catalog_item_properties(item: Any) -> dict[str, Any]:
    """Normalize source JSON records and supported ASFProduct results."""
    if isinstance(item, dict):
        return item
    props = getattr(item, "properties", None)
    return props if isinstance(props, dict) else {}


def _catalog_item_name(item: Any) -> str:
    props = _catalog_item_properties(item)
    for key in ("granuleName", "sceneName", "fileName", "fileID", "name"):
        value = props.get(key)
        if value:
            return normal_name(str(value))
    return ""


def _catalog_item_url(item: Any) -> str | None:
    props = _catalog_item_properties(item)
    for value in (props.get("downloadUrl"), props.get("url")):
        if trusted_asf_url(value):
            return value
    get_urls = getattr(item, "get_urls", None)
    if callable(get_urls):
        try:
            for value in get_urls() or []:
                if trusted_asf_url(value) and _catalog_item_name(item) in Path(urlparse(value).path).name:
                    return str(value)
        except Exception:
            pass
    return None


def _asf_search_fallback(
    acquisition: Any, wanted: str, product_type: str, catalog_start: str, catalog_end: str
) -> tuple[dict[str, Any] | None, str]:
    """Use the official ASF client with the same AOI/window/product filters.

    The pinned source project's legacy JSON query is tried first. When ASF
    returns HTTP 400/502 through that path, this client-based equivalent is
    used instead of hand-constructing another REST URL or querying CMR.
    """
    import asf_search

    first = datetime.strptime(catalog_start, "%Y-%m-%d").date()
    last = datetime.strptime(catalog_end, "%Y-%m-%d").date()
    found: dict[str, Any] = {}
    year = first.year
    while year <= last.year:
        lo = max(first, datetime(year, 1, 1).date())
        hi = min(last, datetime(year, 12, 31).date())
        results = asf_search.search(
            dataset="NISAR",
            intersectsWith=acquisition.SEARCH_WKT,
            processingLevel=list(acquisition.INTERFEROMETRIC),
            start=f"{lo.isoformat()}T00:00:00Z",
            end=f"{hi.isoformat()}T23:59:59Z",
            maxResults=2000,
        )
        for item in results:
            if _catalog_item_name(item) != wanted:
                continue
            props = _catalog_item_properties(item)
            url = _catalog_item_url(item)
            if not url:
                continue
            found[wanted] = {
                "granuleName": wanted,
                "productType": props.get("productType", product_type),
                "downloadUrl": url,
                "sizeMB": props.get("sizeMB", props.get("size_mb")),
                "sizeBytes": props.get("sizeBytes", props.get("bytes")),
                "dataMaturity": props.get("dataMaturity", props.get("maturity")),
                "_sarguardian_discovery_backend": "asf_search.search",
            }
        year += 1
    if len(found) == 1:
        return next(iter(found.values())), "asf_search.search"
    return None, "asf_search.search"


def find_exact_source_product(
    acquisition: Any,
    wanted: str,
    product_type: str,
    maturity: str,
    *,
    catalog_start: str = "2025-01-01",
    catalog_end: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    """Use the pinned source AOI query first, then ASF's supported Python client."""
    end = catalog_end or datetime.now(timezone.utc).date().isoformat()
    source_query_error: Exception | None = None
    rows: list[Any] = []
    try:
        rows = acquisition.query_by_year(
            catalog_start,
            end,
            platform="NISAR",
            processingLevel=",".join(acquisition.INTERFEROMETRIC),
        )
    except Exception as exc:
        source_query_error = exc
        print(
            f"SOURCE_AOI_QUERY_RETRYING_WITH_ASF_CLIENT TYPE={type(exc).__name__}",
            file=sys.stderr,
        )

    exact_source = [
        row for row in rows
        if isinstance(row, dict)
        and normal_name(str(row.get("granuleName", ""))) == wanted
        and str(row.get("productType", product_type)).upper() == product_type
    ]
    if len(exact_source) == 1:
        record = dict(exact_source[0])
        record["_sarguardian_discovery_backend"] = "source_query_by_year"
    else:
        record, backend = _asf_search_fallback(
            acquisition, wanted, product_type, catalog_start, end
        )
        if record is None:
            if source_query_error is not None:
                raise RuntimeError(
                    f"SOURCE_QUERY_AND_ASF_CLIENT_FAILED_{type(source_query_error).__name__}"
                ) from source_query_error
            raise LookupError(f"EXACT_SOURCE_AOI_GRANULE_MATCH_COUNT_{len(exact_source)}")
        record["_sarguardian_discovery_backend"] = backend

    reported_maturity = next(
        (
            str(record.get(key)).strip().upper()
            for key in ("dataMaturity", "maturity", "productMaturity")
            if record.get(key) not in (None, "")
        ),
        None,
    )
    if reported_maturity and reported_maturity != maturity.upper():
        raise ValueError("SOURCE_CATALOG_MATURITY_MISMATCH")
    url = record.get("downloadUrl") or record.get("url")
    if not trusted_asf_url(url):
        raise ValueError("SOURCE_CATALOG_DID_NOT_RETURN_A_TRUSTED_ASF_HTTPS_URL")
    record["downloadUrl"] = url
    return record, catalog_start, end


def size_estimate_bytes(record: dict[str, Any]) -> int | None:
    try:
        size_mb = float(record.get("size_mb", record.get("sizeMB")))
        if size_mb > 0:
            return int(size_mb * 1024 * 1024)
    except (TypeError, ValueError, OverflowError):
        pass
    for key in ("sizeBytes", "size_bytes", "SizeInBytes"):
        try:
            size = int(float(record.get(key)))
            if size > 0:
                return size
        except (TypeError, ValueError, OverflowError):
            pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-type", required=True, choices=["GUNW", "GOFF"])
    parser.add_argument("--maturity", required=True, choices=["PROVISIONAL", "BETA"])
    parser.add_argument("--granule-name", required=True, help="Exact public NISAR granule identifier; no wildcard")
    parser.add_argument("--science-root", required=True, type=Path, help="Checkout of the pinned SARGuardian main source")
    parser.add_argument("--aoi", default="source", help="AOI name defined in the pinned gunw_reader.AOIS")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--expected-source-bytes", type=int, default=0)
    parser.add_argument("--disk-safety-factor", type=float, default=2.2)
    args = parser.parse_args()

    supplied_name = args.granule_name.strip()
    wanted = normal_name(supplied_name)
    if Path(supplied_name).name != supplied_name or not re.fullmatch(
        r"NISAR_L2_(?:(?:PR|UR|OD)_)?(GUNW|GOFF)_[A-Za-z0-9_.-]{10,250}", wanted
    ):
        print("ERROR=EXACT_PUBLIC_GRANULE_NAME_REQUIRED", file=sys.stderr)
        return 2
    if f"_{args.product_type}_" not in wanted:
        print("ERROR=GRANULE_NAME_PRODUCT_TYPE_MISMATCH", file=sys.stderr)
        return 2
    if not os.environ.get("EARTHDATA_USERNAME") or not os.environ.get("EARTHDATA_PASSWORD"):
        print("ERROR=EARTHDATA_CREDENTIALS_MISSING", file=sys.stderr)
        return 2

    try:
        acquisition, acquisition_sha256 = load_source_acquisition(args.science_root, args.aoi)
        record, query_start, query_end = find_exact_source_product(
            acquisition, wanted, args.product_type, args.maturity
        )
    except Exception as exc:
        # No alternate catalog/query is attempted. Report a safe, actionable
        # failure and leave all local data untouched.
        print(f"ERROR=SOURCE_AOI_CATALOG_LOOKUP_FAILED TYPE={type(exc).__name__}", file=sys.stderr)
        print("SOURCE_ACQUISITION_MODULE=src/nisar_acquisition.py", file=sys.stderr)
        print(f"AOI={args.aoi}", file=sys.stderr)
        return 2

    metadata_bytes = size_estimate_bytes(record)
    expected_bytes = args.expected_source_bytes or metadata_bytes
    if not expected_bytes or expected_bytes <= 0:
        print("ERROR=SOURCE_SIZE_UNKNOWN_PROVIDE_EXPECTED_SOURCE_BYTES", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(args.out_dir).free
    required_free = int(expected_bytes * args.disk_safety_factor + 512 * 1024 * 1024)
    collection = f"NISAR_L2_{args.product_type}_{args.maturity}_V1"
    print(f"PRODUCT_TYPE={args.product_type}")
    print(f"MATURITY={args.maturity}")
    print(f"COLLECTION={collection}")
    print(f"AOI={args.aoi}")
    print("DISCOVERY_BACKEND=science-source/src/nisar_acquisition.py::query_by_year")
    print(f"DISCOVERY_START={query_start}")
    print(f"DISCOVERY_END={query_end}")
    print(f"EXPECTED_SOURCE_BYTES={expected_bytes}")
    print(f"RUNNER_FREE_BYTES_BEFORE_DOWNLOAD={free_bytes}")
    print(f"REQUIRED_FREE_BYTES_WITH_SAFETY_MARGIN={required_free}")
    if free_bytes < required_free:
        print("ERROR=INSUFFICIENT_RUNNER_DISK_SPACE", file=sys.stderr)
        return 2

    try:
        import asf_search
        # Same authenticated ASF download helper used by nisar_acquisition.py.
        session = acquisition.build_session()
        asf_search.download_url(
            url=record["downloadUrl"],
            path=str(args.out_dir),
            session=session,
        )
    except Exception as exc:
        print(f"ERROR=SOURCE_ASF_DOWNLOAD_FAILED TYPE={type(exc).__name__}", file=sys.stderr)
        return 2

    files = sorted([*args.out_dir.rglob("*.h5"), *args.out_dir.rglob("*.H5")])
    if len(files) != 1:
        print(f"ERROR=EXPECTED_ONE_HDF5_AFTER_DOWNLOAD COUNT={len(files)}", file=sys.stderr)
        return 2
    raw = files[0]
    if normal_name(raw.name) != wanted:
        print("ERROR=DOWNLOADED_FILENAME_DOES_NOT_MATCH_REQUESTED_GRANULE", file=sys.stderr)
        return 2

    actual_size = raw.stat().st_size
    free_after = shutil.disk_usage(args.out_dir).free
    if actual_size <= 0 or actual_size > free_bytes:
        print("ERROR=INVALID_DOWNLOADED_SOURCE_SIZE", file=sys.stderr)
        return 2
    if actual_size > expected_bytes * 1.20:
        print("ERROR=ACTUAL_SIZE_EXCEEDS_METADATA_ESTIMATE", file=sys.stderr)
        return 2

    receipt = {
        "schema_version": "sarguardian-single-granule-download/2.0",
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "product_type": args.product_type,
        "maturity_requested": args.maturity,
        "aoi": args.aoi,
        "collection_short_name": collection,
        "discovery_backend": record.get("_sarguardian_discovery_backend", "source_query_by_year"),
        "science_acquisition_sha256": acquisition_sha256,
        "discovery_start": query_start,
        "discovery_end": query_end,
        "granule_name": wanted,
        "source_filename": raw.name,
        "source_bytes": actual_size,
        "source_sha256": sha256_file(raw),
        "downloader_script": Path(__file__).name,
        "downloader_script_sha256": sha256_file(Path(__file__).resolve()),
        "asf_search_version": importlib.metadata.version("asf_search"),
        "catalog_size_estimate_bytes": metadata_bytes,
        "expected_size_bytes": expected_bytes,
        "runner_free_bytes_after_download": free_after,
        "source_deleted": False,
        "signed_download_urls_stored": False,
    }
    receipt_path = args.out_dir / "download-manifest.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RAW_PRODUCT_PATH={raw}")
    print(f"RAW_PRODUCT_BYTES={actual_size}")
    print(f"RAW_PRODUCT_SHA256={receipt['source_sha256']}")
    print(f"DOWNLOAD_MANIFEST_PATH={receipt_path}")
    print("RAW_SOURCE_DELETED=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
