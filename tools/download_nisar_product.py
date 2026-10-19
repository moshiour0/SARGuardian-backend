#!/usr/bin/env python3
"""Download exactly one NISAR GUNW/GOFF granule for the retention pilot.

Credentials are read only from EARTHDATA_USERNAME / EARTHDATA_PASSWORD.
This helper never prints credentials, token material, signed URLs, or full
Earthaccess exception text. It does not delete downloaded source files.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.metadata
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def normal_name(value: str) -> str:
    name = Path(value.strip()).name
    return re.sub(r"\.h5$", "", name, flags=re.IGNORECASE)


def safe_name(result: Any) -> str:
    """Get only the public granule identifier from Earthaccess metadata."""
    if hasattr(result, "get"):
        for root_key in ("umm", "metadata"):
            root = result.get(root_key, {})
            if isinstance(root, dict):
                umm = root.get("umm", root) if isinstance(root.get("umm", root), dict) else root
                for key in ("GranuleUR", "producer_granule_id", "granuleName", "name"):
                    val = umm.get(key)
                    if val:
                        return Path(str(val)).name
        for key in ("granule_ur", "name", "producer_granule_id"):
            val = result.get(key)
            if val:
                return Path(str(val)).name
    for key in ("granule_ur", "name"):
        val = getattr(result, key, None)
        if val:
            return Path(str(val)).name
    return ""


def temporal_bounds_for_granule(name: str) -> tuple[str, str] | None:
    """Build a narrow CMR time window from a NISAR interferogram filename."""
    dates = re.findall(r"_(\d{8})T\d{6}", normal_name(name))
    if len(dates) < 2:
        return None
    start_day = min(dates)
    end_day = max(dates)
    try:
        end_exclusive = datetime.strptime(end_day, "%Y%m%d").date() + timedelta(days=1)
    except ValueError:
        return None
    start_iso = f"{start_day[:4]}-{start_day[4:6]}-{start_day[6:]}"
    return start_iso, end_exclusive.isoformat()


def safe_exception_diagnostics(exc: BaseException) -> dict[str, str | None]:
    """Summarise a CMR/HTTP exception without logging URLs or authentication material."""
    status_code: str | None = None
    details: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        code = getattr(response, "status_code", None)
        if code is not None and status_code is None:
            status_code = str(code)
        reason = getattr(response, "reason", None)
        if reason:
            details.append(str(reason))
        for arg in getattr(current, "args", ()):
            if isinstance(arg, str) and arg.strip():
                details.append(arg)
        current = current.__cause__ or current.__context__

    detail = " ".join(details)
    detail = re.sub(r"https?://[^\s\"'<>]+", "[URL]", detail)
    detail = re.sub(
        r"(?i)\b(password|passwd|token|access[_-]?token|refresh[_-]?token|"
        r"authorization|client[_-]?secret|secret)\b\s*[:=]\s*[^,;\s<>]+",
        r"\1=[REDACTED]",
        detail,
    )
    detail = re.sub(r"<[^>]+>", " ", detail)
    detail = html.unescape(detail)
    detail = re.sub(r"\s+", " ", detail).strip()
    # Keep only a short diagnostic; never emit raw response payloads or URLs.
    detail = detail[:180]
    return {
        "type": type(exc).__name__,
        "http_status": status_code,
        "detail_safe": detail or None,
    }


def earthdata_service_status(earthaccess_module: Any) -> dict[str, str]:
    """Return only public service-status labels; do not log status API payloads."""
    try:
        statuses = earthaccess_module.status()
        if not isinstance(statuses, dict):
            return {"Earthdata Login": "Unknown", "Common Metadata Repository": "Unknown"}
        return {
            "Earthdata Login": str(statuses.get("Earthdata Login", "Unknown"))[:40],
            "Common Metadata Repository": str(statuses.get("Common Metadata Repository", "Unknown"))[:40],
        }
    except Exception:
        return {"Earthdata Login": "Unknown", "Common Metadata Repository": "Unknown"}


def _search_data_with_retry(
    earthaccess_module: Any, parameters: dict[str, Any], max_attempts: int = 4,
) -> tuple[list[Any] | None, dict[str, str | None] | None, int]:
    """Retry transient CMR 5xx/timeouts with bounded exponential backoff."""
    last_diag: dict[str, str | None] | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            results = earthaccess_module.search_data(**parameters)
            return list(results), None, attempt
        except Exception as exc:
            last_diag = safe_exception_diagnostics(exc)
            status = last_diag.get("http_status")
            transient = status in {"408", "425", "429", "500", "502", "503", "504"}
            name = last_diag.get("type", "")
            if name in {"Timeout", "ConnectionError", "ConnectTimeout", "ReadTimeout"}:
                transient = True
            if not transient or attempt >= max_attempts:
                return None, last_diag, attempt
            delay = min(2 ** (attempt - 1), 8)
            print(
                f"CMR_TRANSIENT_RETRY attempt={attempt}/{max_attempts} "
                f"http_status={status or 'unknown'} delay_seconds={delay}",
                file=sys.stderr,
            )
            time.sleep(delay)
    return None, last_diag, max_attempts


def search_exact_granule(
    earthaccess_module: Any, collection: str, wanted: str
) -> tuple[list[Any], str, dict[str, Any]]:
    """Search exact granule first; fall back to a narrow temporal query on error/empty results.

    Search requests retry transient HTTP 5xx/429/timeouts four times at most.
    Every candidate is still checked for the exact public granule identifier.
    """
    diagnostics: dict[str, Any] = {
        "exact_search": {
            "type": None, "http_status": None, "detail_safe": None,
            "match_count": None, "attempts": 0,
        },
        "temporal_search": {
            "type": None, "http_status": None, "detail_safe": None,
            "match_count": None, "attempts": 0,
        },
    }
    results, search_error, attempts = _search_data_with_retry(
        earthaccess_module,
        {"short_name": collection, "granule_name": wanted, "count": 10},
    )
    diagnostics["exact_search"]["attempts"] = attempts
    if search_error:
        diagnostics["exact_search"].update(search_error)
    else:
        exact_matches = [
            item for item in (results or []) if normal_name(safe_name(item)) == wanted
        ]
        diagnostics["exact_search"]["match_count"] = len(exact_matches)
        if len(exact_matches) == 1:
            return exact_matches, "exact_granule_name", diagnostics
        if len(exact_matches) > 1:
            return exact_matches, "exact_granule_name_ambiguous", diagnostics

    temporal = temporal_bounds_for_granule(wanted)
    if temporal is None:
        return [], "no_temporal_fallback_available", diagnostics
    candidates, fallback_error, attempts = _search_data_with_retry(
        earthaccess_module,
        {"short_name": collection, "temporal": temporal, "count": 2000},
    )
    diagnostics["temporal_search"]["attempts"] = attempts
    if fallback_error:
        diagnostics["temporal_search"].update(fallback_error)
        return [], "temporal_fallback_failed", diagnostics

    matches = [
        item for item in (candidates or []) if normal_name(safe_name(item)) == wanted
    ]
    diagnostics["temporal_search"]["match_count"] = len(matches)
    return matches, "temporal_collection_fallback", diagnostics


def find_size_bytes(result: Any) -> int | None:
    """Read size estimate from UMM metadata when present; no URL probing."""
    candidates: list[Any] = []
    if hasattr(result, "get"):
        umm = result.get("umm", {})
        if not isinstance(umm, dict):
            umm = {}
        data_granule = umm.get("DataGranule", {})
        if isinstance(data_granule, dict):
            dist = data_granule.get("ArchiveAndDistributionInformation", [])
            if isinstance(dist, dict):
                dist = [dist]
            if isinstance(dist, list):
                for item in dist:
                    if isinstance(item, dict):
                        candidates.append(item.get("SizeInBytes"))
        for key in ("size_bytes", "SizeInBytes", "size"):
            candidates.append(result.get(key))
    for value in candidates:
        try:
            number = int(float(value))
            if number > 0:
                return number
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-type", required=True, choices=["GUNW", "GOFF"])
    parser.add_argument("--maturity", required=True, choices=["PROVISIONAL", "BETA"])
    parser.add_argument("--granule-name", required=True, help="Exact public NISAR granule identifier; no wildcard allowed")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--expected-source-bytes", type=int, default=0, help="Optional byte-size estimate from ASF if UMM does not expose one")
    parser.add_argument("--disk-safety-factor", type=float, default=2.2, help="Require this multiple of estimated source size as free disk space")
    args = parser.parse_args()

    supplied_name = args.granule_name.strip()
    wanted = normal_name(supplied_name)
    if Path(supplied_name).name != supplied_name or not re.fullmatch(r"NISAR_L2_(?:(?:PR|OD)_)?(GUNW|GOFF)_[A-Za-z0-9_.-]{10,250}", wanted):
        print("ERROR=EXACT_PUBLIC_GRANULE_NAME_REQUIRED", file=sys.stderr)
        return 2
    if f"_{args.product_type}_" not in wanted:
        print("ERROR=GRANULE_NAME_PRODUCT_TYPE_MISMATCH", file=sys.stderr)
        return 2
    if not os.environ.get("EARTHDATA_USERNAME") or not os.environ.get("EARTHDATA_PASSWORD"):
        print("ERROR=EARTHDATA_CREDENTIALS_MISSING", file=sys.stderr)
        return 2

    collection = f"NISAR_L2_{args.product_type}_{args.maturity}_V1"
    try:
        import earthaccess
    except Exception as exc:
        print(f"ERROR=EARTHACCESS_IMPORT_FAILED TYPE={type(exc).__name__}", file=sys.stderr)
        return 2
    try:
        auth = earthaccess.login(strategy="environment")
    except Exception as exc:
        print(f"ERROR=EARTHDATA_LOGIN_EXCEPTION TYPE={type(exc).__name__}", file=sys.stderr)
        return 2
    if auth is None or auth is False:
        print("ERROR=EARTHDATA_LOGIN_FAILED", file=sys.stderr)
        return 2

    matches, discovery_mode, diagnostics = search_exact_granule(earthaccess, collection, wanted)
    print(f"DISCOVERY_MODE={discovery_mode}")
    if len(matches) != 1:
        exact_diag = diagnostics["exact_search"]
        temporal_diag = diagnostics["temporal_search"]
        statuses = earthdata_service_status(earthaccess)
        print(
            f"CMR_STATUS={statuses['Common Metadata Repository']} "
            f"EARTHDATA_LOGIN_STATUS={statuses['Earthdata Login']}"
        )
        print(
            "EXACT_QUERY_DIAGNOSTIC="
            + json.dumps(exact_diag, sort_keys=True, separators=(",", ":"))
        )
        print(
            "TEMPORAL_QUERY_DIAGNOSTIC="
            + json.dumps(temporal_diag, sort_keys=True, separators=(",", ":"))
        )
        print(
            f"ERROR=EXPECTED_ONE_EXACT_GRANULE MATCH_COUNT={len(matches)} "
            f"COLLECTION={collection} DISCOVERY_MODE={discovery_mode}",
            file=sys.stderr,
        )
        return 2
    item = matches[0]
    metadata_bytes = find_size_bytes(item)
    expected_bytes = args.expected_source_bytes or metadata_bytes
    if not expected_bytes or expected_bytes <= 0:
        print("ERROR=SOURCE_SIZE_UNKNOWN_PROVIDE_EXPECTED_SOURCE_BYTES", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(args.out_dir).free
    required_free = int(expected_bytes * args.disk_safety_factor + 512 * 1024 * 1024)
    print(f"PRODUCT_TYPE={args.product_type}")
    print(f"MATURITY={args.maturity}")
    print(f"COLLECTION={collection}")
    print(f"EXPECTED_SOURCE_BYTES={expected_bytes}")
    print(f"RUNNER_FREE_BYTES_BEFORE_DOWNLOAD={free_bytes}")
    print(f"REQUIRED_FREE_BYTES_WITH_SAFETY_MARGIN={required_free}")
    if free_bytes < required_free:
        print("ERROR=INSUFFICIENT_RUNNER_DISK_SPACE", file=sys.stderr)
        return 2

    try:
        # One granule only. No parallel download of a multi-date stack.
        earthaccess.download([item], local_path=str(args.out_dir), threads=1)
    except Exception as exc:
        print(f"ERROR=EARTHACCESS_DOWNLOAD_FAILED TYPE={type(exc).__name__}", file=sys.stderr)
        return 2

    files = sorted([*args.out_dir.rglob("*.h5"), *args.out_dir.rglob("*.H5")])
    if len(files) != 1:
        print(f"ERROR=EXPECTED_ONE_HDF5_AFTER_DOWNLOAD COUNT={len(files)}", file=sys.stderr)
        return 2
    raw = files[0]
    actual_size = raw.stat().st_size
    free_after = shutil.disk_usage(args.out_dir).free
    if actual_size <= 0 or actual_size > free_bytes:
        print("ERROR=INVALID_DOWNLOADED_SOURCE_SIZE", file=sys.stderr)
        return 2
    if actual_size > expected_bytes * 1.20:
        print("ERROR=ACTUAL_SIZE_EXCEEDS_METADATA_ESTIMATE", file=sys.stderr)
        return 2

    receipt = {
        "schema_version": "sarguardian-single-granule-download/1.0",
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "product_type": args.product_type,
        "maturity": args.maturity,
        "collection_short_name": collection,
        "granule_name": wanted,
        "source_filename": raw.name,
        "source_bytes": actual_size,
        "source_sha256": sha256_file(raw),
        "downloader_script": Path(__file__).name,
        "downloader_script_sha256": sha256_file(Path(__file__).resolve()),
        "earthaccess_version": importlib.metadata.version("earthaccess"),
        "metadata_size_estimate_bytes": metadata_bytes,
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
