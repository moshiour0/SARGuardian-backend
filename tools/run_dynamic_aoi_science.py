#!/usr/bin/env python3
"""Build a provenance-first scientific analysis from already-retained AOI GeoTIFFs.

This adapter does not download raw NISAR data. It reuses the pinned SARGuardian
time-series, local-floor, inverse-velocity and (only when its assumptions fit)
geometry tools. A source-AOI-specific bound is deliberately not applied to an
arbitrary polygon. Scientific insufficiency is reported, not disguised as zero.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = "sarguardian-dynamic-aoi-science/1.0"
MIN_TARGET_PIXELS = 6
DEFAULT_COMMON_PIXELS = 200


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json_safe(row.get(key)) for key in fields})


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except (ValueError, TypeError):
            pass
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    return str(value)


def safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    candidate.relative_to(root.resolve())
    return candidate


def canonical_granule_name(value: Any) -> str:
    name = Path(str(value or "").strip()).name
    return name[:-3] if name.lower().endswith(".h5") else name




def parse_single_ring_wkt(value: str) -> list[tuple[float, float]]:
    match = re.fullmatch(r"\s*POLYGON\s*\(\(\s*(.*?)\s*\)\)\s*", str(value), flags=re.I)
    if not match:
        raise ValueError("Expected a single-ring WGS84 POLYGON WKT")
    ring = []
    for token in match.group(1).split(","):
        values = token.strip().split()
        if len(values) != 2:
            raise ValueError("Malformed AOI/reference WKT coordinate")
        lon, lat = float(values[0]), float(values[1])
        if not math.isfinite(lon) or not math.isfinite(lat) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("WKT coordinate is outside EPSG:4326 limits")
        ring.append((lon, lat))
    if len(ring) < 4 or ring[0] != ring[-1]:
        raise ValueError("WKT ring must have at least four coordinates and be closed")
    return ring


def point_in_ring(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    eps = 1e-10
    for index, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(index + 1) % len(ring)]
        cross = (lon - x1) * (y2 - y1) - (lat - y1) * (x2 - x1)
        if abs(cross) <= eps and min(x1, x2) - eps <= lon <= max(x1, x2) + eps and min(y1, y2) - eps <= lat <= max(y1, y2) + eps:
            return True
        if (y1 > lat) != (y2 > lat):
            x_cross = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_cross:
                inside = not inside
    return inside


def ring_centroid(ring: list[tuple[float, float]]) -> tuple[float, float]:
    """Planar vertex-polygon centroid for an AOI-sized area; fallback stays inside."""
    points = ring[:-1] if ring[0] == ring[-1] else ring
    cross_sum = 0.0
    cx_sum = 0.0
    cy_sum = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        cross = x1 * y2 - x2 * y1
        cross_sum += cross
        cx_sum += (x1 + x2) * cross
        cy_sum += (y1 + y2) * cross
    if abs(cross_sum) > 1e-15:
        point = (cx_sum / (3.0 * cross_sum), cy_sum / (3.0 * cross_sum))
        if point_in_ring(point[0], point[1], ring):
            return point
    lon_min, lon_max = min(x for x, _ in points), max(x for x, _ in points)
    lat_min, lat_max = min(y for _, y in points), max(y for _, y in points)
    candidates = [
        (lon_min + (lon_max - lon_min) * ix / 20.0,
         lat_min + (lat_max - lat_min) * iy / 20.0)
        for ix in range(1, 20) for iy in range(1, 20)
    ]
    centre = ((lon_min + lon_max) / 2.0, (lat_min + lat_max) / 2.0)
    eligible = [p for p in candidates if point_in_ring(p[0], p[1], ring)]
    if eligible:
        return min(eligible, key=lambda p: (p[0] - centre[0]) ** 2 + (p[1] - centre[1]) ** 2)
    for point in points:
        if point_in_ring(point[0], point[1], ring):
            return point
    raise ValueError("Could not choose an interior analysis point for this polygon")


def parse_date_value(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(?<!\d)(\d{8})(?!\d)", text)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            return None
    return None


def pair_dates(granule_name: str, product_record: dict[str, Any]) -> tuple[date, date]:
    stamps = re.findall(r"_(\d{8})T\d{6}", Path(granule_name).name)
    if len(stamps) >= 4:
        ref = datetime.strptime(stamps[0], "%Y%m%d").date()
        sec = datetime.strptime(stamps[2], "%Y%m%d").date()
    else:
        ref = parse_date_value(product_record.get("reference_date"))
        sec = parse_date_value(product_record.get("secondary_date"))
        if ref is None or sec is None:
            raise ValueError("PAIR_ACQUISITION_DATES_NOT_PARSEABLE")
    if sec <= ref:
        raise ValueError("PAIR_DATE_ORDER_INVALID")
    return ref, sec


def unit_scale_to_mm(family: str, description: str, unit: str) -> tuple[float | None, str]:
    description = str(description or "").strip().lower()
    unit = str(unit or "").strip().lower()
    if not unit:
        match = re.search(r"\((millimetres?|millimeters?|mm|metres?|meters?|m)\)\s*$", description)
        unit = match.group(1) if match else ""
    unit = unit.replace(" ", "")
    is_gunw = family == "GUNW"
    if is_gunw and not any(token in description for token in ("los", "displacement", "unwrapped")):
        return None, "GUNW_BAND1_NOT_IDENTIFIED_AS_LOS_DISPLACEMENT"
    if family == "GOFF" and not any(token in description for token in ("range", "slant", "offset")):
        return None, "GOFF_BAND1_NOT_IDENTIFIED_AS_RANGE_OFFSET"
    if unit in {"mm", "millimeter", "millimeters", "millimetre", "millimetres"}:
        return 1.0, "mm"
    if unit in {"m", "meter", "meters", "metre", "metres"}:
        return 1000.0, "m_to_mm"
    return None, "DISPLACEMENT_UNIT_UNKNOWN"


def load_export(record: dict[str, Any], export: dict[str, Any], out_root: Path,
                coherence_threshold: float) -> tuple[dict[str, Any] | None, str | None]:
    try:
        import numpy as np
        import rasterio
    except ImportError:
        return None, "NUMPY_RASTERIO_MISSING"

    family = str(record.get("product_type") or "").upper()
    if family not in {"GUNW", "GOFF"}:
        return None, "UNSUPPORTED_PRODUCT_FAMILY"
    granule_name = Path(str(record.get("granule_name") or "")).name
    if not granule_name:
        return None, "SOURCE_GRANULE_NAME_MISSING"
    if family == "GOFF":
        layer = str((record.get("stats") or {}).get("layer") or export.get("name") or "").lower()
        if "layer2" not in layer:
            return None, "GOFF_LAYER2_NOT_EXPLICIT"
    try:
        export_path = safe_child(out_root, str(export.get("relative_path") or ""))
    except (ValueError, OSError):
        return None, "EXPORT_PATH_OUTSIDE_RESULT_ROOT"
    if not export_path.is_file():
        return None, "EXPORT_FILE_MISSING"
    try:
        with rasterio.open(export_path) as source:
            if source.crs is None:
                return None, "RASTER_CRS_MISSING"
            if not source.crs.is_projected:
                return None, "RASTER_CRS_NOT_PROJECTED"
            if source.width <= 0 or source.height <= 0 or source.count < 1:
                return None, "RASTER_SCHEMA_INVALID"
            descs = list(source.descriptions or ())
            units = list(source.units or ())
            description = (descs[0] or "").strip()
            unit = (units[0] or "").strip() if units else ""
            scale, units_status = unit_scale_to_mm(family, description, unit)
            if scale is None:
                return None, units_status
            first = source.read(1, masked=True)
            displacement = np.asarray(first.filled(np.nan), dtype=np.float32) * np.float32(scale)
            valid = np.isfinite(displacement) & ~np.ma.getmaskarray(first)
            quality = None
            quality_description = "source reader export mask"
            if family == "GUNW":
                quality_indexes = [
                    i + 1 for i, name in enumerate(descs)
                    if name and "coherence" in name.lower()
                ]
                if not quality_indexes:
                    return None, "GUNW_COHERENCE_BAND_NOT_IDENTIFIED"
                quality_band = quality_indexes[0]
                quality_ma = source.read(quality_band, masked=True)
                quality = np.asarray(quality_ma.filled(np.nan), dtype=np.float32)
                valid &= np.isfinite(quality) & ~np.ma.getmaskarray(quality_ma) & (quality >= coherence_threshold)
                quality_description = f"coherence >= {coherence_threshold:g}"
            else:
                quality_indexes = [
                    i + 1 for i, name in enumerate(descs)
                    if name and any(token in name.lower() for token in ("correlation", "cross-correlation", "corr "))
                ]
                if quality_indexes:
                    quality_ma = source.read(quality_indexes[0], masked=True)
                    quality = np.asarray(quality_ma.filled(np.nan), dtype=np.float32)
                    valid &= np.isfinite(quality) & ~np.ma.getmaskarray(quality_ma)
                    quality_description = "reader export mask plus finite correlation values"

            displacement[~valid] = np.nan
            metadata = {
                "export_path": export_path,
                "export_name": export_path.name,
                "export_sha256": sha256_file(export_path),
                "family": family,
                "granule_name": granule_name,
                "product_id": str(record.get("id") or ""),
                "product_source_sha256": record.get("source_sha256"),
                "crs": source.crs,
                "transform": source.transform,
                "width": source.width,
                "height": source.height,
                "profile": source.profile.copy(),
                "tags": source.tags(),
                "data_mm": displacement,
                "valid": valid,
                "quality": quality,
                "quality_description": quality_description,
                "source_description": description,
                "source_units": unit or units_status,
                "unit_scale_to_mm": scale,
                "record": record,
                "export": export,
                "reference_date": None,
                "secondary_date": None,
            }
    except (OSError, ValueError, RuntimeError) as exc:
        return None, "RASTER_READ_FAILED:" + type(exc).__name__ + ":" + str(exc)[:180]

    try:
        import timeseries
        granule_meta = timeseries.granule_metadata(granule_name)
        if not granule_meta:
            return None, "SOURCE_GRANULE_IDENTITY_NOT_PARSEABLE"
        ref_date, sec_date = pair_dates(granule_name, record)
        if granule_meta["product"] != family:
            return None, "SOURCE_PRODUCT_FAMILY_MISMATCH"
        if str(granule_meta.get("crid") or "").upper() in {"", "UNKNOWN"}:
            return None, "SOURCE_CRID_UNKNOWN"
        pair = timeseries.Pair(
            path=granule_meta["path"], direction=granule_meta["direction"],
            ref=ref_date, sec=sec_date, value=None, n_px=0,
            coherence=None, source=granule_name, metadata=granule_meta,
        )
        metadata.update({"granule_meta": granule_meta, "pair": pair,
                         "reference_date": ref_date, "secondary_date": sec_date})
        return metadata, None
    except Exception as exc:
        return None, "PAIR_METADATA_INVALID:" + type(exc).__name__ + ":" + str(exc)[:180]


def align_raster(item: dict[str, Any], target_grid: dict[str, Any]) -> tuple[Any, Any, Any]:
    import numpy as np
    import rasterio
    from rasterio.warp import Resampling, reproject

    src_valid = item["valid"]
    src_values = np.where(src_valid, item["data_mm"], np.nan).astype(np.float32, copy=False)
    height, width = target_grid["height"], target_grid["width"]
    dest = np.full((height, width), np.nan, dtype=np.float32)
    reproject(
        source=src_values, destination=dest,
        src_transform=item["transform"], src_crs=item["crs"], src_nodata=np.nan,
        dst_transform=target_grid["transform"], dst_crs=target_grid["crs"], dst_nodata=np.nan,
        resampling=Resampling.bilinear, init_dest_nodata=True,
    )
    valid_dest = np.zeros((height, width), dtype=np.uint8)
    reproject(
        source=src_valid.astype(np.uint8), destination=valid_dest,
        src_transform=item["transform"], src_crs=item["crs"], src_nodata=0,
        dst_transform=target_grid["transform"], dst_crs=target_grid["crs"], dst_nodata=0,
        resampling=Resampling.nearest, init_dest_nodata=True,
    )
    dest[(valid_dest == 0) | ~np.isfinite(dest)] = np.nan
    quality_dest = None
    if item.get("quality") is not None:
        quality_dest = np.full((height, width), np.nan, dtype=np.float32)
        reproject(
            source=np.where(src_valid, item["quality"], np.nan).astype(np.float32, copy=False),
            destination=quality_dest,
            src_transform=item["transform"], src_crs=item["crs"], src_nodata=np.nan,
            dst_transform=target_grid["transform"], dst_crs=target_grid["crs"], dst_nodata=np.nan,
            resampling=Resampling.nearest, init_dest_nodata=True,
        )
        quality_dest[valid_dest == 0] = np.nan
    return dest, np.isfinite(dest), quality_dest


def geometry_on_grid(ring: list[tuple[float, float]], dst_crs: Any) -> dict[str, Any]:
    from rasterio.warp import transform_geom
    geometry = {"type": "Polygon", "coordinates": [[list(pair) for pair in ring]]}
    return transform_geom("EPSG:4326", dst_crs, geometry, precision=-1)


def common_reference_mask(common_mask: Any, grid: dict[str, Any],
                          target_lat: float, target_lon: float,
                          aoi_ring: list[tuple[float, float]],
                          reference_ring: list[tuple[float, float]] | None,
                          buffer_km: float) -> tuple[Any, dict[str, Any]]:
    import numpy as np
    from pyproj import Transformer
    from rasterio.features import geometry_mask
    from rasterio.transform import rowcol

    shape = common_mask.shape
    aoi_geom = geometry_on_grid(aoi_ring, grid["crs"])
    aoi_pixels = geometry_mask([aoi_geom], out_shape=shape, transform=grid["transform"],
                               invert=True, all_touched=False)
    common = common_mask & aoi_pixels
    to_grid = Transformer.from_crs("EPSG:4326", grid["crs"], always_xy=True)
    tx, ty = to_grid.transform(target_lon, target_lat)
    target_row, target_col = rowcol(grid["transform"], tx, ty)
    if target_row < 0 or target_col < 0 or target_row >= shape[0] or target_col >= shape[1]:
        return np.zeros(shape, dtype=bool), {"status": "TARGET_OUTSIDE_COMMON_GRID", "common_pixels": int(common.sum())}

    tr = grid["transform"]
    resolution_x = math.hypot(float(tr.a), float(tr.d))
    resolution_y = math.hypot(float(tr.b), float(tr.e))
    if not math.isfinite(resolution_x) or not math.isfinite(resolution_y) or resolution_x <= 0 or resolution_y <= 0:
        return np.zeros(shape, dtype=bool), {"status": "GRID_RESOLUTION_INVALID", "common_pixels": int(common.sum())}

    rows, cols = np.indices(shape)
    px_x = tr.c + (cols + 0.5) * tr.a + (rows + 0.5) * tr.b
    px_y = tr.f + (cols + 0.5) * tr.d + (rows + 0.5) * tr.e
    excluded = ((px_x - tx) ** 2 + (px_y - ty) ** 2) <= (buffer_km * 1000.0) ** 2

    if reference_ring is not None:
        ref_geom = geometry_on_grid(reference_ring, grid["crs"])
        reference_pixels = geometry_mask([ref_geom], out_shape=shape, transform=tr,
                                          invert=True, all_touched=False)
        reference = common & reference_pixels & ~excluded
        mode = "USER_DECLARED_REFERENCE_POLYGON_UNVERIFIED"
    else:
        reference = common & ~excluded
        mode = "PROVISIONAL_COMMON_AOI_PIXELS_OUTSIDE_TARGET_BUFFER"

    return reference, {
        "status": "READY" if int(reference.sum()) > 0 else "NO_REFERENCE_PIXELS",
        "reference_mode": mode,
        "common_aoi_pixels": int(common.sum()),
        "reference_pixels": int(reference.sum()),
        "target_buffer_km": float(buffer_km),
        "target_grid_row_col": [int(target_row), int(target_col)],
        "grid_crs": str(grid["crs"]),
        "grid_transform": [float(v) for v in tr[:6]],
        "grid_size": [int(shape[1]), int(shape[0])],
    }


def write_normalized_input(item: dict[str, Any], dest: Path, aoi_name: str) -> None:
    import numpy as np
    import rasterio

    dest.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(item["profile"])
    profile.update({
        "driver": "GTiff", "count": 1, "dtype": "float32", "nodata": float("nan"),
        "compress": "deflate", "predictor": 3,
    })
    data = np.where(item["valid"], item["data_mm"], np.nan).astype(np.float32, copy=False)
    with rasterio.open(dest, "w", **profile) as output:
        output.write(data, 1)
        output.set_band_description(1, "LOS displacement (mm)" if item["family"] == "GUNW" else "Slant range offset (mm)")
        output.set_band_unit(1, "mm")
        tags = dict(item.get("tags") or {})
        granule = item["granule_name"]
        meta = item["granule_meta"]
        tags.update({
            "aoi_name": aoi_name,
            "aoi_mask_applied": "true",
            "aoi_mask_evidence": "source product derived-output validation passed; normalized analysis copy only",
            "source": granule,
            "source_product": granule,
            "source_granule": granule,
            "source_granule_sha256": str(item.get("product_source_sha256") or ""),
            "source_export_sha256": item["export_sha256"],
            "crid": str(meta["crid"]),
            "maturity": str(item["record"].get("science_maturity") or item["record"].get("maturity") or "UNKNOWN"),
            "layer": "layer2" if item["family"] == "GOFF" else "GUNW",
            "series_id": item["pair"].network_label(short=True),
            "units_normalized_to": "mm",
        })
        output.update_tags(**{str(k): str(v) for k, v in tags.items() if v is not None})


def stable_group_id(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()[:12]


def write_series_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["geometry", "component", "epoch", "days_from_start", "cumulative_mm", "error_mm"]
    write_csv(path, fields, rows)


def plot_series(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    if not rows:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    from datetime import datetime as dt_datetime

    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["geometry"]), int(row["component"])), []).append(row)
    fig, axis = plt.subplots(figsize=(11, 5.5))
    for (geometry, component), series_rows in sorted(grouped.items()):
        series_rows = sorted(series_rows, key=lambda row: row["epoch"])
        x = [dt_datetime.strptime(row["epoch"], "%Y-%m-%d") for row in series_rows]
        y = [float(row["cumulative_mm"]) for row in series_rows]
        available = [(idx, float(row["error_mm"])) for idx, row in enumerate(series_rows)
                     if row.get("error_mm") is not None and math.isfinite(float(row["error_mm"]))]
        label = f"{geometry} · component {component}"
        axis.plot(x, y, marker="o", label=label)
        if available:
            axis.errorbar([x[idx] for idx, _ in available],
                          [y[idx] for idx, _ in available],
                          yerr=[err for _, err in available], fmt="none", capsize=3)
    axis.set_ylabel("Relative cumulative displacement (mm, LOS/range)")
    axis.set_xlabel("Observation date")
    axis.set_title(title + "\ncomponents are independent; error bars are residual-based where defined")
    axis.grid(True, alpha=0.25)
    axis.legend(loc="best", fontsize=7)
    fig.autofmt_xdate()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def run_local_floor(science_root: Path, input_dir: Path, item_group: list[dict[str, Any]],
                    target: tuple[float, float], out_dir: Path, family: str,
                    aoi_wkt: str, target_id: str, radius: int) -> dict[str, Any]:
    group_id = stable_group_id(item_group[0]["pair"].network_label(short=True))
    normalized_dir = out_dir / "inputs" / f"{family.lower()}_custom_{group_id}"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    for item in item_group:
        ref_date, sec_date = item["reference_date"], item["secondary_date"]
        meta = item["granule_meta"]
        proc = str(meta["processing"])
        crid = str(meta["crid"])
        suffix = f"{proc}_{meta['path']}_{meta['direction']}_{meta['frame']}_{meta['subswath']}_{crid}"
        layer_part = "layer2_" if family == "GOFF" else ""
        filename = f"{family}_{ref_date:%Y%m%d}_{sec_date:%Y%m%d}_{layer_part}{suffix}.tif"
        write_normalized_input(item, normalized_dir / filename, "custom")

    match = "layer2" if family == "GOFF" else "GUNW"
    details = out_dir / "local-floors" / f"{family.lower()}_{group_id}_details.csv"
    floors = out_dir / "local-floors" / f"{family.lower()}_{group_id}_floors.csv"
    log = out_dir / "logs" / f"{family.lower()}_{group_id}_local_floor.log"
    argv = [
        sys.executable, str(science_root / "src" / "local_floor.py"),
        "--dir", str(normalized_dir), "--aoi", "custom",
        "--lat", f"{target[0]:.10f}", "--lon", f"{target[1]:.10f}",
        "--band", "1", "--radius", str(radius), "--match", match,
        "--csv", str(details), "--as-floors", str(floors),
    ]
    env = dict(os.environ)
    env["SARGUARDIAN_AOI_WKT"] = aoi_wkt
    done = subprocess.run(argv, cwd=science_root, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=900, check=False)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(done.stdout or "", encoding="utf-8")
    floor_rows = []
    if floors.is_file():
        with floors.open(newline="", encoding="utf-8-sig") as stream:
            floor_rows = list(csv.DictReader(stream))
    usable_floor_rows = [
        row for row in floor_rows
        if str(row.get("series_id") or "").strip()
        and math.isfinite(float(row.get("detect_floor_mm_day") or "nan"))
        and float(row.get("detect_floor_mm_day") or "nan") > 0
    ]
    return {
        "status": "PASS" if done.returncode == 0 and usable_floor_rows else "INSUFFICIENT_DATA",
        "exit_code": done.returncode,
        "command": argv,
        "log": str(log.relative_to(out_dir)),
        "details_csv": str(details.relative_to(out_dir)) if details.is_file() else None,
        "floors_csv": str(floors.relative_to(out_dir)) if floors.is_file() else None,
        "floors_count": len(usable_floor_rows),
        "error": None if done.returncode == 0 and usable_floor_rows else
                 ((done.stdout or "")[-1000:] or "No usable geometry-scoped local floor rows were produced."),
    }


def run_inverse_velocity(science_root: Path, series_csv: Path, floor_csv: Path,
                         out_dir: Path, family: str, latest_date: date,
                         aoi_wkt: str, group_id: str) -> dict[str, Any]:
    plot_path = out_dir / "inverse-velocity" / f"{family.lower()}_{group_id}.png"
    log_path = out_dir / "logs" / f"{family.lower()}_{group_id}_inverse_velocity.log"
    argv = [
        sys.executable, str(science_root / "src" / "inverse_velocity.py"),
        "--ts", str(series_csv), "--floors", str(floor_csv),
        "--floors-layer", "layer2" if family == "GOFF" else "GUNW",
        "--forecast-cutoff", (latest_date + timedelta(days=1)).isoformat(),
        "--plot", str(plot_path),
    ]
    env = dict(os.environ)
    env["SARGUARDIAN_AOI_WKT"] = aoi_wkt
    try:
        done = subprocess.run(argv, cwd=science_root, env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=900, check=False)
        output = done.stdout or ""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output, encoding="utf-8")
        lower = output.lower()
        fired = bool(re.search(r"(?m)^\s*alarm\s*:", output, flags=re.I))
        if done.returncode != 0:
            status = "INSUFFICIENT_DATA" if any(k in lower for k in (
                "insufficient", "no rows", "no floor", "missing", "cannot use floor"
            )) else "FAIL"
        elif fired:
            status = "CANDIDATE_FOR_REVIEW"
        elif "no alarm" in lower:
            status = "NO_QUALIFYING_ACCELERATION_OR_INSUFFICIENT_INTERVALS"
        else:
            status = "COMPLETED_REVIEW_LOG"
        return {
            "status": status,
            "actionability": "RESEARCH_ONLY_NOT_AN_OPERATIONAL_ALERT",
            "exit_code": done.returncode,
            "forecast_cutoff": (latest_date + timedelta(days=1)).isoformat(),
            "used_event_date": False,
            "command": argv,
            "log": str(log_path.relative_to(out_dir)),
            "plot": str(plot_path.relative_to(out_dir)) if plot_path.is_file() else None,
            "candidate_line_detected": fired,
            "output_tail": output[-1800:],
        }
    except subprocess.TimeoutExpired as exc:
        tail = (exc.stdout or b"").decode("utf-8", errors="replace")[-1000:] if isinstance(exc.stdout, bytes) else str(exc.stdout or "")[-1000:]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("TIMEOUT\n" + tail, encoding="utf-8")
        return {"status": "FAIL", "actionability": "RESEARCH_ONLY_NOT_AN_OPERATIONAL_ALERT",
                "error": "INVERSE_VELOCITY_TIMEOUT", "log": str(log_path.relative_to(out_dir))}


def run_geometry_merge(science_root: Path, family_csv: Path, family: str,
                       available_labels: list[str], target: tuple[float, float],
                       reference_mode: str, aoi_wkt: str, out_dir: Path) -> dict[str, Any]:
    if reference_mode != "USER_DECLARED_REFERENCE_POLYGON_UNVERIFIED":
        return {"status": "NOT_EVALUATED_PROVISIONAL_REFERENCE",
                "reason": "A single user-declared spatial reference polygon is required before comparing projected series across geometries."}
    if len(available_labels) < 2:
        return {"status": "NOT_EVALUATED_SINGLE_GEOMETRY",
                "reason": "At least two independently measured look geometries are required for the multi-geometry interpretation stage."}
    try:
        sys.path.insert(0, str(science_root / "src"))
        import geometry_merge
        unknown = [label for label in available_labels if geometry_merge.match_track(label) is None]
        if unknown:
            return {"status": "NOT_EVALUATED_UNSUPPORTED_TRACK",
                    "unsupported_geometry_labels": unknown,
                    "reason": "The current geometry_merge.py uses a finite nominal track table that does not include every observed track."}
    except Exception as exc:
        return {"status": "NOT_EVALUATED_GEOMETRY_IMPORT_FAILED",
                "error": type(exc).__name__ + ":" + str(exc)[:200]}
    csv_path = out_dir / "geometry" / f"{family.lower()}_downslope_projection.csv"
    log_path = out_dir / "logs" / f"{family.lower()}_geometry_merge.log"
    argv = [
        sys.executable, str(science_root / "src" / "geometry_merge.py"),
        "--merge", "--ts", str(family_csv), "--lat", f"{target[0]:.10f}",
        "--lon", f"{target[1]:.10f}", "--csv", str(csv_path),
    ]
    env = dict(os.environ)
    env["SARGUARDIAN_AOI_WKT"] = aoi_wkt
    try:
        done = subprocess.run(argv, cwd=science_root, env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=1200, check=False)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(done.stdout or "", encoding="utf-8")
        return {
            "status": "PASS" if done.returncode == 0 and csv_path.is_file() else "FAIL",
            "output_csv": str(csv_path.relative_to(out_dir)) if csv_path.is_file() else None,
            "log": str(log_path.relative_to(out_dir)),
            "exit_code": done.returncode,
            "interpretation": "Nominal-track projection onto DEM downslope; not a 3-D decomposition or a single combined continuous series.",
        }
    except subprocess.TimeoutExpired:
        return {"status": "FAIL", "error": "GEOMETRY_MERGE_TIMEOUT"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    import numpy as np
    import rasterio
    from pyproj import Transformer
    from rasterio.features import geometry_mask
    from rasterio.transform import rowcol
    from rasterio.warp import Resampling, reproject

    out_root = args.out_root.resolve()
    out_dir = out_root / "science-analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.manifest.resolve()
    report_path = args.processing_report.resolve()
    manifest = read_json(manifest_path)
    processing_report = read_json(report_path)
    products = processing_report.get("products")
    if not isinstance(products, list):
        raise ValueError("PROCESSING_REPORT_PRODUCTS_MISSING")
    manifest_products = manifest.get("products")
    if not isinstance(manifest_products, list):
        raise ValueError("RUN_MANIFEST_PRODUCTS_MISSING")
    manifest_by_id = {str(row.get("id") or ""): row for row in manifest_products if isinstance(row, dict)}
    if not manifest_by_id or "" in manifest_by_id:
        raise ValueError("RUN_MANIFEST_PRODUCT_IDS_INVALID")
    report_by_id = {str(row.get("id") or ""): row for row in products if isinstance(row, dict)}
    if len(report_by_id) != len(products) or set(report_by_id) != set(manifest_by_id):
        raise ValueError("PROCESSING_REPORT_PRODUCT_SET_MISMATCH")
    for product_id, manifest_product in manifest_by_id.items():
        report_product = report_by_id[product_id]
        if canonical_granule_name(manifest_product.get("granule_name")) != canonical_granule_name(report_product.get("granule_name")):
            raise ValueError(f"PROCESSING_REPORT_GRANULE_MISMATCH product_id={product_id}")
        if str(manifest_product.get("product_type") or "").upper() != str(report_product.get("product_type") or "").upper():
            raise ValueError(f"PROCESSING_REPORT_FAMILY_MISMATCH product_id={product_id}")
    aoi_wkt = str(manifest.get("aoi_wkt") or "").strip()
    if not aoi_wkt:
        raise ValueError("AOI_WKT_MISSING_FROM_MANIFEST")
    aoi_ring = parse_single_ring_wkt(aoi_wkt)
    science_root = args.science_root.resolve()

    os.environ["SARGUARDIAN_AOI_WKT"] = aoi_wkt
    science_src = str(science_root / "src")
    if science_src not in sys.path:
        sys.path.insert(0, science_src)
    import timeseries

    if (args.target_lat is None) != (args.target_lon is None):
        raise ValueError("TARGET_COORDINATES_REQUIRE_BOTH_LAT_AND_LON")
    if args.target_lat is None:
        target_lon, target_lat = ring_centroid(aoi_ring)
        target_source = "AUTO_AOI_INTERIOR_CENTRE_NOT_USER_SELECTED"
    else:
        target_lat, target_lon = float(args.target_lat), float(args.target_lon)
        target_source = "USER_SUPPLIED_TARGET"
    if not (-90 <= target_lat <= 90 and -180 <= target_lon <= 180):
        raise ValueError("TARGET_COORDINATE_OUT_OF_RANGE")
    target_inside_aoi = point_in_ring(target_lon, target_lat, aoi_ring)
    if not target_inside_aoi:
        raise ValueError("TARGET_OUTSIDE_EXACT_AOI_POLYGON")
    reference_ring = parse_single_ring_wkt(args.reference_wkt) if args.reference_wkt else None
    reference_mode = ("USER_DECLARED_REFERENCE_POLYGON_UNVERIFIED"
                      if reference_ring else "PROVISIONAL_COMMON_AOI_PIXELS_OUTSIDE_TARGET_BUFFER")

    result = {
        "schema_version": SCHEMA,
        "status": "INSUFFICIENT_DATA",
        "scope": "dynamic custom AOI; retained AOI-clipped exports only; no raw HDF5 downloaded",
        "science_commit": str(manifest.get("science_commit") or ""),
        "aoi_wkt_sha256": hashlib.sha256(aoi_wkt.encode("utf-8")).hexdigest(),
        "target": {"lat": target_lat, "lon": target_lon, "selection_method": target_source,
                   "inside_exact_aoi": target_inside_aoi},
        "reference": {"mode": reference_mode,
                      "wkt_sha256": hashlib.sha256(args.reference_wkt.encode("utf-8")).hexdigest() if args.reference_wkt else None,
                      "not_independently_verified_stable": True,
                      "buffer_km": args.buffer_km,
                      "minimum_common_reference_pixels": args.min_common_pixels},
        "stages": {},
        "pair_inventory_csv": "science-analysis/pair-inventory.csv",
        "series": {"GUNW": [], "GOFF": []},
        "local_detection_floors": [],
        "inverse_velocity": [],
        "geometry": [],
        "event_specific_bound": {"status": "NOT_APPLICABLE_GENERIC_AOI",
                                 "reason": "bound.py uses fixed 26-Aug-2026 source-event parameters and source-AOI candidates; it is deliberately not run for arbitrary WKT."},
        "scientific_warning": "A computed series is relative to its stated datum. A provisional or user-declared reference is not independently certified stable ground. This research result is not an operational warning.",
        "errors": [],
        "warnings": [],
    }
    if reference_ring is None:
        result["warnings"].append("NO_REFERENCE_POLYGON_SUPPLIED: auto common-pixel datum is provisional and cannot support an operational warning.")

    loaded = []
    rejected = []
    for record in products:
        if str(record.get("status") or "").upper() not in {"PASS", "WARNING"}:
            rejected.append({"product_id": record.get("id"), "granule_name": record.get("granule_name"),
                             "status": "PRODUCT_NOT_VALIDATED", "reason": str(record.get("status") or "UNKNOWN")})
            continue
        if not record.get("science_pixel_support"):
            rejected.append({"product_id": record.get("id"), "granule_name": record.get("granule_name"),
                             "status": "NO_SCIENCE_PIXEL_SUPPORT", "reason": "Validated structure without finite band-1 science pixels"})
            continue
        exports = record.get("exports") or []
        if len(exports) != 1:
            rejected.append({"product_id": record.get("id"), "granule_name": record.get("granule_name"),
                             "status": "AMBIGUOUS_EXPORT_COUNT", "reason": f"Expected 1 pair raster, got {len(exports)}"})
            continue
        item, issue = load_export(record, exports[0], out_root, args.coherence_threshold)
        if issue:
            rejected.append({"product_id": record.get("id"), "granule_name": record.get("granule_name"),
                             "status": "EXPORT_NOT_ELIGIBLE", "reason": issue})
            continue
        item["pair"].value = None
        loaded.append(item)
    result["stages"]["export_inventory"] = {
        "status": "PASS" if loaded else "INSUFFICIENT_DATA",
        "products_in_report": len(products), "eligible_pair_exports": len(loaded),
        "rejected_count": len(rejected), "rejected": rejected,
        "source": "aoi-processing-report.json exports; source TIFFs read-only",
    }
    if not loaded:
        result["errors"].append("NO_ELIGIBLE_PAIR_EXPORTS")
        result["rejected_products"] = rejected
        write_csv(out_dir / "pair-inventory.csv",
                  ["product_id", "granule_name", "status", "reason"], rejected)
        write_json(out_dir / "analysis-manifest.json", {
            "schema_version": SCHEMA, "aoi_wkt_sha256": result["aoi_wkt_sha256"],
            "science_commit": result["science_commit"], "source_processing_report_sha256": sha256_file(report_path),
            "target": result["target"], "reference": result["reference"], "eligible_pair_exports": 0,
        })
        write_json(out_dir / "analysis-report.json", result)
        write_json(out_dir / "series.json", {"schema_version": SCHEMA, "status": result["status"], "series": []})
        return result

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for item in loaded:
        grouped.setdefault(item["pair"].network_key(), []).append(item)

    inventory_rows: list[dict[str, Any]] = []
    series_rows_by_family: dict[str, list[dict[str, Any]]] = {"GUNW": [], "GOFF": []}
    series_objects: list[dict[str, Any]] = []
    groups_for_downstream: list[dict[str, Any]] = []
    common_reference_ok = 0
    groups_processed = 0
    for key, group in sorted(grouped.items(), key=lambda value: str(value[0])):
        group.sort(key=lambda item: (item["reference_date"], item["secondary_date"], item["granule_name"]))
        label = group[0]["pair"].network_label(short=True)
        family = group[0]["family"]
        gid = stable_group_id(label)
        duplicate_pairs: dict[tuple[date, date], list[dict[str, Any]]] = {}
        for item in group:
            duplicate_pairs.setdefault((item["reference_date"], item["secondary_date"]), []).append(item)
        conflict_pairs = {pair: values for pair, values in duplicate_pairs.items() if len(values) > 1}
        if conflict_pairs:
            reason = "DUPLICATE_VARIANT_OR_RELEASE_ON_SAME_PAIR_REQUIRES_EXPLICIT_RESOLUTION"
            result["warnings"].append(f"{label}: {reason}")
            for item in group:
                inventory_rows.append({
                    "product_id": item["product_id"], "granule_name": item["granule_name"],
                    "family": family, "geometry": label, "reference_date": item["reference_date"].isoformat(),
                    "secondary_date": item["secondary_date"].isoformat(), "status": "BLOCKED",
                    "reason": reason, "source_export_sha256": item["export_sha256"],
                })
            continue

        grid_item = group[0]
        if not grid_item["crs"].is_projected:
            result["warnings"].append(f"{label}: non-projected grid blocked")
            continue
        grid = {"crs": grid_item["crs"], "transform": grid_item["transform"],
                "width": grid_item["width"], "height": grid_item["height"]}
        aligned_data, aligned_valid, aligned_quality = [], [], []
        for item in group:
            try:
                data, valid, quality = align_raster(item, grid)
                aligned_data.append(data)
                aligned_valid.append(valid)
                aligned_quality.append(quality)
            except Exception as exc:
                result["warnings"].append(f"{item['granule_name']}: grid alignment failed: {type(exc).__name__}: {str(exc)[:120]}")
                aligned_data.append(np.full((grid["height"], grid["width"]), np.nan, dtype=np.float32))
                aligned_valid.append(np.zeros((grid["height"], grid["width"]), dtype=bool))
                aligned_quality.append(None)
        common = np.logical_and.reduce(aligned_valid) if aligned_valid else np.zeros((grid["height"], grid["width"]), dtype=bool)
        reference_mask, ref_metrics = common_reference_mask(
            common, grid, target_lat, target_lon, aoi_ring, reference_ring, args.buffer_km
        )
        ref_pixels = int(reference_mask.sum())
        enough_reference = ref_metrics.get("status") == "READY" and ref_pixels >= args.min_common_pixels
        ref_metrics["status"] = "READY" if enough_reference else "INSUFFICIENT_COMMON_REFERENCE_PIXELS"
        group_report = {
            "group_id": gid, "family": family, "geometry": label, "pair_count": len(group),
            "reference": ref_metrics, "reference_eligible": enough_reference,
            "pairs_used": 0, "components": [], "time_series_status": "NOT_EVALUATED",
            "local_floor": None, "inverse_velocity": [],
        }
        if not enough_reference:
            for item in group:
                inventory_rows.append({
                    "product_id": item["product_id"], "granule_name": item["granule_name"],
                    "family": family, "geometry": label, "reference_date": item["reference_date"].isoformat(),
                    "secondary_date": item["secondary_date"].isoformat(), "status": "INSUFFICIENT_COMMON_REFERENCE_PIXELS",
                    "reference_pixels": ref_pixels, "source_export_sha256": item["export_sha256"],
                })
            groups_for_downstream.append({"family": family, "label": label, "gid": gid, "items": group,
                                          "group_report": group_report})
            result["warnings"].append(f"{label}: {ref_pixels} common reference pixels; minimum is {args.min_common_pixels}")
        else:
            common_reference_ok += 1
            target_x, target_y = Transformer.from_crs("EPSG:4326", grid["crs"], always_xy=True).transform(target_lon, target_lat)
            target_row, target_col = rowcol(grid["transform"], target_x, target_y)
            radius = int(args.target_radius_px)
            rows_index, cols_index = np.indices((grid["height"], grid["width"]))
            in_window = ((rows_index >= max(0, target_row - radius)) &
                         (rows_index < min(grid["height"], target_row + radius + 1)) &
                         (cols_index >= max(0, target_col - radius)) &
                         (cols_index < min(grid["width"], target_col + radius + 1)))
            measurements = []
            for item, data, valid, quality in zip(group, aligned_data, aligned_valid, aligned_quality):
                offset = float(np.median(data[reference_mask]))
                relative = data - offset
                target_valid = valid & in_window & np.isfinite(relative)
                n = int(target_valid.sum())
                value = float(np.median(relative[target_valid])) if n >= MIN_TARGET_PIXELS else None
                if value is not None:
                    item["pair"].value = value
                    item["pair"].n_px = n
                    item["pair"].coherence = (
                        float(np.nanmedian(quality[target_valid]))
                        if quality is not None and np.isfinite(quality[target_valid]).any() else None
                    )
                measurements.append({
                    "item": item, "offset": offset, "value": value,
                    "target_px": n, "quality": item["quality_description"],
                })
                inventory_rows.append({
                    "product_id": item["product_id"], "granule_name": item["granule_name"],
                    "family": family, "geometry": label,
                    "reference_date": item["reference_date"].isoformat(),
                    "secondary_date": item["secondary_date"].isoformat(),
                    "pair_span_days": (item["secondary_date"] - item["reference_date"]).days,
                    "status": "MEASURED" if value is not None else "NO_VALID_TARGET_WINDOW",
                    "relative_pair_measurement_mm": value,
                    "reference_offset_removed_mm": offset,
                    "target_valid_pixels": n, "reference_pixels": ref_pixels,
                    "mean_support_metric": item["pair"].coherence,
                    "quality_gate": item["quality_description"],
                    "unit_conversion": item["source_units"],
                    "source_export": item["export_name"], "source_export_sha256": item["export_sha256"],
                    "source_granule_sha256": item["product_source_sha256"],
                })
            measured_pairs = [item["pair"] for item in group if item["pair"].value is not None]
            group_report["pairs_used"] = len(measured_pairs)
            if measured_pairs:
                components = timeseries.connected_components(measured_pairs)
                group_series_rows = []
                for component_index, epochs in enumerate(components, 1):
                    comp_pairs = [pair for pair in measured_pairs if pair.ref in epochs and pair.sec in epochs]
                    n_unknowns = len(epochs) - 1
                    dof = len(comp_pairs) - n_unknowns
                    comp_info = {
                        "component": component_index, "epochs": [epoch.isoformat() for epoch in epochs],
                        "pairs": len(comp_pairs), "unknowns": n_unknowns, "degrees_of_freedom": dof,
                    }
                    if dof < 0:
                        comp_info.update({"status": "UNDERDETERMINED_NETWORK", "uncertainty": "UNAVAILABLE"})
                        group_report["components"].append(comp_info)
                        continue
                    inversion = timeseries.invert_component(comp_pairs, epochs)
                    if "error" in inversion:
                        comp_info.update({"status": "INVERSION_FAILED", "error": inversion["error"]})
                        group_report["components"].append(comp_info)
                        continue
                    first_epoch = inversion["epochs"][0]
                    comp_rows = []
                    for epoch, value, error in zip(inversion["epochs"], inversion["cumulative_mm"], inversion["error_mm"]):
                        value_f = float(value)
                        error_f = float(error) if error is not None else float("nan")
                        row = {
                            "geometry": label, "component": component_index, "epoch": epoch.isoformat(),
                            "days_from_start": (epoch - first_epoch).days,
                            "cumulative_mm": round(value_f, 5),
                            "error_mm": round(error_f, 5) if math.isfinite(error_f) else None,
                        }
                        comp_rows.append(row)
                        series_rows_by_family[family].append(row)
                        group_series_rows.append(row)
                    comp_info.update({
                        "status": "PASS" if dof > 0 else "EXACTLY_DETERMINED_NO_RESIDUAL_UNCERTAINTY",
                        "residual_rms_mm": json_safe(float(inversion["residual_rms_mm"])),
                        "sigma_mm": json_safe(float(inversion["sigma_mm"])),
                        "linear_velocity_mm_per_day": json_safe(float(inversion["velocity_mm_per_day"])),
                        "linear_velocity_error_mm_per_day": json_safe(float(inversion["velocity_err_mm_per_day"])),
                        "series_rows": comp_rows,
                        "uncertainty": "RESIDUAL_BASED" if dof > 0 else "UNDEFINED_NO_REDUNDANCY",
                    })
                    group_report["components"].append(comp_info)
                    series_objects.append({
                        "id": f"{family.lower()}-{gid}-component-{component_index}",
                        "family": family, "geometry": label, "component": component_index,
                        "status": comp_info["status"], "units": "mm",
                        "component_zero": epochs[0].isoformat(),
                        "reference_mode": reference_mode,
                        "uncertainty": comp_info["uncertainty"],
                        "n_pairs": len(comp_pairs), "n_epochs": len(epochs), "dof": dof,
                        "residual_rms_mm": json_safe(float(inversion["residual_rms_mm"])),
                        "rows": comp_rows,
                    })
                group_report["time_series_status"] = (
                    "PASS" if any(component["status"] == "PASS" for component in group_report["components"])
                    else ("EXACTLY_DETERMINED_NO_RESIDUAL_UNCERTAINTY" if group_report["components"] and
                          any(c["status"] == "EXACTLY_DETERMINED_NO_RESIDUAL_UNCERTAINTY" for c in group_report["components"])
                          else "INSUFFICIENT_DATA")
                )
                if not group_series_rows:
                    result["warnings"].append(f"{label}: temporal network did not produce a publishable series")
                group_series_path = out_dir / "group-series" / f"{family.lower()}_{gid}.csv"
                write_series_csv(group_series_path, group_series_rows)
                group_report["series_csv"] = str(group_series_path.relative_to(out_dir)) if group_series_rows else None
            else:
                group_report["time_series_status"] = "NO_VALID_TARGET_MEASUREMENTS"
                result["warnings"].append(f"{label}: no pair has enough valid pixels in the target window")
            groups_for_downstream.append({"family": family, "label": label, "gid": gid, "items": group,
                                          "group_report": group_report})
            groups_processed += 1

    for family, family_rows in series_rows_by_family.items():
        family_rows.sort(key=lambda row: (row["geometry"], int(row["component"]), row["epoch"]))
        write_series_csv(out_dir / f"time-series-{family.lower()}.csv", family_rows)
        plot_series(out_dir / f"time-series-{family.lower()}.png", family_rows,
                    f"{family} relative displacement time series")

    floor_results = []
    inverse_results = []
    for item_group in groups_for_downstream:
        family, label, gid = item_group["family"], item_group["label"], item_group["gid"]
        group_report = item_group["group_report"]
        # Local floors are useful even if common-reference support was inadequate:
        # the result is detection capability, not a movement time series.
        floors = run_local_floor(science_root, out_root, item_group["items"],
                                 (target_lat, target_lon), out_dir, family,
                                 aoi_wkt, "auto-centre" if target_source.startswith("AUTO_") else "target",
                                 args.target_radius_px)
        group_report["local_floor"] = floors
        floor_results.append({"family": family, "geometry": label, **floors})
        floor_path_text = floors.get("floors_csv")
        series_path_text = group_report.get("series_csv")
        forecast_eligible_components = [
            component for component in group_report.get("components", [])
            if component.get("status") == "PASS" and component.get("degrees_of_freedom", 0) > 0
        ]
        if floor_path_text and series_path_text and forecast_eligible_components:
            series_path = out_dir / series_path_text
            # A network/component has to retain its own floor file and series key;
            # the source detector checks series_id+CRID instead of dates alone.
            latest = max(item["secondary_date"] for item in item_group["items"])
            forecast = run_inverse_velocity(
                science_root, series_path, out_dir / floor_path_text, out_dir,
                family, latest, aoi_wkt, gid,
            )
            inverse_results.append({"family": family, "geometry": label, **forecast})
            group_report["inverse_velocity"].append(forecast)
        else:
            skip_reason = (
                "NO_GEOMETRY_SCOPED_LOCAL_FLOOR" if not floor_path_text else
                "NO_REDUNDANT_INVERTED_SERIES" if not forecast_eligible_components else
                "INVERSE_VELOCITY_PREREQUISITES_NOT_MET"
            )
            skipped = {"status": "NOT_EVALUATED", "reason": skip_reason,
                       "actionability": "RESEARCH_ONLY_NOT_AN_OPERATIONAL_ALERT"}
            inverse_results.append({"family": family, "geometry": label, **skipped})
            group_report["inverse_velocity"].append(skipped)

    geometry_results = []
    for family in ("GUNW", "GOFF"):
        labels = sorted({entry["geometry"] for entry in series_objects if entry["family"] == family})
        family_csv = out_dir / f"time-series-{family.lower()}.csv"
        if labels and family_csv.is_file():
            geometry_result = run_geometry_merge(
                science_root, family_csv, family, labels, (target_lat, target_lon),
                reference_mode, aoi_wkt, out_dir,
            )
        else:
            geometry_result = {"status": "NOT_EVALUATED_NO_VALID_TIME_SERIES"}
        geometry_results.append({"family": family, **geometry_result})

    passed_components = sum(
        1 for item in series_objects if item["status"] == "PASS" and item.get("dof", 0) > 0
    )
    if not series_objects:
        result_status = "INSUFFICIENT_DATA"
    elif reference_ring is None or passed_components == 0:
        result_status = "PARTIAL"
    else:
        result_status = "PASS"
    result.update({
        "status": result_status,
        "groups": [entry["group_report"] for entry in groups_for_downstream],
        "series": {"GUNW": [item for item in series_objects if item["family"] == "GUNW"],
                   "GOFF": [item for item in series_objects if item["family"] == "GOFF"]},
        "rejected_products": rejected,
        "pair_inventory_count": len(inventory_rows),
        "eligible_pair_exports": len(loaded),
        "groups_evaluated": groups_processed,
        "groups_with_reference": common_reference_ok,
        "series_component_count": len(series_objects),
        "series_components_with_residual_uncertainty": passed_components,
        "local_detection_floors": floor_results,
        "inverse_velocity": inverse_results,
        "geometry": geometry_results,
        "reference": {
            **result["reference"],
            "status": "USER_DECLARED_UNVERIFIED" if reference_ring else "PROVISIONAL",
        },
    })
    result["stages"]["spatial_reference_and_time_series"] = {
        "status": "PASS" if passed_components else "INSUFFICIENT_DATA",
        "groups_evaluated": groups_processed, "groups_with_reference": common_reference_ok,
        "components_with_redundant_fit": passed_components,
        "notes": [
            "Grid alignment uses rasterio reprojection; source GeoTIFFs are never modified.",
            "All values are referenced to a common pixel set inside the AOI and outside the target buffer/reference polygon.",
            "A provisional reference is not independently known stable ground.",
            "Disconnected network components retain independent zeros and are not concatenated.",
            "Residual-based uncertainties are undefined for exactly determined networks.",
        ],
    }
    result["stages"]["local_detection_floor"] = {
        "status": "PASS" if any(item.get("status") == "PASS" for item in floor_results) else "INSUFFICIENT_DATA",
        "groups_with_usable_floors": sum(item.get("floors_count", 0) > 0 for item in floor_results),
    }
    result["stages"]["inverse_velocity"] = {
        "status": "COMPLETED_RESEARCH_GATES" if inverse_results else "NOT_EVALUATED",
        "candidate_for_review_count": sum(item.get("status") == "CANDIDATE_FOR_REVIEW" for item in inverse_results),
        "operational_alerts": 0,
        "notes": "A fitted candidate is a research result only; stability, thresholds, historical holdouts and false-alarm rates have not been operationally calibrated.",
    }
    result["stages"]["geometry_merge"] = {
        "status": "PARTIAL" if any(item.get("status") == "PASS" for item in geometry_results) else "NOT_EVALUATED_OR_UNSUPPORTED",
        "per_family": geometry_results,
    }
    result["analysis_outputs"] = {
        "pair_inventory": "science-analysis/pair-inventory.csv",
        "gunw_series_csv": "science-analysis/time-series-gunw.csv",
        "goff_series_csv": "science-analysis/time-series-goff.csv",
        "series_json": "science-analysis/series.json",
        "manifest": "science-analysis/analysis-manifest.json",
        "report": "science-analysis/analysis-report.json",
    }
    write_csv(out_dir / "pair-inventory.csv", [
        "product_id", "granule_name", "family", "geometry", "reference_date", "secondary_date",
        "pair_span_days", "status", "reason", "relative_pair_measurement_mm",
        "reference_offset_removed_mm", "target_valid_pixels", "reference_pixels",
        "mean_support_metric", "quality_gate", "unit_conversion",
        "source_export", "source_export_sha256", "source_granule_sha256",
    ], inventory_rows)
    analysis_manifest = {
        "schema_version": SCHEMA,
        "run_id": manifest.get("run_id"),
        "workflow_sha": manifest.get("orchestration_sha") or manifest.get("orchestration_commit"),
        "science_commit": result["science_commit"],
        "source_manifest_sha256": sha256_file(manifest_path),
        "source_processing_report_sha256": sha256_file(report_path),
        "aoi_wkt_sha256": result["aoi_wkt_sha256"],
        "date_window": {key: manifest.get(key) for key in ("start_date", "end_date", "date_filter_mode")},
        "target": result["target"], "reference": result["reference"],
        "reader_policy": {"GUNW_coherence_threshold": args.coherence_threshold,
                          "min_common_reference_pixels": args.min_common_pixels,
                          "target_radius_px": args.target_radius_px},
        "science_script_sha256": {
            name: sha256_file(science_root / "src" / name)
            for name in ("timeseries.py", "local_floor.py", "inverse_velocity.py", "geometry_merge.py", "bound.py")
            if (science_root / "src" / name).is_file()
        },
        "source_exports": [{"product_id": item["product_id"], "source_granule": item["granule_name"],
                            "source_sha256": item["product_source_sha256"], "export": item["export_name"],
                            "export_sha256": item["export_sha256"]} for item in loaded],
    }
    write_json(out_dir / "analysis-manifest.json", analysis_manifest)
    write_json(out_dir / "series.json", {
        "schema_version": SCHEMA, "status": result_status,
        "reference_mode": reference_mode, "target": result["target"],
        "scientific_warning": result["scientific_warning"],
        "series": series_objects,
    })
    result["analysis_manifest"] = "science-analysis/analysis-manifest.json"
    result["series_json"] = "science-analysis/series.json"
    write_json(out_dir / "analysis-report.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--processing-report", type=Path, required=True)
    parser.add_argument("--science-root", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--expected-science-commit", default="")
    parser.add_argument("--target-lat", type=float)
    parser.add_argument("--target-lon", type=float)
    parser.add_argument("--reference-wkt", default="")
    parser.add_argument("--buffer-km", type=float, default=2.0)
    parser.add_argument("--min-common-pixels", type=int, default=DEFAULT_COMMON_PIXELS)
    parser.add_argument("--target-radius-px", type=int, default=6)
    parser.add_argument("--coherence-threshold", type=float, default=0.3)
    args = parser.parse_args()

    out_dir = args.out_root.resolve() / "science-analysis"
    try:
        if args.min_common_pixels < 6:
            raise ValueError("MIN_COMMON_PIXELS_MUST_BE_AT_LEAST_6")
        if args.target_radius_px < 1 or args.buffer_km < 0:
            raise ValueError("TARGET_RADIUS_AND_BUFFER_MUST_BE_NON_NEGATIVE")
        if not 0 < args.coherence_threshold <= 1:
            raise ValueError("COHERENCE_THRESHOLD_MUST_BE_IN_(0,1]")
        if args.expected_science_commit:
            expected = args.expected_science_commit.strip().lower()
            input_manifest = read_json(args.manifest.resolve())
            if str(input_manifest.get("science_commit") or "").strip().lower() != expected:
                raise ValueError("MANIFEST_SCIENCE_COMMIT_MISMATCH")
            commit = subprocess.run(
                ["git", "-C", str(args.science_root.resolve()), "rev-parse", "HEAD"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            actual = commit.stdout.strip().lower()
            if commit.returncode or actual != expected:
                raise ValueError(f"PINNED_SCIENCE_COMMIT_MISMATCH expected={expected} actual={actual or 'UNKNOWN'}")
        if bool(args.reference_wkt.strip()):
            parse_single_ring_wkt(args.reference_wkt)
        result = run(args)
        print(f"DYNAMIC_AOI_SCIENCE_STATUS={result['status']}")
        print(f"DYNAMIC_AOI_SCIENCE_ELIGIBLE_EXPORTS={result.get('eligible_pair_exports', 0)}")
        print(f"DYNAMIC_AOI_SCIENCE_SERIES_COMPONENTS={result.get('series_component_count', 0)}")
        print(f"DYNAMIC_AOI_SCIENCE_OPERATIONAL_ALERTS=0")
        return 0
    except Exception as exc:
        failure = {
            "schema_version": SCHEMA, "status": "FAIL",
            "errors": [{"type": type(exc).__name__, "detail": str(exc)[:600]}],
            "scientific_warning": "Scientific analysis failed or was blocked; this does not erase otherwise-valid retained product outputs.",
            "operational_alerts": 0,
        }
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            write_json(out_dir / "analysis-report.json", failure)
            write_json(out_dir / "analysis-manifest.json", {
                "schema_version": SCHEMA, "status": "FAIL",
                "error_type": type(exc).__name__, "error": str(exc)[:600],
            })
            write_json(out_dir / "series.json", {"schema_version": SCHEMA, "status": "FAIL", "series": []})
        except Exception:
            pass
        print(f"DYNAMIC_AOI_SCIENCE_STATUS=FAIL")
        print(f"DYNAMIC_AOI_SCIENCE_ERROR={type(exc).__name__}:{str(exc)[:300]}")
        # Deliberately return success so a science-stage failure cannot skip
        # the already-validated result archive/Drive upload/callback contract.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
