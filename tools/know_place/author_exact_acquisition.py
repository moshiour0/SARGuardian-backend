"""Acquire the author's exact five GOFF products via NASA CMR metadata.

The catalog and authenticated preflight operations never download the HDF5 payload.
The download-and-analyze operation requires the explicit [run-know-place] marker,
records fresh SHA-256 hashes, and writes derived outputs separately from raw inputs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

from .author_catalog import (
    CMR_COLLECTION_CONCEPT_ID,
    EXPECTED_COLLECTION,
    EXPECTED_MATURITY,
    load_author_granules,
    query_cmr_exact_author_product,
)
from .goff_io import GoffReadError, inspect_goff_grid, parse_granule_identity

CONSENT_MARKER = "[run-know-place]"
TARGET_EPSG = 32645
TARGET_POSTING_M = 80.0
CROWN_GEOMETRY_HEIGHT_M = 5151.0
DEFAULT_CONTROL_DRAWS = 1000
DEFAULT_CONTROL_SEED = 260826
DEFAULT_COHERENCE_MINIMUM = 1
TRUSTED_ASF_HOSTS = (
    "asf.alaska.edu",
    ".asf.alaska.edu",
    ".asf.earthdatacloud.nasa.gov",
)


class AuthorExactAcquisitionError(RuntimeError):
    """Raised when exact-source acquisition or its provenance cannot be verified."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _trusted_asf_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == TRUSTED_ASF_HOSTS[0]
        or host.endswith(TRUSTED_ASF_HOSTS[1])
        or host.endswith(TRUSTED_ASF_HOSTS[2])
    )


def require_consent_marker(value: str | None) -> None:
    if value != CONSENT_MARKER:
        raise AuthorExactAcquisitionError("EXPLICIT_RAW_DOWNLOAD_CONSENT_MARKER_REQUIRED")


def select_exact_hdf5_data_url(catalog_record: dict[str, Any], wanted_name: str) -> str:
    """Select a direct CMR HTTP data link for this exact product, never a browse/metadata URL."""
    metadata = catalog_record.get("cmr_metadata")
    if not isinstance(metadata, dict):
        raise AuthorExactAcquisitionError(f"CMR_METADATA_MISSING:{wanted_name}")
    if catalog_record.get("catalog_identity_status") != "EXACT_CMR_GRANULE_CONFIRMED":
        raise AuthorExactAcquisitionError(f"CMR_EXACT_IDENTITY_NOT_CONFIRMED:{wanted_name}")
    if catalog_record.get("release_id") != "P05023":
        raise AuthorExactAcquisitionError(f"AUTHOR_RELEASE_MISMATCH:{wanted_name}")
    if catalog_record.get("cmr_collection_concept_id") != CMR_COLLECTION_CONCEPT_ID:
        raise AuthorExactAcquisitionError(f"CMR_COLLECTION_MISMATCH:{wanted_name}")
    links = metadata.get("links", [])
    if not isinstance(links, list):
        raise AuthorExactAcquisitionError(f"CMR_LINKS_INVALID:{wanted_name}")
    candidates: list[str] = []
    expected_file = wanted_name + ".h5"
    expected_path = f"/NISAR/{EXPECTED_COLLECTION}/{wanted_name}/{expected_file}"
    for link in links:
        if not isinstance(link, dict) or link.get("inherited") is True:
            continue
        rel = str(link.get("rel") or "")
        title = str(link.get("title") or "")
        href = link.get("href")
        if "data#" not in rel or expected_file not in title:
            continue
        if not isinstance(href, str) or not _trusted_asf_url(href):
            continue
        parsed = urlparse(href)
        if parsed.path != expected_path:
            continue
        candidates.append(href)
    unique = sorted(set(candidates))
    if len(unique) != 1:
        raise AuthorExactAcquisitionError(
            f"EXACT_CMR_HDF5_HTTP_URL_NOT_UNIQUE:{wanted_name}:count={len(unique)}"
        )
    return unique[0]


