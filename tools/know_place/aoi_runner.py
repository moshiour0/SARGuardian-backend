"""Run arbitrary polygon/date-range NISAR GOFF measurement jobs.

The runner keeps catalog discovery, source-file integrity, pixel measurement,
scientific interpretation and hazard-detection status separate. It never emits
a positive hazard alarm; early-warning validation is a separate benchmark layer.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, time, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import shutil
import tempfile
from typing import Any
from urllib.parse import urlparse

import numpy as np

from .aoi_request import AOIRequest, AOIRequestError, validate_aoi_request
from .dashboard import write_dashboard
from .geometry import build_analysis_roi, parse_polygon_wkt
from .goff_io import (
    GoffReadError,
    inspect_goff_grid,
    parse_granule_identity,
    read_geometry_cubes,
    read_raw_goff,
    sample_geometry,
)
from .paper_method import (
    ScientificInputError,
    apply_paper_quality_gates,
    componentwise_background_correction,
    directional_coherence,
    project_offsets_to_horizontal,
    summarize_crown,
)
from .series import SeriesPlanError, build_pairwise_series_plan
from .uncertainty import spatial_block_bootstrap_summary

ENGINE_VERSION = "1.0.0"
TRUSTED_ASF_HOSTS = ("asf.alaska.edu", ".asf.earthdatacloud.nasa.gov")


class AOIRunError(RuntimeError):
    """A safe AOI runner failure with a stable machine-readable code."""

    def __init__(self, code: str, safe_message: str):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_safe_json(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        return _safe_json(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _runtime_environment() -> dict[str, Any]:
    versions = {}
    for module in ("numpy", "h5py", "scipy", "pyproj", "rasterio", "asf_search"):
        try:
            versions[module] = importlib.metadata.version(module)
        except importlib.metadata.PackageNotFoundError:
            versions[module] = None
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": versions,
    }


def _trusted_download_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "asf.alaska.edu" or host.endswith(".asf.alaska.edu")
        or host.endswith(".asf.earthdatacloud.nasa.gov")
    )


def _exact_bytes(properties: dict[str, Any]) -> int | None:
    for key in ("bytes", "fileSizeBytes", "fileSize", "sizeBytes", "size"):
        raw = properties.get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int) and raw >= 0:
            return raw
        if isinstance(raw, float) and raw >= 0 and raw.is_integer():
            return int(raw)
        if isinstance(raw, str) and re.fullmatch(r"[0-9]+", raw.strip()):
            return int(raw.strip())
    return None


def _asf_property(product: Any) -> dict[str, Any]:
    properties = getattr(product, "properties", None)
    if properties is None and isinstance(product, dict):
        properties = product.get("properties", product)
    return properties if isinstance(properties, dict) else {}


def _product_urls(product: Any, properties: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    get_urls = getattr(product, "get_urls", None)
    if callable(get_urls):
        try:
            urls.extend(item for item in get_urls() if isinstance(item, str))
        except Exception:
            pass
    for key in ("url", "downloadUrl", "download_url"):
        value = properties.get(key)
        if isinstance(value, str):
            urls.append(value)
    return list(dict.fromkeys(urls))


def _maturity(properties: dict[str, Any], urls: list[str]) -> tuple[str, str]:
    for key in ("dataMaturity", "maturity", "data_maturity"):
        raw = properties.get(key)
        value = str(raw or "").strip().upper()
        if value in {"PROVISIONAL", "BETA"}:
            return value, f"catalog_property:{key}"
    paths = [urlparse(url).path.upper() for url in urls]
    for path in paths:
        if "/NISAR_L2_GOFF_PROVISIONAL_V1/" in path:
            return "PROVISIONAL", "trusted_source_url_collection_path"
        if "/NISAR_L2_GOFF_BETA_V1/" in path:
            return "BETA", "trusted_source_url_collection_path"
    raise AOIRunError("CATALOG_MATURITY_UNRESOLVED", "Catalog returned a product with unresolved maturity")


def _product_name(properties: dict[str, Any], urls: list[str]) -> str:
    for key in ("granuleName", "granule_name", "fileName", "filename", "sceneName", "productName", "fileID"):
        value = properties.get(key)
        if isinstance(value, str) and value.strip():
            candidate = Path(urlparse(value).path).name
            if candidate.lower().endswith(".h5"):
                return candidate
            if candidate.startswith("NISAR_L2_PR_GOFF_"):
                return candidate + ".h5"
    for url in urls:
        name = Path(urlparse(url).path).name
        if name.startswith("NISAR_L2_PR_GOFF_") and name.lower().endswith(".h5"):
            return name
    raise AOIRunError("CATALOG_GRANULE_NAME_UNRESOLVED", "Catalog returned a GOFF product without an exact granule name")


def discover_nisar_goff(request: AOIRequest) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Query ASF once for the AOI/date range and preserve explicit exclusions."""
    try:
        import asf_search
    except ImportError as exc:
        raise AOIRunError("ASF_SEARCH_DEPENDENCY_MISSING", "Install the pinned asf_search runtime to query NISAR products") from exc

    try:
        results = asf_search.search(
            dataset="NISAR",
            intersectsWith=request.aoi_wkt,
            start=f"{request.start_date.isoformat()}T00:00:00Z",
            end=f"{request.end_date.isoformat()}T23:59:59Z",
            processingLevel="GOFF",
            mainBandPolarization=request.polarization,
            maxResults=2000,
        )
    except Exception as exc:
        raise AOIRunError(
            "ASF_CATALOG_QUERY_FAILED",
            f"ASF catalog query failed ({type(exc).__name__}); no product downloads were attempted",
        ) from None

    accepted: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    allowed_maturities = set(request.allowed_maturities)
    for product in results:
        properties = _asf_property(product)
        urls = _product_urls(product, properties)
        name = _product_name(properties, urls)
        trusted_urls = [url for url in urls if _trusted_download_url(url)]
        if not trusted_urls:
            raise AOIRunError("ASF_DOWNLOAD_HOST_UNTRUSTED", "Catalog returned no trusted HTTPS ASF download URL")
        identity = parse_granule_identity(name)
        maturity, maturity_evidence = _maturity(properties, trusted_urls)
        raw_pol = str(
            properties.get("mainBandPolarization")
            or properties.get("polarization")
            or properties.get("frequencyAPolarization")
            or ""
        ).upper()
        available_pol = {part.strip() for part in raw_pol.replace(",", "+").split("+") if part.strip()}
        if raw_pol and request.polarization not in available_pol and raw_pol != request.polarization:
            row = {
                "granule_name": name, "release_id": identity.release_id,
                "maturity": maturity, "decision": "EXCLUDED_POLARIZATION_MISMATCH",
                "reported_polarization": raw_pol,
            }
            all_rows.append(row)
            continue
        if not (identity.reference_start.date() >= request.start_date and
                identity.secondary_start.date() <= request.end_date):
            row = {
                "granule_name": name, "release_id": identity.release_id,
                "maturity": maturity, "decision": "EXCLUDED_PAIR_OUTSIDE_INCLUSIVE_DATE_RANGE",
                "reference_date": identity.reference_start.date().isoformat(),
                "secondary_date": identity.secondary_start.date().isoformat(),
            }
            all_rows.append(row)
            continue

        row = {
            "granule_name": name,
            "reference_date": identity.reference_start.date().isoformat(),
            "secondary_date": identity.secondary_start.date().isoformat(),
            "track": identity.track,
            "direction": identity.direction,
            "polarization": request.polarization,
            "polarization_evidence": (
                "ASF catalog query filtered mainBandPolarization; exact HDF5 group is rechecked after download"
                if raw_pol else
                "ASF query filter only; catalog product property omitted polarization, exact HDF5 group must confirm"
            ),
            "release_id": identity.release_id,
            "maturity": maturity,
            "maturity_evidence": maturity_evidence,
            "source_bytes": _exact_bytes(properties),
            "download_url": trusted_urls[0],
            "download_url_host": urlparse(trusted_urls[0]).hostname,
            "decision": "ELIGIBLE_CATALOG_CANDIDATE" if maturity in allowed_maturities else "EXCLUDED_MATURITY_NOT_ALLOWED",
        }
        all_rows.append({key: value for key, value in row.items() if key != "download_url"})
        if maturity in allowed_maturities:
            accepted.append(row)

    manifest = {
        "schema_version": "know-place-aoi-catalog-manifest/1.0",
        "catalog": "ASF DAAC via asf_search",
        "query": {
            "dataset": "NISAR",
            "processing_level": "GOFF",
            "intersects_wkt_sha256": _sha256_text(request.aoi_wkt),
            "start_utc": f"{request.start_date.isoformat()}T00:00:00Z",
            "end_utc": f"{request.end_date.isoformat()}T23:59:59Z",
            "main_band_polarization": request.polarization,
            "polarization_evidence_policy": "query filter is recorded; exact HDF5 polarization group must be validated before measurement",
            "allowed_maturities": list(request.allowed_maturities),
        },
        "result_count": len(all_rows),
        "eligible_count": len(accepted),
        "candidates": all_rows,
        "policy": {
            "maturity_not_in_allowlist": "excluded and preserved in manifest",
            "release_variant_substitution": "forbidden",
            "exact_source_checksums": "computed after downloads; not inferred from catalog names",
        },
    }
    return accepted, manifest


