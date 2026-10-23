"""Live ASF identity check for the author's exact five GOFF granules.

This gate confirms catalog identity only. It never downloads HDF5 or invents a
source checksum. Source-byte and SHA-256 pins are added only after exact bytes
are deliberately fetched and independently recorded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

from .catalog import (
    EXPECTED_COLLECTION,
    EXPECTED_MATURITY,
    CatalogIdentityError,
    _is_trusted_asf_url,
    _normalise_product_name,
    _product_properties,
    _product_urls,
)
from .goff_io import GoffReadError, parse_granule_identity


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHOR_BENCHMARK_PATH = (
    REPO_ROOT / "docs" / "know-place" / "reference" / "author_benchmark_v1.json"
)


def load_author_granules(path: str | Path = AUTHOR_BENCHMARK_PATH) -> list[dict[str, Any]]:
    """Load the five source IDs transcribed from Supplementary Table 1."""
    with Path(path).open("r", encoding="utf-8") as stream:
        benchmark = json.load(stream)
    pairs = benchmark.get("exact_author_granules")
    if not isinstance(pairs, list) or len(pairs) != 5:
        raise CatalogIdentityError("AUTHOR_GRANULE_MANIFEST_MUST_HAVE_FIVE_PAIRS")
    expected_intervals = [
        ("2026-06-20", "2026-07-02"),
        ("2026-07-02", "2026-07-14"),
        ("2026-07-14", "2026-07-26"),
        ("2026-07-26", "2026-08-19"),
        ("2026-08-19", "2026-08-31"),
    ]
    products: list[dict[str, Any]] = []
    for row, expected_dates in zip(pairs, expected_intervals, strict=True):
        name = row.get("id")
        interval = row.get("interval")
        if not isinstance(name, str) or not name or not isinstance(interval, str):
            raise CatalogIdentityError("AUTHOR_GRANULE_MANIFEST_ENTRY_INVALID")
        try:
            start, end = interval.split("/", maxsplit=1)
        except ValueError:
            raise CatalogIdentityError(f"AUTHOR_GRANULE_INTERVAL_INVALID:{name}") from None
        identity = parse_granule_identity(name + ".h5")
        actual_dates = (
            identity.reference_start.date().isoformat(),
            identity.secondary_start.date().isoformat(),
        )
        if (start, end) != expected_dates or actual_dates != expected_dates:
            raise CatalogIdentityError(
                f"AUTHOR_GRANULE_DATE_CONFLICT:{name}:expected={expected_dates}:actual={actual_dates}"
            )
        if identity.processing != "PR" or identity.track != "098" or identity.direction != "A":
            raise CatalogIdentityError(f"AUTHOR_GRANULE_GEOMETRY_MISMATCH:{name}")
        if identity.release_id != "P05023":
            raise CatalogIdentityError(f"AUTHOR_GRANULE_RELEASE_MISMATCH:{name}")
        products.append({"granule_name": name, "interval": interval, "days": int(row.get("days", 0))})
    if any("_P05023_" not in row["granule_name"] for row in products):
        raise CatalogIdentityError("AUTHOR_GRANULE_RELEASE_MANIFEST_CONFLICT")
    return products


def validate_author_catalog_product(
    target: dict[str, Any], results: list[Any]
) -> dict[str, Any]:
    """Confirm one exact author ID, expected collection and no conflicting maturity."""
    wanted = str(target["granule_name"])
    identity_keys = (
        "fileName", "granuleName", "sceneName", "productName",
        "producerGranuleId", "producerGranuleID", "granule_ur", "fileID", "name",
    )
    matches: list[tuple[dict[str, Any], list[str]]] = []
    for product in results:
        props = _product_properties(product)
        urls = _product_urls(product, props)
        exact_urls = [
            url for url in urls
            if _is_trusted_asf_url(url)
            and _normalise_product_name(url) == wanted
            and f"/{EXPECTED_COLLECTION}/" in urlparse(url).path
        ]
        exact_identity = any(_normalise_product_name(props.get(key)) == wanted for key in identity_keys)
        if exact_urls and (exact_identity or len(exact_urls) >= 1):
            matches.append((props, exact_urls))
    if not matches:
        raise CatalogIdentityError(f"ASF_AUTHOR_EXACT_GRANULE_NOT_FOUND:{wanted}")
    if len(matches) != 1:
        raise CatalogIdentityError(f"ASF_AUTHOR_EXACT_GRANULE_AMBIGUOUS:{wanted}:matches={len(matches)}")

    props, urls = matches[0]
    maturity_raw = props.get("dataMaturity") or props.get("maturity")
    maturity = str(maturity_raw or "").strip().upper()
    if maturity and maturity != EXPECTED_MATURITY:
        raise CatalogIdentityError(
            f"ASF_AUTHOR_MATURITY_CONFLICT:{wanted}:expected={EXPECTED_MATURITY}:actual={maturity}"
        )

    collection_values = [
        str(props[key]).strip()
        for key in ("collectionName", "collection", "collection_name")
        if props.get(key) is not None and str(props[key]).strip()
    ]
    if any(EXPECTED_COLLECTION not in value for value in collection_values):
        raise CatalogIdentityError(f"ASF_AUTHOR_COLLECTION_CONFLICT:{wanted}")

    identity = parse_granule_identity(wanted + ".h5")
    return {
        "granule_name": wanted,
        "interval": target["interval"],
        "processing": identity.processing,
        "track": identity.track,
        "direction": identity.direction,
        "release_id": identity.release_id,
        "collection": EXPECTED_COLLECTION,
        "catalog_maturity": maturity or "COLLECTION_ROUTE_ONLY",
        "catalog_url_host": urlparse(urls[0]).hostname,
        "catalog_identity_status": "EXACT_URL_CONFIRMED",
        "source_sha256": None,
        "source_sha256_status": "NOT_DOWNLOADED",
    }


def discover_author_products() -> list[dict[str, Any]]:
    """Query ASF's catalog for the five author IDs. No source payload is downloaded."""
    try:
        import asf_search
    except ImportError as exc:
        raise CatalogIdentityError("ASF_SEARCH_DEPENDENCY_MISSING") from exc

    verified: list[dict[str, Any]] = []
    for target in load_author_granules():
        wanted = target["granule_name"]
        try:
            results = list(asf_search.search(dataset="NISAR", granule_list=[wanted]))
        except Exception as exc:
            raise CatalogIdentityError(
                f"ASF_AUTHOR_QUERY_FAILED:{wanted}:exception={type(exc).__name__}"
            ) from None
        verified.append(validate_author_catalog_product(target, results))
    return verified


def write_manifest(out_path: str | Path) -> dict[str, Any]:
    products = discover_author_products()
    manifest = {
        "schema_version": "know-place-author-catalog-manifest/1.0",
        "status": "PASS",
        "catalog_checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "archive_payload_downloaded": False,
        "source_hashes_recorded": False,
        "warning": (
            "Catalog identity is not source-byte identity, method parity, a golden-output "
            "comparison, or a hazard detection. SHA-256 remains unknown until exact bytes "
            "are separately fetched and hashed."
        ),
        "products": products,
    }
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = write_manifest(args.out)
    except (CatalogIdentityError, GoffReadError, OSError, ValueError) as exc:
        print("KNOW_PLACE_AUTHOR_CATALOG_STATUS=FAIL")
        print(f"ERROR={type(exc).__name__}:{exc}")
        return 2
    print("KNOW_PLACE_AUTHOR_CATALOG_STATUS=PASS")
    print(f"AUTHOR_GRANULE_COUNT={len(manifest['products'])}")
    print("SOURCE_DOWNLOADS=0")
    print(f"MANIFEST={args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