def discover_exact_author_sources() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Query CMR for all five author IDs, pin the collection, URL and interval."""
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    targets = load_author_granules()
    for target in targets:
        wanted = target["granule_name"]
        try:
            row, receipt = query_cmr_exact_author_product(target)
            if row is None:
                raise AuthorExactAcquisitionError(
                    f"CMR_AUTHOR_PRODUCT_NOT_CONFIRMED:{receipt.get('status')}"
                )
            if row.get("granule_name") != wanted:
                raise AuthorExactAcquisitionError("CMR_RETURNED_DIFFERENT_GRANULE")
            identity = parse_granule_identity(wanted + ".h5")
            if identity.release_id != "P05023" or identity.track != "098" or identity.direction != "A":
                raise AuthorExactAcquisitionError("AUTHOR_GRANULE_IDENTITY_CONTRACT_MISMATCH")
            start, end = target["interval"].split("/", maxsplit=1)
            if (
                identity.reference_start.date().isoformat() != start
                or identity.secondary_start.date().isoformat() != end
            ):
                raise AuthorExactAcquisitionError("AUTHOR_INTERVAL_DOES_NOT_MATCH_FILENAME")
            url = select_exact_hdf5_data_url(row, wanted)
            row["exact_data_url"] = url
            row["source_filename"] = wanted + ".h5"
            row["cmr_query_receipt"] = receipt
            row["interval_days"] = int(target["days"])
            row["expected_release"] = "P05023"
            row["source_sha256"] = None
            row["source_bytes"] = None
            row["download_status"] = "NOT_DOWNLOADED"
            rows.append(row)
        except Exception as exc:
            errors.append({
                "granule_name": wanted,
                "interval": target["interval"],
                "error_type": type(exc).__name__,
                "error_code": str(exc).split(":", maxsplit=1)[0][:160],
            })
    manifest = {
        "schema_version": "know-place-author-exact-acquisition/1.0",
        "created_at_utc": _utc_now(),
        "repository_branch": os.environ.get("GITHUB_REF_NAME", "local"),
        "repository_commit": os.environ.get("GITHUB_SHA", "local"),
        "collection_concept_id": CMR_COLLECTION_CONCEPT_ID,
        "expected_collection_short_name": EXPECTED_COLLECTION,
        "expected_maturity": EXPECTED_MATURITY,
        "author_release_id": "P05023",
        "expected_intervals": [row["interval"] for row in targets],
        "author_product_count": len(targets),
        "exact_cmr_confirmed_count": len(rows),
        "blocking_count": len(errors),
        "status": "PASS" if len(rows) == 5 and not errors else "BLOCKED",
        "products": rows,
        "blocking_products": errors,
        "source_downloads": 0,
        "raw_source_byte_identity": "UNVERIFIED",
        "paper_reproduction_status": "BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED",
        "hazard_detection_status": "NOT_EVALUATED",
    }
    return rows, manifest


def _load_downloader(science_root: Path):
    """Load the existing hardened single-granule HTTPS/credential helpers."""
    downloader_path = Path(__file__).resolve().parents[1] / "download_nisar_product.py"
    spec = importlib.util.spec_from_file_location("sarguardian_know_place_downloader", downloader_path)
    if spec is None or spec.loader is None:
        raise AuthorExactAcquisitionError("HARDENED_DOWNLOADER_MODULE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    acquisition, acquisition_sha = module.load_source_acquisition(science_root, "source")
    session = module.build_authenticated_session_with_retry(acquisition)
    return module, acquisition_sha, session


def authenticated_preflight(
    rows: list[dict[str, Any]],
    *,
    science_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Check current authenticated URL availability and exact Content-Length using HEAD/range only."""
    downloader, acquisition_sha, session = _load_downloader(science_root)
    probe_rows: list[dict[str, Any]] = []
    total_bytes = 0
    blockers: list[dict[str, str]] = []
    for row in rows:
        name = row["granule_name"]
        try:
            remote_bytes = downloader.probe_url_content_length(session, row["exact_data_url"])
            if remote_bytes is None or int(remote_bytes) <= 0:
                raise AuthorExactAcquisitionError("REMOTE_CONTENT_LENGTH_UNAVAILABLE")
            record = {
                "granule_name": name,
                "interval": row["interval"],
                "collection_concept_id": CMR_COLLECTION_CONCEPT_ID,
                "cmr_granule_concept_id": row["cmr_metadata"].get("id"),
                "url_host": urlparse(row["exact_data_url"]).hostname,
                "remote_content_length_bytes": int(remote_bytes),
                "probe_status": "PASS",
                "source_payload_downloaded": False,
            }
            total_bytes += int(remote_bytes)
        except Exception as exc:
            record = {
                "granule_name": name,
                "interval": row["interval"],
                "probe_status": "FAIL",
                "source_payload_downloaded": False,
                "error_type": type(exc).__name__,
                "error_code": str(exc).split(":", maxsplit=1)[0][:160],
            }
            blockers.append({"granule_name": name, "error_code": record["error_code"]})
        probe_rows.append(record)
    report = {
        "schema_version": "know-place-author-exact-preflight/1.0",
        "checked_at_utc": _utc_now(),
        "collection_concept_id": CMR_COLLECTION_CONCEPT_ID,
        "science_acquisition_module_sha256": acquisition_sha,
        "probe_method": "Authenticated HEAD with bounded metadata-only fallback to HTTP Range bytes=0-0 where server disallows HEAD",
        "product_count": len(probe_rows),
        "passed_count": sum(row["probe_status"] == "PASS" for row in probe_rows),
        "blocking_count": len(blockers),
        "estimated_total_source_bytes": total_bytes,
        "products": probe_rows,
        "blocking_products": blockers,
        "raw_payload_downloads": 0,
        "status": "PASS" if len(probe_rows) == 5 and not blockers else "BLOCKED",
    }
    _write_json_atomic(output_path, report)
    return report