def _session_from_environment():
    try:
        import asf_search
    except ImportError as exc:
        raise AOIRunError("ASF_SEARCH_DEPENDENCY_MISSING", "Install asf_search to download NISAR GOFF products") from exc
    token = os.getenv("EARTHDATA_TOKEN", "").strip()
    username = os.getenv("EARTHDATA_USERNAME", "").strip()
    password = os.getenv("EARTHDATA_PASSWORD", "")
    session = asf_search.ASFSession()
    try:
        if token:
            return session.auth_with_token(token)
        if username and password:
            return session.auth_with_creds(username, password)
    except Exception as exc:
        raise AOIRunError("EARTHDATA_AUTH_FAILED", f"Earthdata authentication failed ({type(exc).__name__})") from None
    raise AOIRunError(
        "EARTHDATA_CREDENTIALS_REQUIRED",
        "Set EARTHDATA_TOKEN or both EARTHDATA_USERNAME and EARTHDATA_PASSWORD in the process environment",
    )


def _download_exact_product(record: dict[str, Any], cache_dir: Path, session: Any) -> tuple[Path, dict[str, Any]]:
    """Download one exact granule once, verify it, then atomically promote to cache."""
    import asf_search

    name = record["granule_name"]
    product_dir = cache_dir / hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    product_dir.mkdir(parents=True, exist_ok=True)
    target = product_dir / name
    receipt = product_dir / f"{name}.source-receipt.json"

    url = record["download_url"]
    url_fingerprint = _sha256_text(urlparse(url)._replace(query="", fragment="").geturl())
    maturity = record.get("maturity") or record.get("catalog_maturity") or "UNVERIFIED"
    release_id = record.get("release_id") or "UNKNOWN"

    if target.is_file():
        actual_hash = _sha256(target)
        if receipt.is_file():
            try:
                previous = json.loads(receipt.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise AOIRunError("SOURCE_CACHE_RECEIPT_INVALID", "Existing source cache receipt is invalid") from None
            if previous.get("source_url_fingerprint") != url_fingerprint or previous.get("source_sha256") != actual_hash:
                raise AOIRunError("SOURCE_CACHE_PROVENANCE_CONFLICT", "Existing cached granule no longer matches its source receipt")
            if previous.get("granule_name") != name or previous.get("release_id") != release_id or previous.get("maturity") != maturity:
                raise AOIRunError("SOURCE_CACHE_IDENTITY_CONFLICT", "Cached granule identity conflicts with the selected catalog record")
            if record.get("source_bytes") is not None and target.stat().st_size != record["source_bytes"]:
                raise AOIRunError("SOURCE_BYTE_SIZE_MISMATCH", "Cached granule byte size conflicts with current catalog evidence")
            return target, {
                "granule_name": name, "release_id": release_id, "maturity": maturity,
                "source_sha256": actual_hash, "source_bytes": target.stat().st_size,
                "source_url_fingerprint": url_fingerprint, "cache_status": "REUSED_HASH_VERIFIED",
            }
        raise AOIRunError("SOURCE_CACHE_RECEIPT_MISSING", "Existing cached source file has no integrity receipt; refusing silent reuse")

    if not _trusted_download_url(url):
        raise AOIRunError("ASF_DOWNLOAD_HOST_UNTRUSTED", "Refusing to download from an untrusted host")

    # A failed download must never leave a partial .h5 at the final cache path.
    temporary_dir = Path(tempfile.mkdtemp(prefix=".download-", dir=product_dir))
    try:
        try:
            asf_search.download_urls(urls=[url], path=str(temporary_dir), session=session, processes=1)
        except Exception as exc:
            raise AOIRunError(
                "ASF_PRODUCT_DOWNLOAD_FAILED",
                f"Product download failed ({type(exc).__name__}); no fallback variant was selected",
            ) from None
        downloaded = temporary_dir / name
        if not downloaded.is_file():
            candidates = [
                item for item in temporary_dir.iterdir()
                if item.is_file() and item.suffix.lower() == ".h5" and item.name == name
            ]
            if len(candidates) != 1:
                raise AOIRunError(
                    "DOWNLOADED_GRANULE_NAME_MISMATCH",
                    "Downloaded file did not preserve the exact selected granule name",
                )
            downloaded = candidates[0]
        source_bytes = downloaded.stat().st_size
        if record.get("source_bytes") is not None and source_bytes != record["source_bytes"]:
            raise AOIRunError(
                "SOURCE_BYTE_SIZE_MISMATCH",
                "Downloaded granule byte size does not match exact catalog byte-size evidence",
            )
        digest = _sha256(downloaded)
        os.replace(downloaded, target)
        receipt_payload = {
            "schema_version": "know-place-source-receipt/1.0",
            "granule_name": name,
            "release_id": release_id,
            "maturity": maturity,
            "source_url_fingerprint": url_fingerprint,
            "source_sha256": digest,
            "source_bytes": source_bytes,
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        temporary_receipt = receipt.with_suffix(receipt.suffix + ".partial")
        temporary_receipt.write_text(json.dumps(receipt_payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_receipt, receipt)
        return target, {
            "granule_name": name, "release_id": release_id, "maturity": maturity,
            "source_sha256": digest, "source_bytes": source_bytes,
            "source_url_fingerprint": url_fingerprint, "cache_status": "DOWNLOADED_AND_HASHED",
        }
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def _processing_extent_wkt(aoi_wkt: str, epsg: int, buffer_m: float) -> str:
    """Build an AOI-centred rectangular context extent in the product's native CRS."""
    from pyproj import Transformer

    ring = parse_polygon_wkt(aoi_wkt)
    forward = Transformer.from_crs("EPSG:4326", f"EPSG:{int(epsg)}", always_xy=True)
    reverse = Transformer.from_crs(f"EPSG:{int(epsg)}", "EPSG:4326", always_xy=True)
    px, py = forward.transform([p[0] for p in ring], [p[1] for p in ring])
    xmin, xmax = min(px) - buffer_m, max(px) + buffer_m
    ymin, ymax = min(py) - buffer_m, max(py) + buffer_m
    lon, lat = reverse.transform([xmin, xmax, xmax, xmin, xmin], [ymin, ymin, ymax, ymax, ymin])
    points = list(zip(lon, lat))
    if not all(math.isfinite(x) and math.isfinite(y) for x, y in points):
        raise AOIRunError("PROCESSING_EXTENT_PROJECTION_FAILED", "Could not project AOI buffer into WGS84")
    return "POLYGON ((" + ", ".join(f"{x:.9f} {y:.9f}" for x, y in points) + "))"


def _write_geotiff(
    path: Path,
    east: np.ndarray,
    north: np.ndarray,
    magnitude: np.ndarray,
    coherence: np.ndarray,
    valid: np.ndarray,
    x_coordinates_m: np.ndarray,
    y_coordinates_m: np.ndarray,
    epsg: int,
) -> None:
    try:
        import rasterio
        from affine import Affine
    except ImportError as exc:
        raise AOIRunError("GEOTIFF_RUNTIME_REQUIRED", "Install rasterio and affine to export GIS-ready displacement rasters") from exc
    dxs = np.abs(np.diff(x_coordinates_m))
    dys = np.abs(np.diff(y_coordinates_m))
    if not (len(dxs) and len(dys) and np.allclose(dxs, np.median(dxs), rtol=0, atol=1e-4)
            and np.allclose(dys, np.median(dys), rtol=0, atol=1e-4)):
        raise AOIRunError("NONUNIFORM_GOFF_GRID", "GeoTIFF export requires uniform monotonic GOFF grid axes")
    dx, dy = float(np.median(dxs)), float(np.median(dys))
    x_ascending = bool(x_coordinates_m[-1] > x_coordinates_m[0])
    y_descending = bool(y_coordinates_m[-1] < y_coordinates_m[0])
    arrays = [east, north, magnitude, coherence, valid.astype(float)]
    if not x_ascending:
        arrays = [np.fliplr(item) for item in arrays]
    if not y_descending:
        arrays = [np.flipud(item) for item in arrays]
    min_x, max_y = float(np.min(x_coordinates_m)), float(np.max(y_coordinates_m))
    transform = Affine(dx, 0.0, min_x - dx / 2.0, 0.0, -dy, max_y + dy / 2.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", width=arrays[0].shape[1], height=arrays[0].shape[0],
        count=5, dtype="float32", crs=f"EPSG:{int(epsg)}", transform=transform,
        nodata=-9999.0, compress="deflate", predictor=3,
    ) as dst:
        for index, array in enumerate(arrays, start=1):
            out = np.asarray(array, dtype=np.float32).copy()
            out[~np.isfinite(out)] = -9999.0
            dst.write(out, index)
        dst.set_band_description(1, "Eastward horizontal displacement (m)")
        dst.set_band_description(2, "Northward horizontal displacement (m)")
        dst.set_band_description(3, "Horizontal displacement magnitude (m)")
        dst.set_band_description(4, "5x5 directional coherence R (unitless)")
        dst.set_band_description(5, "Valid measurement mask (1=valid)")
        dst.update_tags(
            AREA_OR_POINT="Point",
            displacement_assumption="vertical motion assumed zero",
            nodata_policy="explicit -9999 only; inspect mask band",
            geometry_epsg=int(epsg),
        )


def _preview(
    magnitude: np.ndarray,
    x_coordinates_m: np.ndarray,
    y_coordinates_m: np.ndarray,
    aoi_ring_projected: tuple[tuple[float, float], ...],
    max_side: int = 72,
) -> dict[str, Any]:
    x = np.asarray(x_coordinates_m, dtype=float)
    y = np.asarray(y_coordinates_m, dtype=float)
    arr = np.asarray(magnitude, dtype=float)
    dx = float(np.median(np.abs(np.diff(x))))
    dy = float(np.median(np.abs(np.diff(y))))
    if x[-1] < x[0]:
        arr = np.fliplr(arr)
    if y[-1] > y[0]:
        arr = np.flipud(arr)
    stride = max(1, int(math.ceil(max(arr.shape) / max_side)))
    out_h = int(math.ceil(arr.shape[0] / stride))
    out_w = int(math.ceil(arr.shape[1] / stride))
    values: list[list[float | None]] = []
    for r in range(out_h):
        row = []
        for c in range(out_w):
            block = arr[r * stride:min(arr.shape[0], (r + 1) * stride),
                        c * stride:min(arr.shape[1], (c + 1) * stride)]
            finite = block[np.isfinite(block)]
            row.append(float(np.median(finite)) if finite.size else None)
        values.append(row)
    return {
        "width": out_w, "height": out_h, "values": values,
        "min_x_m": float(np.min(x)), "max_y_m": float(np.max(y)),
        "pixel_size_x_m": dx * stride, "pixel_size_y_m": dy * stride,
        "stride_cells": stride,
        "aoi_ring_xy": [[float(px), float(py)] for px, py in aoi_ring_projected],
        "description": "Median magnitude per block; visualization only, not measurement source.",
    }


def _write_pair_csv(path: Path, pairs: list[dict[str, Any]]) -> None:
    fields = [
        "reference_date", "secondary_date", "granule_name", "release_id",
        "status", "valid_aoi_pixels", "crown_median_horizontal_magnitude_m",
        "crown_mean_vector_magnitude_m", "crown_mean_vector_azimuth_deg_clockwise_from_north",
        "crown_median_directional_coherence_R", "source_sha256", "geotiff_file",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for pair in pairs:
            stats = pair.get("statistics", {})
            writer.writerow({
                "reference_date": pair.get("reference_date"),
                "secondary_date": pair.get("secondary_date"),
                "granule_name": pair.get("granule_name"),
                "release_id": pair.get("release_id"),
                "status": pair.get("status"),
                "valid_aoi_pixels": pair.get("valid_aoi_pixels"),
                **{field: stats.get(field) for field in fields[6:9]},
                "crown_median_directional_coherence_R": stats.get("crown_median_directional_coherence_R"),
                "source_sha256": pair.get("source_sha256"),
                "geotiff_file": pair.get("geotiff_file"),
            })


def run_aoi_analysis(
    request_payload: dict[str, Any],
    output_root: str | Path,
    *,
    cache_root: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Discover products, plan a single orbit chain, verify/download and measure it."""
    request = validate_aoi_request(request_payload)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_parent = Path(output_root).expanduser().resolve()
    run_dir = output_parent / f"{timestamp}_{request.request_sha256[:8]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "maps").mkdir()
    (run_dir / "diagnostics").mkdir()
    (run_dir / "visuals").mkdir()
    (run_dir / "source-evidence").mkdir()
    (run_dir / "request.json").write_text(json.dumps(request.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    try:
        catalog_rows, catalog_manifest = discover_nisar_goff(request)
        (run_dir / "source-evidence" / "catalog-manifest.json").write_text(
            json.dumps(catalog_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if not catalog_rows:
            raise AOIRunError("NO_ALLOWED_NISAR_GOFF_PRODUCTS", "No GOFF products matched the AOI, date range, polarization and maturity policy")

        plan_rows = [
            {key: value for key, value in row.items() if key != "download_url"}
            for row in catalog_rows
        ]
        plan = build_pairwise_series_plan(
            plan_rows,
            start_date=request.start_date,
            end_date=request.end_date,
            polarization=request.polarization,
            track=request.track,
            direction=request.direction,
            preferred_granules=request.preferred_granules,
        )
        (run_dir / "series-plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if dry_run:
            result = {
                "schema_version": "know-place-aoi-result/1.0",
                "engine_version": ENGINE_VERSION,
                "status": "CATALOG_AND_SERIES_PLAN_READY",
                "structural_status": "PASS",
                "measurement_status": "NOT_RUN_DRY_RUN",
                "paper_reproduction_status": "NOT_EVALUATED",
                "hazard_detection_status": "NOT_EVALUATED",
                "request_sha256": request.request_sha256,
                "request": request.to_dict(),
                "source_adapters": list(request.source_adapters),
                "source_candidates": len(catalog_rows),
                "pairwise_series_plan": plan,
                "pairs": [],
                "limitations": ["Dry run only: no source files were downloaded and no displacement metrics were computed."],
            }
            (run_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            (run_dir / "README.txt").write_text(
                "SARGuardian Know Place Analysis — catalog/series dry run\n"
                "No source HDF5 products were downloaded and no displacement metrics were computed.\n",
                encoding="utf-8",
            )
            write_dashboard(result, run_dir / "visuals" / "dashboard.html")
            output_files = sorted(
                file for file in run_dir.rglob("*")
                if file.is_file() and file.name != "manifest.json"
            )
            manifest = {
                "schema_version": "know-place-aoi-manifest/1.0",
                "engine_version": ENGINE_VERSION,
                "request_sha256": request.request_sha256,
                "dry_run": True,
                "sources": [],
                "files": [
                    {"path": str(file.relative_to(run_dir)).replace("\\", "/"),
                     "bytes": file.stat().st_size, "sha256": _sha256(file)}
                    for file in output_files
                ],
                "claim_boundary": {
                    "measurement_status": result["measurement_status"],
                    "paper_reproduction_status": result["paper_reproduction_status"],
                    "hazard_detection_status": result["hazard_detection_status"],
                },
            }
            (run_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            result["output_manifest"] = "manifest.json"
            result["output_files"] = len(manifest["files"])
            return result

        session = _session_from_environment()
        cache_base = Path(cache_root).expanduser().resolve() if cache_root else (
            Path.home() / ".cache" / "sarguardian" / "know-place"
        )
        # Share verified raw products across AOI requests so the same 1-GB
        # granule is not downloaded again for every polygon/date-range job.
        cache_dir = cache_base / "goff-products"
        cache_dir.mkdir(parents=True, exist_ok=True)
        catalog_by_name = {item["granule_name"]: item for item in catalog_rows}
        pairs: list[dict[str, Any]] = []
        download_evidence: list[dict[str, Any]] = []
        for planned in plan["pairs"]:
            record = catalog_by_name[planned["granule_name"]]
            source_path, receipt = _download_exact_product(record, cache_dir, session)
            download_evidence.append(receipt)
            grid = inspect_goff_grid(
                source_path, polarization=request.polarization, layer=2,
                expected_track=planned["track"], expected_direction=planned["direction"],
                expected_processing="PR",
            )
            roi_box_wkt = request.reference_wkt or _processing_extent_wkt(
                request.aoi_wkt, grid.epsg, request.reference_buffer_m
            )
            roi = build_analysis_roi(
                grid.x_coordinates_m, grid.y_coordinates_m, grid.epsg,
                box_wkt=roi_box_wkt, crown_wkt=request.aoi_wkt,
            )
            xx, yy = np.meshgrid(roi.x_coordinates_m, roi.y_coordinates_m)
            raw = read_raw_goff(
                source_path, polarization=request.polarization, layer=2,
                expected_track=planned["track"], expected_direction=planned["direction"],
                expected_processing="PR", window_slices=(roi.row_slice, roi.col_slice),
                expected_grid=grid,
            )
            cubes = read_geometry_cubes(source_path, expected_epsg=raw.epsg)
            if request.geometry_height_m is None:
                height_m = float(np.median(cubes.height_m))
                height_source = "product_geometry_height_axis_median_approximation_not_DEM"
            else:
                height_m = request.geometry_height_m
                height_source = "explicit_user_constant_hae_not_DEM"
            sample = sample_geometry(
                cubes, x_m=xx, y_m=yy, height_m=height_m, expected_epsg=raw.epsg,
            )
            east, north = project_offsets_to_horizontal(
                raw.along_track_m, raw.slant_range_m,
                sample.along_track_x, sample.along_track_y,
                sample.los_x, sample.los_y, sample.incidence_deg,
            )
            input_valid = np.isfinite(raw.correlation)
            valid, gate_counts, uncorrected_mag = apply_paper_quality_gates(
                east, north, raw.snr, input_valid=input_valid,
                minimum_snr=request.min_snr,
                maximum_horizontal_magnitude_m=request.max_horizontal_magnitude_m,
            )
            aoi_valid_before_reference = valid & roi.crown_mask & np.isfinite(east) & np.isfinite(north)
            if not aoi_valid_before_reference.any():
                pairs.append({
                    "reference_date": planned["reference_date"],
                    "secondary_date": planned["secondary_date"],
                    "chain_id": planned.get("chain_id", "UNASSIGNED"),
                    "relation_to_previous": planned.get("relation_to_previous", "UNVERIFIED"),
                    "granule_name": raw.identity.granule_name,
                    "release_id": raw.identity.release_id,
                    "catalog_maturity": record["maturity"],
                    "source_sha256": raw.source_sha256,
                    "epsg": raw.epsg,
                    "status": "INSUFFICIENT_AOI_VALID_PIXELS",
                    "valid_aoi_pixels": 0,
                    "quality_gate_counts": asdict(gate_counts),
                    "interpretation": "No AOI pixels passed the finite-data, SNR and magnitude gates; no displacement summary is emitted.",
                })
                continue

            background_info: dict[str, Any]
            if request.reference_wkt:
                try:
                    corrected_east, corrected_north, background_info = componentwise_background_correction(
                        east, north, valid, roi.box_mask, roi.crown_mask,
                    )
                except ScientificInputError as exc:
                    pairs.append({
                        "reference_date": planned["reference_date"],
                        "secondary_date": planned["secondary_date"],
                        "chain_id": planned.get("chain_id", "UNASSIGNED"),
                        "relation_to_previous": planned.get("relation_to_previous", "UNVERIFIED"),
                        "granule_name": raw.identity.granule_name,
                        "release_id": raw.identity.release_id,
                        "catalog_maturity": record["maturity"],
                        "source_sha256": raw.source_sha256,
                        "epsg": raw.epsg,
                        "status": "INSUFFICIENT_REFERENCE_SUPPORT",
                        "valid_aoi_pixels": int(aoi_valid_before_reference.sum()),
                        "quality_gate_counts": asdict(gate_counts),
                        "reason_code": str(exc).split(":", 1)[0],
                    })
                    continue
                reference_status = "APPLIED_EXTERNAL_REFERENCE_POLYGON"
            else:
                corrected_east, corrected_north = east.copy(), north.copy()
                background_info = {
                    "status": "NOT_APPLIED_NO_REFERENCE_POLYGON",
                    "valid_buffer_cells": int((valid & roi.box_mask & ~roi.crown_mask).sum()),
                }
                reference_status = "NOT_APPLIED_NO_REFERENCE_POLYGON"

            # Invalid raw offsets must not be mistaken for usable displacement in
            # the raster outputs when no external reference correction is applied.
            corrected_east = np.asarray(corrected_east, dtype=float)
            corrected_north = np.asarray(corrected_north, dtype=float)
            corrected_east[~valid] = np.nan
            corrected_north[~valid] = np.nan
            valid_box = valid & roi.box_mask & np.isfinite(corrected_east) & np.isfinite(corrected_north)
            magnitude = np.full(valid.shape, np.nan, dtype=float)
            magnitude[valid_box] = np.hypot(corrected_east[valid_box], corrected_north[valid_box])
            coherence = directional_coherence(
                corrected_east, corrected_north, valid,
                window_size=request.coherence_window,
                minimum_valid_cells=request.minimum_valid_neighbours,
            )
            aoi_valid = valid & roi.crown_mask & np.isfinite(corrected_east) & np.isfinite(corrected_north)
            base = {
                "reference_date": planned["reference_date"],
                "secondary_date": planned["secondary_date"],
                "chain_id": planned.get("chain_id", "UNASSIGNED"),
                "relation_to_previous": planned.get("relation_to_previous", "UNVERIFIED"),
                "granule_name": raw.identity.granule_name,
                "release_id": raw.identity.release_id,
                "catalog_maturity": record["maturity"],
                "source_sha256": raw.source_sha256,
                "source_bytes": source_path.stat().st_size,
                "epsg": raw.epsg,
                "direction": raw.identity.direction,
                "track": raw.identity.track,
                "polarization": raw.polarization,
                "status": "STARTED",
                "quality_gate_counts": asdict(gate_counts),
                "valid_aoi_pixels": int(aoi_valid.sum()),
                "geometry": {
                    "metadata_group": sample.metadata_group,
                    "unit_evidence": cubes.unit_evidence,
                    "height_m_used": height_m,
                    "height_source": height_source,
                    "vertical_motion_assumption": "zero",
                    "projection_equations": "dE=AT*atuX-(SR/sin(theta))*(losX/|los_h|); dN=AT*atuY-(SR/sin(theta))*(losY/|los_h|)",
                },
                "background_correction": background_info,
                "reference_policy": reference_status,
                "quality_policy": {
                    "minimum_snr": request.min_snr,
                    "maximum_horizontal_magnitude_m": request.max_horizontal_magnitude_m,
                    "gross_outliers": "rejected_not_clipped",
                },
                "coherence_policy": {
                    "window_size": request.coherence_window,
                    "minimum_valid_neighbours": request.minimum_valid_neighbours,
                    "edge_policy": "zero-padded windows; only cells meeting minimum count are reported",
                    "parity_status": "EXPLORATORY_UNTIL_AUTHOR_POLICY_IS_VERIFIED",
                },
            }
            if not aoi_valid.any():
                base["status"] = "INSUFFICIENT_AOI_VALID_PIXELS"
                base["reason"] = "No AOI cells pass finite-data, SNR and projected-magnitude gates"
                pairs.append(base)
                continue

            summary = summarize_crown(
                corrected_east, corrected_north, valid, roi.crown_mask,
                coherence, interval_days=max(1, (raw.identity.secondary_start.date() - raw.identity.reference_start.date()).days),
            )
            uncertainty = spatial_block_bootstrap_summary(
                corrected_east, corrected_north, valid, roi.crown_mask,
                block_size_cells=5, replicates=1000, seed=260826, minimum_blocks=8,
            )
            controls = None
            try:
                from .paper_method import empirical_percentile, size_matched_spatial_controls
                control = size_matched_spatial_controls(
                    magnitude, coherence, valid_box, roi.box_mask, roi.crown_mask,
                    pixel_size_x_m=float(np.median(np.abs(np.diff(roi.x_coordinates_m)))),
                    pixel_size_y_m=float(np.median(np.abs(np.diff(roi.y_coordinates_m)))),
                    draws=1000, seed=260826,
                )
                control_median = control["control_median_of_median_displacement_m"]
                control["exploratory_magnitude_percentile"] = empirical_percentile(
                    control["mag_distribution_for_percentile"], summary["crown_median_horizontal_magnitude_m"]
                )
                control.pop("mag_distribution_for_percentile", None)
                control.pop("R_distribution_for_percentile", None)
                control.pop("displacement_control_values_m", None)
                control.pop("directional_coherence_control_values_R", None)
                control.pop("valid_pixel_counts", None)
                control["paper_parity_status"] = "NOT_VERIFIED"
                controls = control
            except (ScientificInputError, ValueError) as exc:
                controls = {"status": "UNAVAILABLE", "reason_code": str(exc).split(":",1)[0], "paper_parity_status": "NOT_VERIFIED"}

            token = hashlib.sha256(raw.identity.granule_name.encode("utf-8")).hexdigest()[:16]
            geotiff_relative = f"maps/{token}_displacement.tif"
            npz_relative = f"diagnostics/{token}_arrays.npz"
            _write_geotiff(
                run_dir / geotiff_relative,
                corrected_east, corrected_north, magnitude, coherence, valid_box,
                roi.x_coordinates_m, roi.y_coordinates_m, raw.epsg,
            )
            np.savez_compressed(
                run_dir / npz_relative,
                east_m=corrected_east.astype(np.float32),
                north_m=corrected_north.astype(np.float32),
                magnitude_m=magnitude.astype(np.float32),
                coherence_R=coherence.astype(np.float32),
                valid_mask=valid_box.astype(np.uint8),
                aoi_mask=roi.crown_mask.astype(np.uint8),
                reference_mask=roi.box_mask.astype(np.uint8),
                x_coordinates_m=roi.x_coordinates_m.astype(np.float64),
                y_coordinates_m=roi.y_coordinates_m.astype(np.float64),
            )
            base.update({
                "status": "METRICS_COMPUTED",
                "statistics": summary,
                "spatial_block_bootstrap_uncertainty": uncertainty,
                "exploratory_control_comparison": controls,
                "geotiff_file": geotiff_relative,
                "diagnostic_arrays_file": npz_relative,
                "map_preview": _preview(
                    magnitude, roi.x_coordinates_m, roi.y_coordinates_m,
                    roi.crown_ring_projected,
                ),
                "interpretation": "Measurement-only output. Hazard classification is not evaluated by this measurement engine.",
            })
            pairs.append(base)

        if not pairs:
            raise AOIRunError("NO_PAIR_MEASUREMENTS", "No product pair reached metric computation")
        computed = sum(p.get("status") == "METRICS_COMPUTED" for p in pairs)
        result = {
            "schema_version": "know-place-aoi-result/1.0",
            "engine_version": ENGINE_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "runtime_environment": _runtime_environment(),
            "status": "SCIENTIFIC_METRICS_COMPUTED" if computed else "NO_VALID_PAIR_METRICS",
            "structural_status": "PASS" if computed else "PARTIAL_INSUFFICIENT_DATA",
            "measurement_status": "METRICS_COMPUTED" if computed else "NOT_MEASURABLE",
            "paper_reproduction_status": "NOT_EVALUATED_GENERIC_AOI",
            "hazard_detection_status": "NOT_EVALUATED",
            "request_sha256": request.request_sha256,
            "request": request.to_dict(),
            "source_adapters": list(request.source_adapters),
            "reference_policy": "external reference polygon component-median correction" if request.reference_wkt else f"no background correction; {request.reference_buffer_m:g} m local context used for controls",
            "pairwise_series_plan": plan,
            "pairs": pairs,
            "download_evidence": download_evidence,
            "output_manifest": "manifest.json",
            "limitations": [
                "The runner measures displacement; it does not classify landslide/glacier-collapse hazard or issue alarms.",
                "A constant height per AOI is an approximation. Product-height-axis midpoint is used when no explicit HAE is supplied; use a DEM-backed per-pixel geometry sampler before operational claims.",
                "Spatial controls are exploratory; the sampler must be benchmarked against independent source-method or author-supplement implementations where available.",
                "Source grids and orbit direction are not mixed within a pairwise series; a continuous chain still requires separate review before cumulative movement can be computed.",
                "GOFF horizontal displacement assumes zero vertical motion and uses product geometry; it does not measure 3-D displacement.",
            ],
        }
        _write_pair_csv(run_dir / "timeseries.csv", pairs)
        (run_dir / "result.json").write_text(json.dumps(_safe_json(result), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        (run_dir / "README.txt").write_text(
            "SARGuardian Know Place Analysis\n"
            "This folder contains measurement products and provenance. A successful run is not a hazard detection.\n"
            "Inspect result.json, manifest.json, timeseries.csv, visuals/dashboard.html and the native-grid GeoTIFFs under maps/.\n",
            encoding="utf-8",
        )
        write_dashboard(result, run_dir / "visuals" / "dashboard.html")
        output_files = sorted(
            path for path in run_dir.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        )
        manifest = {
            "schema_version": "know-place-aoi-manifest/1.0",
            "engine_version": ENGINE_VERSION,
            "created_at_utc": result["created_at_utc"],
            "request_sha256": request.request_sha256,
            "source_product_count": len(download_evidence),
            "sources": download_evidence,
            "files": [
                {"path": str(file.relative_to(run_dir)).replace("\\", "/"),
                 "bytes": file.stat().st_size, "sha256": _sha256(file)}
                for file in output_files
            ],
            "raw_h5_retention": {
                "raw_h5_in_output_bundle": False,
                "source_cache_policy": "Raw HDF5 remains in a private external cache; absolute paths are intentionally not written to the result manifest.",
                "note": "Result bundles include source identities and SHA-256 provenance, not raw source HDF5 files.",
            },
            "claim_boundary": {
                "measurement_status": result["measurement_status"],
                "paper_reproduction_status": result["paper_reproduction_status"],
                "hazard_detection_status": result["hazard_detection_status"],
            },
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return result
    except (AOIRunError, AOIRequestError, SeriesPlanError, GoffReadError, ScientificInputError) as exc:
        code = getattr(exc, "code", str(exc).split(":", 1)[0]) or type(exc).__name__
        safe = getattr(exc, "safe_message", str(exc))
        failure = {
            "schema_version": "know-place-aoi-result/1.0",
            "engine_version": ENGINE_VERSION,
            "status": "FAILED",
            "structural_status": "FAIL",
            "measurement_status": "NOT_COMPUTED",
            "paper_reproduction_status": "NOT_EVALUATED",
            "hazard_detection_status": "NOT_EVALUATED",
            "request_sha256": request.request_sha256,
            "failure": {"code": str(code)[:100], "safe_message": str(safe)[:300]},
        }
        (run_dir / "failure.json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        raise AOIRunError(str(code)[:100], str(safe)[:300]) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run polygon/date-range NISAR GOFF measurement analysis (no hazard alarm).")
    parser.add_argument("--request", required=True, type=Path, help="Versioned JSON request with AOI polygon and inclusive date range")
    parser.add_argument("--out", required=True, type=Path, help="Root directory for derived result runs")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Private source-HDF5 cache directory")
    parser.add_argument("--dry-run", action="store_true", help="Discover/plan only; do not authenticate or download source products")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.request.read_text(encoding="utf-8"))
        result = run_aoi_analysis(payload, args.out, cache_root=args.cache_dir, dry_run=args.dry_run)
    except (OSError, json.JSONDecodeError) as exc:
        print("KNOW_PLACE_AOI_STATUS=FAIL")
        print(f"ERROR={type(exc).__name__}:REQUEST_READ_FAILED")
        return 2
    except AOIRunError as exc:
        print("KNOW_PLACE_AOI_STATUS=FAIL")
        print(f"ERROR={exc.code}:{exc.safe_message}")
        return 2
    print(f"KNOW_PLACE_AOI_STATUS={result['status']}")
    print(f"STRUCTURAL_STATUS={result['structural_status']}")
    print(f"MEASUREMENT_STATUS={result['measurement_status']}")
    print(f"PAPER_REPRODUCTION_STATUS={result['paper_reproduction_status']}")
    print(f"HAZARD_DETECTION_STATUS={result['hazard_detection_status']}")
    print(f"RUN_OUTPUT={args.out.resolve()}")
    return 0 if result["structural_status"] in {"PASS", "PARTIAL_INSUFFICIENT_DATA"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
