"""Target-free, AOI-wide spatial anomaly screening on retained NISAR rasters.

This stage finds candidate regions without a user-specified point. It is deliberately
a conservative screening layer: a spatial outlier is not, by itself, validated ground
movement. Candidate pixels are scored separately for GUNW LOS displacement, GOFF
range offset, and GOFF along-track offset, with product quality masks applied first.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.warp import transform_geom
from scipy.ndimage import label, median_filter


_IDENTITY = re.compile(
    r"^NISAR_L2_(?P<processing>PR|UR)_(?P<product>GUNW|GOFF)_"
    r"(?P<path>\d{3})_(?P<frame>\d{3})_(?P<direction>[AD])_"
    r"(?P<track_segment>\d{3})_(?P<subswath>\d{3})_(?P<bandwidth>\d{4})_"
    r"(?P<polarisation>[A-Z]{2})_.*?_(?P<crid>[PX]\d{5})_N_",
    re.IGNORECASE,
)


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _safe_export_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def _source_stem(value: Any) -> str:
    name = Path(str(value or "")).name
    return name[:-3] if name.lower().endswith(".h5") else name


def _identity(granule_name: str, product_type: str) -> dict[str, str] | None:
    match = _IDENTITY.search(Path(granule_name).name)
    if not match or match.group("product").upper() != product_type.upper():
        return None
    return {key: str(value).upper() if key in {"processing", "product", "direction", "polarisation", "crid"} else str(value)
            for key, value in match.groupdict().items()}


def _robust_sigma(values: np.ndarray) -> float | None:
    sample = values[np.isfinite(values)]
    if sample.size < 200:
        return None
    median = float(np.median(sample))
    mad = float(np.median(np.abs(sample - median)))
    if not math.isfinite(mad) or mad <= np.finfo(np.float32).eps:
        return None
    return 1.4826 * mad


def _empty_report(status: str, reason: str, aoi_wkt_sha256: str | None) -> dict[str, Any]:
    return {
        "schema_version": "sarguardian-aoi-spatial-candidates/1.0",
        "status": status,
        "aoi_wkt_sha256": aoi_wkt_sha256,
        "analysis_scope": "target-free spatial anomaly screening of retained AOI-clipped raster exports",
        "target_required": False,
        "candidate_features": 0,
        "products_examined": 0,
        "product_metrics_examined": 0,
        "groups": [],
        "features": [],
        "movement_confirmed": False,
        "hazard_detected": False,
        "warnings": [
            "Spatial anomalies are candidate regions, not confirmed ground movement.",
            "The screen measures relative spatial contrast within each pair; it cannot detect uniform AOI-wide motion from its own background.",
            "The robust AOI/background scale is not an independently validated stable-ground reference.",
            "GUNW LOS, GOFF range offset and GOFF along-track offset are separate metrics and must never be combined as if they shared one measurement axis.",
            "Pairwise candidate recurrence is screening evidence only; cumulative time series and velocity require a compatible, redundant, validated temporal network and reference.",
        ],
        "reason": reason,
    }


def _grid_key(dataset: rasterio.io.DatasetReader) -> tuple[Any, ...]:
    return (
        dataset.crs.to_string(),
        int(dataset.width),
        int(dataset.height),
        tuple(round(float(value), 9) for value in dataset.transform),
    )


def _read_metric_rasters(
    products: list[dict[str, Any]],
    output_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for product in products:
        family = str(product.get("product_type") or "").upper()
        if family not in {"GUNW", "GOFF"}:
            continue
        name = str(product.get("granule_name") or "")
        identity = _identity(name, family)
        if identity is None:
            rejected.append({"product_id": product.get("id"), "product_type": family,
                             "status": "REJECTED_UNPARSEABLE_IDENTITY",
                             "reason": "The exact product identity could not be parsed; cross-pair grouping would be unsafe."})
            continue
        exports = product.get("exports") if isinstance(product.get("exports"), list) else []
        if len(exports) != 1 or not isinstance(exports[0], dict):
            rejected.append({"product_id": product.get("id"), "product_type": family,
                             "status": "REJECTED_EXPORT_COUNT",
                             "reason": "Exactly one validated multi-band raster export is required per product."})
            continue
        try:
            raster_path = _safe_export_path(output_root, str(exports[0].get("relative_path") or ""))
            if not raster_path.is_file():
                raise ValueError("EXPORT_MISSING")
            with rasterio.open(raster_path) as ds:
                tags = ds.tags()
                if ds.crs is None or not ds.crs.is_projected or ds.crs.to_epsg() is None:
                    raise ValueError("PROJECTED_CRS_REQUIRED")
                if tags.get("aoi_name") != "custom" or str(tags.get("aoi_mask_applied", "")).lower() != "true":
                    raise ValueError("CUSTOM_AOI_MASK_NOT_PROVEN")
                if tags.get("grid_policy") != "common_aoi_lattice":
                    raise ValueError("COMMON_AOI_LATTICE_NOT_PROVEN")
                if tags.get("export_status") != "WRITTEN":
                    raise ValueError("EXPORT_STATUS_NOT_WRITTEN")
                if _source_stem(tags.get("source")) != _source_stem(name):
                    raise ValueError("EXPORT_SOURCE_IDENTITY_MISMATCH")
                if family == "GUNW":
                    if ds.count < 2:
                        raise ValueError("GUNW_REQUIRES_DISPLACEMENT_AND_COHERENCE_BANDS")
                    displacement = ds.read(1, masked=True).filled(np.nan).astype("float32")
                    coherence = ds.read(2, masked=True).filled(np.nan).astype("float32")
                    valid = np.isfinite(displacement) & np.isfinite(coherence) & (coherence >= 0.3)
                    metrics = [("GUNW_LOS_DISPLACEMENT_MM", displacement, valid)]
                    quality_description = "finite LOS displacement, finite coherence >= 0.3"
                else:
                    if ds.count < 3 or "layer2" not in str(tags.get("layer", "")).lower():
                        raise ValueError("GOFF_REQUIRES_LAYER2_RANGE_AZIMUTH_AND_CORRELATION")
                    range_offset = ds.read(1, masked=True).filled(np.nan).astype("float32")
                    azimuth_offset = ds.read(2, masked=True).filled(np.nan).astype("float32")
                    correlation = ds.read(3, masked=True).filled(np.nan).astype("float32")
                    corr_limit = max(0.3, _finite(tags.get("correlation_min")) or 0.3)
                    valid = np.isfinite(range_offset) & np.isfinite(azimuth_offset) & np.isfinite(correlation) & (correlation >= corr_limit)
                    metrics = [
                        ("GOFF_SLANT_RANGE_OFFSET_MM", range_offset, valid),
                        ("GOFF_ALONG_TRACK_OFFSET_MM", azimuth_offset, valid),
                    ]
                    quality_description = f"finite range/azimuth/correlation; correlation >= {corr_limit:g}"
                grid = _grid_key(ds)
                transform = ds.transform
                crs = ds.crs
                resolution = (abs(float(ds.res[0])), abs(float(ds.res[1])))
        except (OSError, ValueError, rasterio.errors.RasterioError) as exc:
            reason = str(exc)[:180] or type(exc).__name__
            rejected.append({"product_id": product.get("id"), "product_type": family,
                             "status": "REJECTED_RASTER_CONTRACT", "reason": reason})
            continue

        ref_date = str(product.get("reference_date") or tags.get("reference") or "")[:10]
        sec_date = str(product.get("secondary_date") or tags.get("secondary") or "")[:10]
        if not ref_date or not sec_date or sec_date <= ref_date:
            rejected.append({"product_id": product.get("id"), "product_type": family,
                             "status": "REJECTED_ACQUISITION_DATES",
                             "reason": "Valid, ordered reference and secondary dates are required."})
            continue
        network = (
            family, identity["processing"], identity["path"], identity["frame"], identity["direction"],
            identity["subswath"], identity["bandwidth"], identity["polarisation"], identity["crid"], grid,
        )
        for metric_name, values, valid_metric in metrics:
            accepted.append({
                "product": product, "product_id": str(product.get("id") or ""),
                "granule_name": name, "product_type": family,
                "metric": metric_name, "values": values, "valid": valid_metric,
                "identity": identity, "network_key": network, "grid": grid,
                "transform": transform, "crs": crs, "resolution": resolution,
                "reference_date": ref_date, "secondary_date": sec_date,
                "raster_path": raster_path, "valid_pixels": int(np.count_nonzero(valid_metric)),
                "quality_description": quality_description,
            })
    return accepted, rejected


def _score_pair(item: dict[str, Any], *, threshold_z: float, background_window_pixels: int) -> dict[str, Any]:
    values = item["values"]
    valid = item["valid"]
    valid_count = int(np.count_nonzero(valid))
    if valid_count < 200:
        return item | {"score_status": "INSUFFICIENT_VALID_PIXELS", "candidate_mask": np.zeros(valid.shape, dtype=bool),
                       "score": np.zeros(valid.shape, dtype="float32"), "robust_background_sigma": None,
                       "robust_local_sigma": None, "valid_pixels": valid_count}

    center = float(np.median(values[valid]))
    centered = values - center
    global_sigma = _robust_sigma(centered[valid])
    if global_sigma is None:
        return item | {"score_status": "INSUFFICIENT_ROBUST_BACKGROUND_SCALE", "candidate_mask": np.zeros(valid.shape, dtype=bool),
                       "score": np.zeros(valid.shape, dtype="float32"), "robust_background_sigma": None,
                       "robust_local_sigma": None, "valid_pixels": valid_count}

    window = int(max(5, background_window_pixels))
    if window % 2 == 0:
        window += 1
    max_window = max(3, min(values.shape))
    if max_window % 2 == 0:
        max_window -= 1
    window = min(window, max_window)
    if window < 3:
        return item | {"score_status": "INSUFFICIENT_SPATIAL_SUPPORT", "candidate_mask": np.zeros(valid.shape, dtype=bool),
                       "score": np.zeros(valid.shape, dtype="float32"), "robust_background_sigma": global_sigma,
                       "robust_local_sigma": None, "valid_pixels": valid_count}
    # Fill invalid pixels with the robust centre before filtering; invalid pixels
    # remain excluded in the final candidate mask.
    filled = np.where(valid, values, center).astype("float32", copy=False)
    local_background = median_filter(filled, size=window, mode="nearest")
    local_residual = values - local_background
    local_sigma = _robust_sigma(local_residual[valid])
    if local_sigma is None:
        return item | {"score_status": "INSUFFICIENT_ROBUST_LOCAL_SCALE", "candidate_mask": np.zeros(valid.shape, dtype=bool),
                       "score": np.zeros(valid.shape, dtype="float32"), "robust_background_sigma": global_sigma,
                       "robust_local_sigma": None, "valid_pixels": valid_count}

    z_global = np.abs(centered) / global_sigma
    z_local = np.abs(local_residual) / local_sigma
    score = np.maximum(z_global, z_local).astype("float32")
    score[~valid] = 0.0
    candidate_mask = valid & np.isfinite(score) & (score >= threshold_z)
    return item | {
        "score_status": "SCORED",
        "candidate_mask": candidate_mask,
        "score": score,
        "robust_background_sigma": global_sigma,
        "robust_local_sigma": local_sigma,
        "valid_pixels": valid_count,
        "background_median_mm": center,
        "candidate_pixels": int(np.count_nonzero(candidate_mask)),
        "threshold_robust_z": threshold_z,
        "background_window_pixels": window,
    }


def build_aoi_spatial_candidate_report(
    products: list[dict[str, Any]],
    output_root: Path,
    aoi_wkt_sha256: str | None,
    *,
    minimum_valid_pixels: int = 200,
    minimum_component_pixels: int = 4,
    minimum_repeat_pairs: int = 2,
    threshold_robust_z: float = 4.5,
    background_window_pixels: int = 11,
) -> dict[str, Any]:
    """Generate target-free spatial candidate polygons from retained raster exports."""
    output_root = output_root.resolve()
    report = _empty_report(
        "NOT_STARTED",
        "Candidate screen evaluates spatially unusual raster regions, not confirmed movement.",
        aoi_wkt_sha256,
    )
    try:
        accepted, rejected = _read_metric_rasters(products, output_root)
    except Exception as exc:
        report.update({
            "status": "UNAVAILABLE",
            "reason": f"{type(exc).__name__}: {str(exc)[:240]}",
            "rejected_products": [],
        })
        _write_outputs(output_root, report, [])
        return report

    report["rejected_products"] = rejected
    report["products_examined"] = len({item["product_id"] for item in accepted})
    if not accepted:
        report.update({
            "status": "NO_ELIGIBLE_RASTER_EXPORTS",
            "reason": "No retained raster satisfied the product identity, projection, AOI-mask, common-lattice and quality-band contracts.",
        })
        _write_outputs(output_root, report, [])
        return report

    accepted = [
        _score_pair(item, threshold_z=threshold_robust_z, background_window_pixels=background_window_pixels)
        for item in accepted
    ]
    report["product_metrics_examined"] = len(accepted)
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in accepted:
        groups[(item["network_key"], item["metric"])].append(item)

    all_features: list[dict[str, Any]] = []
    group_reports: list[dict[str, Any]] = []
    for group_key, rows in sorted(groups.items(), key=lambda pair: str(pair[0])):
        scored = [item for item in rows if item["score_status"] == "SCORED"]
        sample = rows[0]
        group_label = (
            f"{sample['product_type']} {sample['identity']['direction']} path {sample['identity']['path']} "
            f"frame {sample['identity']['frame']} subswath {sample['identity']['subswath']} "
            f"bandwidth {sample['identity']['bandwidth']} pol {sample['identity']['polarisation']} "
            f"CRID {sample['identity']['crid']} · {sample['metric']}"
        )
        unique_pairs = sorted({(item["reference_date"], item["secondary_date"]) for item in scored})
        if not scored:
            group_reports.append({
                "network": group_label, "status": "WITHHELD_INSUFFICIENT_ROBUST_SUPPORT",
                "pairs": len(rows), "reason": "No pair met the valid-pixel and robust-scale requirements.",
            })
            continue

        support = np.zeros(sample["valid"].shape, dtype="uint16")
        maximum_score = np.zeros(sample["valid"].shape, dtype="float32")
        product_ids_by_pair: dict[tuple[str, str], list[str]] = defaultdict(list)
        for item in scored:
            pair_key = (item["reference_date"], item["secondary_date"])
            # Each acquisition interval contributes at most one vote per cell.
            if pair_key in product_ids_by_pair:
                continue
            product_ids_by_pair[pair_key].append(item["product_id"])
            mask = item["candidate_mask"]
            support += mask.astype("uint16")
            maximum_score = np.maximum(maximum_score, item["score"] * mask.astype("float32"))

        labels, component_count = label(support > 0, structure=np.ones((3, 3), dtype=np.uint8))
        group_features: list[dict[str, Any]] = []
        for component_id in range(1, component_count + 1):
            component_mask = labels == component_id
            pixel_count = int(np.count_nonzero(component_mask))
            if pixel_count < minimum_component_pixels:
                continue
            support_values = support[component_mask]
            max_support = int(np.max(support_values))
            pair_support = sorted({pair for pair, ids in product_ids_by_pair.items()
                                   if ids and np.any(component_mask & np.logical_or.reduce([
                                       item["candidate_mask"] for item in scored
                                       if (item["reference_date"], item["secondary_date"]) == pair
                                   ]))})
            if not pair_support:
                continue
            geom_shapes = list(shapes(labels.astype("int32"), mask=component_mask, transform=sample["transform"], connectivity=8))
            if not geom_shapes:
                continue
            geometry = transform_geom(sample["crs"], "EPSG:4326", geom_shapes[0][0], precision=7)
            pixel_width, pixel_height = sample["resolution"]
            max_score = float(np.max(maximum_score[component_mask]))
            properties = {
                "network": group_label,
                "product_type": sample["product_type"],
                "metric": sample["metric"],
                "support_pairs": len(pair_support),
                "required_repeat_pairs": minimum_repeat_pairs,
                "max_pixel_pair_support": max_support,
                "pixel_count": pixel_count,
                "approx_area_m2": round(pixel_count * pixel_width * pixel_height, 2),
                "max_robust_score": round(max_score, 3),
                "product_ids": sorted({pid for pair in pair_support for pid in product_ids_by_pair[pair]}),
                "pair_intervals": [f"{a}/{b}" for a, b in pair_support],
                "status": "REPEATED_SPATIAL_CANDIDATE" if len(pair_support) >= minimum_repeat_pairs else "SINGLE_PAIR_CANDIDATE_UNCONFIRMED",
                "interpretation": "A candidate spatial anomaly requiring geophysical validation; not a movement or hazard declaration.",
            }
            feature = {"type": "Feature", "geometry": geometry, "properties": properties}
            group_features.append(feature)
            all_features.append(feature)

        group_reports.append({
            "network": group_label,
            "status": "CANDIDATES_FOUND_NEED_VALIDATION" if group_features else "NO_CANDIDATES_AT_SCREEN_THRESHOLD",
            "product_pairs": len(unique_pairs),
            "products_scored": len(scored),
            "candidate_features": len(group_features),
            "candidate_pixels": int(np.count_nonzero(support)),
            "repeated_pair_candidate_features": sum(f["properties"]["status"] == "REPEATED_SPATIAL_CANDIDATE" for f in group_features),
            "single_pair_unconfirmed_features": sum(f["properties"]["status"] == "SINGLE_PAIR_CANDIDATE_UNCONFIRMED" for f in group_features),
            "threshold_robust_z": threshold_robust_z,
            "minimum_valid_pixels": minimum_valid_pixels,
            "minimum_component_pixels": minimum_component_pixels,
            "robust_scale_source": "per-pair AOI-valid pixels; median/MAD; not an independently stable-ground measurement",
            "pair_results": [{
                "product_id": item["product_id"],
                "granule_name": item["granule_name"],
                "reference_date": item["reference_date"],
                "secondary_date": item["secondary_date"],
                "metric": item["metric"],
                "status": item["score_status"],
                "valid_pixels": item["valid_pixels"],
                "candidate_pixels": item.get("candidate_pixels", 0),
                "background_median_mm": _finite(item.get("background_median_mm")),
                "robust_background_sigma_mm": _finite(item.get("robust_background_sigma")),
                "robust_local_sigma_mm": _finite(item.get("robust_local_sigma")),
                "quality_mask": item["quality_description"],
            } for item in rows],
        })

    repeated_count = sum(
        feature["properties"]["status"] == "REPEATED_SPATIAL_CANDIDATE" for feature in all_features
    )
    report.update({
        "status": (
            "REPEATED_SPATIAL_CANDIDATES_NEED_GEOPHYSICAL_VALIDATION" if repeated_count
            else "SINGLE_PAIR_CANDIDATES_NEED_TEMPORAL_CONFIRMATION" if all_features
            else "NO_CANDIDATES_AT_CONFIGURED_THRESHOLD"
        ),
        "reason": (
            "At least one region is spatially unusual in more than one compatible pair; validate reference stability, uncertainty and temporal consistency before calling movement."
            if repeated_count else
            "Candidate regions were found in individual pairs, but no region met the configured repeated-pair support."
            if all_features else
            "No spatial components met the configured robust-score and minimum-area screen. This is not evidence of zero movement."
        ),
        "candidate_features": len(all_features),
        "products_examined": len({item["product_id"] for item in accepted}),
        "product_metrics_examined": len(accepted),
        "groups": group_reports,
        "features": all_features,
        "repeated_pair_candidate_features": repeated_count,
        "minimum_repeat_pairs": minimum_repeat_pairs,
        "threshold_robust_z": threshold_robust_z,
        "movement_confirmed": False,
        "hazard_detected": False,
    })
    _write_outputs(output_root, report, all_features)
    return report


def _write_outputs(output_root: Path, report: dict[str, Any], features: list[dict[str, Any]]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "aoi-displacement-candidates.json"
    geojson_path = output_root / "aoi-displacement-candidates.geojson"
    csv_path = output_root / "aoi-displacement-candidates.csv"
    # Remove in-memory raster arrays before JSON serialization.
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    geojson_path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "schema_version": "sarguardian-aoi-spatial-candidates/1.0",
            "aoi_wkt_sha256": report.get("aoi_wkt_sha256"),
            "movement_confirmed": False,
            "hazard_detected": False,
        },
    }, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    rows = [feature["properties"] for feature in features]
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        fields = ["network", "product_type", "metric", "status", "support_pairs", "pixel_count",
                  "approx_area_m2", "max_robust_score", "product_ids", "pair_intervals"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **row,
                "product_ids": ";".join(row.get("product_ids", [])),
                "pair_intervals": ";".join(row.get("pair_intervals", [])),
            })