def _build_analysis_config(
    source_manifest: dict[str, Any],
    raw_dir: Path,
    run_root: Path,
    *,
    geometry_height_m: float = CROWN_GEOMETRY_HEIGHT_M,
    control_draws: int = DEFAULT_CONTROL_DRAWS,
    seed: int = DEFAULT_CONTROL_SEED,
    coherence_minimum_valid_cells: int = DEFAULT_COHERENCE_MINIMUM,
) -> dict[str, Any]:
    """Build the analyzer's strict five-pair input config from actual downloaded receipts."""
    benchmark_path = Path(__file__).resolve().parents[2] / "docs" / "know-place" / "reference" / "author_benchmark_v1.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    spatial = benchmark["spatial_definition"]
    target_rows = load_author_granules()
    target_by_name = {row["granule_name"]: row for row in target_rows}
    products = []
    for product in source_manifest.get("products", []):
        if product.get("download_status") != "PASS":
            raise AuthorExactAcquisitionError("ANALYSIS_CONFIG_REQUIRES_FIVE_HASHED_DOWNLOADS")
        wanted = product["granule_name"]
        expected = target_by_name.get(wanted)
        if expected is None:
            raise AuthorExactAcquisitionError("DOWNLOADED_GRANULE_NOT_IN_AUTHOR_BENCHMARK")
        if product.get("release_id") != "P05023":
            raise AuthorExactAcquisitionError("ANALYSIS_CONFIG_RELEASE_NOT_AUTHOR_EXACT")
        if not product.get("source_sha256") or not product.get("source_bytes"):
            raise AuthorExactAcquisitionError("ANALYSIS_CONFIG_SOURCE_RECEIPT_INCOMPLETE")
        products.append({
            "path": f"raw/{product['source_filename']}",
            "expected_granule_name": product["source_filename"],
            "catalog_maturity": "PROVISIONAL",
            "catalog_maturity_evidence": (
                "NASA CMR exact producer-granule ID in pinned collection "
                f"{CMR_COLLECTION_CONCEPT_ID}; payload SHA-256 recorded after HDF5 validation"
            ),
        })
    if len(products) != 5:
        raise AuthorExactAcquisitionError("ANALYSIS_CONFIG_REQUIRES_FIVE_AUTHOR_PRODUCTS")
    config = {
        "schema_version": "know-place-analysis-inputs/1.0",
        "reference_box_wkt": spatial["reference_box_wkt"],
        "crown_wkt": spatial["crown_wkt"],
        "crown_geometry_kind": "bounding-box-approximation",
        "crown_geometry_source": (
            "Published WGS84 rectangle transcribed in author benchmark; the raw source product series is author-exact, "
            "but an author-supplied editable vector geometry was not present in the raw-data archive."
        ),
        "geometry_height_m": float(geometry_height_m),
        "control_seed": int(seed),
        "control_draws": int(control_draws),
        "coherence_minimum_valid_cells": int(coherence_minimum_valid_cells),
        "coherence_neighbour_policy": (
            "Primary minimum 1 because the preprint does not publish a minimum neighbour count; "
            "sensitivity is reported for 1,5,10,15,20,25."
        ),
        "products": products,
    }
    config_path = run_root / "know-place-inputs.json"
    _write_json_atomic(config_path, config)
    provenance = {
        "schema_version": "know-place-author-exact-run-config-provenance/1.0",
        "created_at_utc": _utc_now(),
        "config_sha256": sha256_file(config_path),
        "author_benchmark_file": "docs/know-place/reference/author_benchmark_v1.json",
        "author_benchmark_sha256": sha256_file(benchmark_path),
        "source_manifest_sha256": None,
        "configuration": config,
        "scientific_scope": "Exploratory metrics from author-exact source granules. Not a validated hazard detector.",
        "paper_reproduction_status": "BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED",
        "hazard_detection_status": "NOT_EVALUATED",
    }
    _write_json_atomic(run_root / "run-config-provenance.json", provenance)
    return config


def acquire_and_analyze(
    *,
    science_root: Path,
    run_root: Path,
    output_root: Path,
    consent_marker: str | None,
    expected_geometry_height_m: float = CROWN_GEOMETRY_HEIGHT_M,
    control_draws: int = DEFAULT_CONTROL_DRAWS,
    seed: int = DEFAULT_CONTROL_SEED,
) -> dict[str, Any]:
    """Download exactly five author granules one time each, hash/validate, then analyze separately."""
    require_consent_marker(consent_marker)
    run_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    raw_dir = run_root / "raw"
    raw_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(raw_dir, 0o700)

    rows, source_manifest = discover_exact_author_sources()
    source_manifest["source_downloads"] = 0
    manifest_path = run_root / "author-exact-source-manifest.json"
    _write_json_atomic(manifest_path, source_manifest)
    if source_manifest["status"] != "PASS" or len(rows) != 5:
        raise AuthorExactAcquisitionError("CMR_EXACT_AUTHOR_CATALOG_GATE_BLOCKED")

    preflight_path = run_root / "author-exact-preflight-manifest.json"
    probe = authenticated_preflight(rows, science_root=science_root, output_path=preflight_path)
    if probe.get("status") != "PASS" or probe.get("passed_count") != 5:
        source_manifest["status"] = "BLOCKED_REMOTE_PREFLIGHT_FAILED"
        source_manifest["preflight"] = probe
        _write_json_atomic(manifest_path, source_manifest)
        raise AuthorExactAcquisitionError("AUTHOR_EXACT_AUTHENTICATED_URL_PREFLIGHT_FAILED")

    required_bytes = int(probe["estimated_total_source_bytes"])
    free_bytes = shutil.disk_usage(run_root).free
    required_free = int(required_bytes * 1.5 + 2 * 1024 * 1024 * 1024)
    if free_bytes < required_free:
        source_manifest["status"] = "BLOCKED_INSUFFICIENT_DISK_SPACE"
        source_manifest["required_free_bytes"] = required_free
        source_manifest["runner_free_bytes_before_download"] = free_bytes
        _write_json_atomic(manifest_path, source_manifest)
        raise AuthorExactAcquisitionError("INSUFFICIENT_DISK_SPACE_BEFORE_RAW_DOWNLOAD")

    downloader, acquisition_sha, session = _load_downloader(science_root)
    source_manifest.update({
        "status": "DOWNLOAD_IN_PROGRESS",
        "authorization_marker": CONSENT_MARKER,
        "science_acquisition_module_sha256": acquisition_sha,
        "preflight": probe,
        "runner_free_bytes_before_download": free_bytes,
        "required_free_bytes_before_download": required_free,
        "source_downloads": 0,
        "products": [
            {
                "granule_name": row["granule_name"],
                "interval": row["interval"],
                "release_id": "P05023",
                "collection_concept_id": CMR_COLLECTION_CONCEPT_ID,
                "cmr_granule_concept_id": row["cmr_metadata"].get("id"),
                "source_filename": row["source_filename"],
                "download_url_host": urlparse(row["exact_data_url"]).hostname,
                "remote_content_length_bytes": next(
                    item["remote_content_length_bytes"]
                    for item in probe["products"] if item["granule_name"] == row["granule_name"]
                ),
                "download_status": "PENDING",
                "source_bytes": None,
                "source_sha256": None,
            }
            for row in rows
        ],
    })
    _write_json_atomic(manifest_path, source_manifest)

    for row, product_receipt in zip(rows, source_manifest["products"], strict=True):
        target_path = raw_dir / row["source_filename"]
        if target_path.exists():
            raise AuthorExactAcquisitionError("REFUSING_TO_OVERWRITE_EXISTING_RAW_HDF5")
        expected_bytes = int(product_receipt["remote_content_length_bytes"])
        try:
            downloaded = downloader.download_exact_product_with_timeout(
                session, row["exact_data_url"], target_path, expected_bytes,
            )
            import h5py
            if not h5py.is_hdf5(target_path):
                raise AuthorExactAcquisitionError("DOWNLOADED_SOURCE_IS_NOT_VALID_HDF5")
            if target_path.stat().st_size != expected_bytes or downloaded != expected_bytes:
                raise AuthorExactAcquisitionError("DOWNLOADED_SOURCE_BYTE_COUNT_MISMATCH")
            grid = inspect_goff_grid(
                target_path, polarization="HH", layer=2,
                expected_track="098", expected_direction="A", expected_processing="PR",
            )
            start, end = row["interval"].split("/", maxsplit=1)
            if (
                grid.identity.granule_name != row["granule_name"]
                or grid.identity.release_id != "P05023"
                or grid.identity.reference_start.date().isoformat() != start
                or grid.identity.secondary_start.date().isoformat() != end
                or grid.epsg != TARGET_EPSG
            ):
                raise AuthorExactAcquisitionError("RAW_HDF5_NOT_EXACT_AUTHOR_GRID_OR_INTERVAL")
            if not all(abs(abs(float(v)) - TARGET_POSTING_M) <= 1e-4 for v in (
                __import__("numpy").median(__import__("numpy").diff(grid.x_coordinates_m)),
                __import__("numpy").median(__import__("numpy").diff(grid.y_coordinates_m)),
            )):
                raise AuthorExactAcquisitionError("RAW_HDF5_POSTING_NOT_80M")
            product_receipt.update({
                "download_status": "PASS",
                "source_bytes": target_path.stat().st_size,
                "source_sha256": sha256_file(target_path),
                "hdf5_container_valid": True,
                "grid_epsg": grid.epsg,
                "grid_width": len(grid.x_coordinates_m),
                "grid_height": len(grid.y_coordinates_m),
                "polarization": grid.polarization,
                "layer": grid.layer,
                "validated_at_utc": _utc_now(),
            })
            source_manifest["source_downloads"] = sum(p.get("download_status") == "PASS" for p in source_manifest["products"])
            source_manifest["status"] = "DOWNLOAD_IN_PROGRESS"
            _write_json_atomic(manifest_path, source_manifest)
            print(
                f"AUTHOR_SOURCE_DOWNLOAD_PASS={row['granule_name']} "
                f"BYTES={product_receipt['source_bytes']} SHA256={product_receipt['source_sha256']}",
                flush=True,
            )
        except Exception as exc:
            product_receipt["download_status"] = "FAIL"
            product_receipt["failure_type"] = type(exc).__name__
            product_receipt["failure_code"] = str(exc).split(":", maxsplit=1)[0][:160]
            source_manifest["status"] = "FAILED_DURING_SOURCE_DOWNLOAD"
            source_manifest["source_downloads"] = sum(p.get("download_status") == "PASS" for p in source_manifest["products"])
            _write_json_atomic(manifest_path, source_manifest)
            raise

    source_manifest["status"] = "PASS_FIVE_EXACT_HDF5_DOWNLOADED_HASHED_AND_GRID_VALIDATED"
    source_manifest["source_downloads"] = 5
    source_manifest["author_exact_source_sha256_count"] = 5
    source_manifest["download_completed_at_utc"] = _utc_now()
    _write_json_atomic(manifest_path, source_manifest)

    _build_analysis_config(
        source_manifest, raw_dir, run_root,
        geometry_height_m=expected_geometry_height_m,
        control_draws=control_draws, seed=seed,
    )
    # Copy only receipts/configuration to the derived output area; raw HDF5 stays in run_root/raw.
    shutil.copy2(manifest_path, output_root / "author-exact-source-manifest.json")
    shutil.copy2(preflight_path, output_root / "author-exact-preflight-manifest.json")
    shutil.copy2(run_root / "know-place-inputs.json", output_root / "know-place-inputs.json")
    shutil.copy2(run_root / "run-config-provenance.json", output_root / "run-config-provenance.json")
    try:
        completed = subprocess.run(
            [
                sys.executable, "-m", "tools.know_place.analyze",
                "--config", str(run_root / "know-place-inputs.json"),
                "--out", str(output_root),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5 * 60 * 60,
        )
        (output_root / "analysis.stdout.log").write_text(completed.stdout or "", encoding="utf-8")
        (output_root / "analysis.stderr.log").write_text(completed.stderr or "", encoding="utf-8")
        report_path = output_root / "know-place-analysis-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {
            "status": "FAILED",
            "structural_status": "FAIL",
            "paper_reproduction_status": "BLOCKED_ANALYSIS_REPORT_MISSING",
            "hazard_detection_status": "NOT_EVALUATED",
        }
        report["author_exact_source_identity"] = {
            "status": "PASS_5_OF_5_EXACT_AUTHOR_P05023",
            "source_manifest_sha256": sha256_file(manifest_path),
            "source_hashes": {
                product["granule_name"]: product["source_sha256"]
                for product in source_manifest["products"]
            },
        }
        report["paper_reproduction_status"] = "BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED"
        report["hazard_detection_status"] = "NOT_EVALUATED"
        _write_json_atomic(report_path, report)
        status = {
            "schema_version": "know-place-author-exact-run-status/1.0",
            "status": "OUTPUTS_WRITTEN" if report_path.is_file() else "ANALYSIS_REPORT_MISSING",
            "analysis_exit_code": completed.returncode,
            "analysis_status": report.get("status"),
            "structural_status": report.get("structural_status"),
            "paper_reproduction_status": report.get("paper_reproduction_status"),
            "hazard_detection_status": report.get("hazard_detection_status"),
            "source_manifest_sha256": sha256_file(manifest_path),
            "created_at_utc": _utc_now(),
        }
        _write_json_atomic(output_root / "author-exact-analysis-status.json", status)
        print(f"AUTHOR_EXACT_ANALYSIS_EXIT_CODE={completed.returncode}")
        print(f"AUTHOR_EXACT_ANALYSIS_STATUS={report.get('status')}")
        print(f"PAPER_REPRODUCTION_STATUS={report.get('paper_reproduction_status')}")
        print("HAZARD_DETECTION_STATUS=NOT_EVALUATED")
        return status
    except subprocess.TimeoutExpired as exc:
        status = {
            "schema_version": "know-place-author-exact-run-status/1.0",
            "status": "ANALYSIS_TIMEOUT",
            "analysis_exit_code": None,
            "paper_reproduction_status": "BLOCKED_ANALYSIS_TIMEOUT",
            "hazard_detection_status": "NOT_EVALUATED",
            "source_manifest_sha256": sha256_file(manifest_path),
            "created_at_utc": _utc_now(),
        }
        _write_json_atomic(output_root / "author-exact-analysis-status.json", status)
        return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=("catalog", "preflight", "download-and-analyze"), required=True)
    parser.add_argument("--out-root", required=True, type=Path)
    parser.add_argument("--science-root", type=Path)
    parser.add_argument("--consent-marker")
    parser.add_argument("--geometry-height-m", type=float, default=CROWN_GEOMETRY_HEIGHT_M)
    parser.add_argument("--control-draws", type=int, default=DEFAULT_CONTROL_DRAWS)
    parser.add_argument("--seed", type=int, default=DEFAULT_CONTROL_SEED)
    args = parser.parse_args(argv)
    root = args.out_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.operation != "catalog" and args.science_root is None:
        parser.error("--science-root is required for preflight/download-and-analyze")
    try:
        rows, manifest = discover_exact_author_sources()
        if args.operation == "catalog":
            path = root / "author-exact-catalog-manifest.json"
            _write_json_atomic(path, manifest)
            print(f"AUTHOR_CMR_CATALOG_GATE={manifest['status']}")
            print(f"AUTHOR_EXACT_PRODUCTS_CONFIRMED={manifest['exact_cmr_confirmed_count']}/5")
            print("RAW_SOURCE_DOWNLOADS=0")
            print(f"MANIFEST={path}")
            return 0 if manifest["status"] == "PASS" else 2
        if args.operation == "preflight":
            path = root / "author-exact-preflight-manifest.json"
            report = authenticated_preflight(rows, science_root=args.science_root, output_path=path)
            print(f"AUTHOR_EXACT_PREFLIGHT={report['status']}")
            print(f"PRODUCTS_WITH_REMOTE_BYTES={report['passed_count']}/5")
            print("RAW_SOURCE_DOWNLOADS=0")
            return 0 if report["status"] == "PASS" else 2
        require_consent_marker(args.consent_marker)
        status = acquire_and_analyze(
            science_root=args.science_root,
            run_root=root / "source-run",
            output_root=root / "derived",
            consent_marker=args.consent_marker,
            expected_geometry_height_m=args.geometry_height_m,
            control_draws=args.control_draws,
            seed=args.seed,
        )
        return 0 if status["status"] == "OUTPUTS_WRITTEN" else 2
    except Exception as exc:
        print("AUTHOR_EXACT_ACQUISITION_STATUS=FAIL")
        print(f"ERROR={type(exc).__name__}:{str(exc).split(':',maxsplit=1)[0][:160]}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
