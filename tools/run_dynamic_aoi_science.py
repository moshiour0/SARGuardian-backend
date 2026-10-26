#!/usr/bin/env python3
"""Run the guarded, AOI-scoped science stages on retained derived GeoTIFFs.

This adapter intentionally does not re-download source HDF5. It imports the
pinned science repository's network inversion and robust noise-floor routines,
uses only exact AOI-clipped exports, preserves network components, and records
why geometry fusion/forecasting/bounds are unavailable instead of inventing
missing evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "sarguardian-dynamic-aoi-science-engine/1.0"
MIN_COMMON_PIXELS = 6
MAX_PIXEL_SERIES_PER_COMPONENT = 256
REFERENCE_BUFFER_METRES = 1000.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path, required: bool = True) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"required JSON is missing: {path}")
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def parse_wkt_ring(value: str) -> list[tuple[float, float]]:
    m = re.fullmatch(r"\s*POLYGON\s*\(\(\s*(.*?)\s*\)\)\s*", value, re.I)
    if not m:
        raise ValueError("Expected already-validated single-ring WGS84 POLYGON WKT")
    ring = []
    for token in m.group(1).split(","):
        xy = token.split()
        if len(xy) != 2:
            raise ValueError("Malformed WKT coordinate")
        lon, lat = float(xy[0]), float(xy[1])
        if not math.isfinite(lon) or not math.isfinite(lat) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError("WKT coordinate is outside EPSG:4326 limits")
        ring.append((lon, lat))
    if len(ring) < 4 or ring[0] != ring[-1]:
        raise ValueError("WKT ring must be closed")
    return ring


def point_in_ring(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        crosses = (y1 > lat) != (y2 > lat)
        if crosses:
            x_at_y = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < x_at_y:
                inside = not inside
    return inside


def record_product_files(root: Path, summary: dict[str, Any], science_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    import numpy as np
    import rasterio

    src_path = science_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from timeseries import Pair, granule_metadata

    records: list[dict[str, Any]] = []
    errors: list[str] = []
    product_root = root / "product-data"
    if not product_root.is_dir():
        return [], ["PRODUCT_DATA_DIRECTORY_MISSING"]

    for record_path in sorted(product_root.glob("*/product-record.json")):
        try:
            record = read_json(record_path)
            if record.get("status") not in {"PASS", "WARNING"}:
                raise ValueError("product record is not structurally validated")
            family = str(record.get("product_type", "")).upper()
            if family not in {"GUNW", "GOFF"}:
                raise ValueError("unsupported product family")
            export = next((x for x in record.get("exports", [])
                           if str(x.get("relative_path", "")).lower().endswith(".tif")), None)
            if not export:
                raise ValueError("no retained GeoTIFF export")
            tif = (root / str(export["relative_path"])).resolve()
            tif.relative_to(root.resolve())
            if not tif.is_file():
                raise FileNotFoundError("retained GeoTIFF missing")

            granule = str(record.get("granule_name", "")).strip()
            if not granule:
                raise ValueError("full NISAR granule identity missing")
            granule_source = granule if granule.lower().endswith(".h5") else granule + ".h5"
            metadata = granule_metadata(granule_source)
            if not metadata or str(metadata.get("product", "")).upper() != family:
                raise ValueError("pinned science parser cannot validate NISAR product identity")

            ref = date.fromisoformat(str(record["reference_date"]))
            sec = date.fromisoformat(str(record["secondary_date"]))
            if sec <= ref:
                raise ValueError("secondary acquisition must follow reference acquisition")
            stamps = re.findall(r"_(\d{8})T\d{6}", granule)
            if len(stamps) < 4:
                raise ValueError("granule timestamp identity is incomplete")
            parsed_ref = datetime.strptime(stamps[0], "%Y%m%d").date()
            parsed_sec = datetime.strptime(stamps[2], "%Y%m%d").date()
            if (ref, sec) != (parsed_ref, parsed_sec):
                raise ValueError("manifest acquisition dates disagree with NISAR granule timestamps")

            with rasterio.open(tif) as ds:
                tags = ds.tags()
                if ds.crs is None or ds.count < (3 if family == "GOFF" else 2):
                    raise ValueError("export has missing CRS or required science/quality bands")
                if str(tags.get("aoi_mask_applied", "")).lower() != "true":
                    raise ValueError("export does not prove exact AOI masking")
                if str(tags.get("aoi_name", "")) != str(summary.get("aoi_name", "")):
                    raise ValueError("export AOI metadata does not match the run summary")
                source_tag = Path(str(tags.get("source", ""))).name
                if source_tag and source_tag.removesuffix(".h5") != granule.removesuffix(".h5"):
                    raise ValueError("export source granule does not match product record")
                value = ds.read(1).astype("float64")
                quality_band = 3 if family == "GOFF" else 2
                quality = ds.read(quality_band).astype("float64")
                threshold = float(tags.get("correlation_min" if family == "GOFF" else "coherence_min", "0.3"))
                valid = np.isfinite(value) & np.isfinite(quality) & (quality >= threshold)
                if ds.nodata is not None and math.isfinite(float(ds.nodata)):
                    valid &= value != float(ds.nodata)
                transform = ds.transform
                crs = ds.crs
                shape = ds.shape
                descriptions = list(ds.descriptions)
                exported_hash = sha256(tif)

            pair = Pair(
                path=int(metadata["path"]),
                direction=str(metadata["direction"]),
                ref=ref,
                sec=sec,
                value=None,
                n_px=int(valid.sum()),
                coherence=float(np.median(quality[valid])) if valid.any() else None,
                source=granule_source,
                metadata=metadata,
            )
            records.append({
                "record": record, "pair": pair, "family": family, "track": str((record.get("stats") or {}).get("track") or pair.network_label()),
                "raster": tif, "values": value, "quality": quality, "valid": valid,
                "transform": transform, "crs": crs, "shape": shape,
                "descriptions": descriptions, "export_sha256": exported_hash,
                "threshold": threshold, "source_sha256": record.get("source_sha256"),
            })
        except Exception as exc:
            errors.append(f"{record_path.parent.name}:{type(exc).__name__}:{str(exc)[:220]}")
    return records, errors


def run_engine(root: Path, science_root: Path) -> dict[str, Any]:
    import numpy as np
    import rasterio
    from rasterio.transform import rowcol
    from pyproj import Transformer

    science_src = science_root / "src"
    if str(science_src) not in sys.path:
        sys.path.insert(0, str(science_src))
    from timeseries import Pair, connected_components, invert_component
    from local_floor import compare as compare_floor, detection_floor

    root = root.resolve()
    out = root / "science-engine"
    out.mkdir(parents=True, exist_ok=True)
    summary_path = root / "aoi-run-summary.json"
    summary = read_json(summary_path)
    report: dict[str, Any] = {
        "schema_version": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": summary.get("run_id"),
        "aoi_name": summary.get("aoi_name"),
        "aoi_wkt_sha256": summary.get("aoi_wkt_sha256"),
        "science_commit_expected": summary.get("science_commit"),
        "stages": {},
        "network_components": [],
        "warnings": [],
        "errors": [],
        "outputs": {},
        "scientific_scope": {
            "reference_policy": "Per-pair median on common valid AOI support is removed when no explicit target is supplied; these are spatially relative diagnostics, not absolute ground displacement.",
            "target_reference_policy": "When target coordinates are provided, each pair uses the median of common valid pixels outside a 1 km target buffer. Stable-ground assumption is unverified and reported.",
            "prohibitions": [
                "Never join disconnected temporal components.",
                "Never mix GUNW phase-derived LOS with GOFF range offsets.",
                "Never merge ascending/descending tracks without product LOS vectors and compatible epochs.",
                "Never forecast without a validated target series, enough intervals and per-pair noise-floor gates.",
                "Never run the source-event bound on arbitrary WKT AOIs.",
            ],
        },
    }

    actual = subprocess.run(
        ["git", "-C", str(science_root), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False, timeout=30,
    )
    report["science_commit_actual"] = (actual.stdout or "").strip()
    if actual.returncode or report["science_commit_actual"] != report["science_commit_expected"]:
        report["status"] = "FAIL_SCIENCE_COMMIT_MISMATCH"
        report["errors"].append({
            "problem": "SCIENCE_COMMIT_MISMATCH",
            "expected": report["science_commit_expected"],
            "actual": report["science_commit_actual"],
        })
        (root / "science-engine-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    products, input_errors = record_product_files(root, summary, science_root)
    report["input_products"] = [{
        "id": x["record"].get("id"), "family": x["family"], "track": x["track"],
        "reference_date": str(x["pair"].ref), "secondary_date": str(x["pair"].sec),
        "valid_pixels": int(x["valid"].sum()), "export_sha256": x["export_sha256"],
        "raw_source_sha256": x["source_sha256"],
    } for x in products]
    if input_errors:
        report["errors"].extend(input_errors)
        report["warnings"].append("ONE_OR_MORE_PRODUCTS_EXCLUDED_FROM_SCIENCE_ENGINE")
    if not products:
        report["status"] = "FAIL_NO_VALIDATED_TIFF_INPUTS"
        report["errors"].append("No validated AOI-clipped raster input could be used.")
        (root / "science-engine-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report

    target = summary.get("analysis_target")
    target_lat = target_lon = None
    target_valid = False
    if isinstance(target, dict) and target.get("latitude") not in (None, "") and target.get("longitude") not in (None, ""):
        target_lat, target_lon = float(target["latitude"]), float(target["longitude"])
        ring = parse_wkt_ring(str(summary.get("aoi_wkt", "")))
        target_valid = -90 <= target_lat <= 90 and -180 <= target_lon <= 180 and point_in_ring(target_lon, target_lat, ring)
        if not target_valid:
            report["errors"].append("ANALYSIS_TARGET_OUTSIDE_AOI_OR_INVALID")
            target_lat = target_lon = None
        else:
            report["analysis_target"] = {"latitude": target_lat, "longitude": target_lon, "inside_aoi": True}
    else:
        report["analysis_target"] = None
        report["warnings"].append("NO_ANALYSIS_TARGET_COORDINATES: local target floor and inverse-velocity forecast are gated off.")

    # The science parser supplies the exact temporal graph logic. Track/network identity
    # includes family, orbit direction/path and NISAR footprint/release identity.
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for item in products:
        groups[(item["family"], item["pair"].network_key())].append(item)

    network_rows: list[dict[str, Any]] = []
    pixel_series_rows: list[dict[str, Any]] = []
    local_floor_rows: list[dict[str, Any]] = []
    target_series_outputs: list[dict[str, Any]] = []
    target_floor_catalogue: dict[str, dict[tuple[date, date], float]] = defaultdict(dict)
    geometry_inputs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    common_support_total = 0
    component_total = 0

    for group_key, group_items in sorted(groups.items(), key=lambda kv: str(kv[0])):
        pairs = [x["pair"] for x in group_items]
        item_by_pair = {id(x["pair"]): x for x in group_items}
        components = connected_components(pairs)
        family = group_items[0]["family"]
        track = group_items[0]["track"]
        for comp_idx, epochs in enumerate(components, 1):
            component_total += 1
            inside = [x for x in group_items if x["pair"].ref in epochs and x["pair"].sec in epochs]
            n_pairs = len(inside)
            n_epochs = len(epochs)
            n_unknowns = max(0, n_epochs - 1)
            redundancy = n_pairs - n_unknowns
            comp_id = f"{family}:{track}:component-{comp_idx}"
            base = inside[0]
            grid_ok = all(
                x["shape"] == base["shape"] and x["crs"] == base["crs"]
                and tuple(x["transform"]) == tuple(base["transform"])
                for x in inside
            )
            row: dict[str, Any] = {
                "component_id": comp_id, "family": family, "track": track,
                "direction": base["pair"].direction, "path": base["pair"].path,
                "epochs": [str(x) for x in epochs], "n_pairs": n_pairs, "n_epochs": n_epochs,
                "n_unknowns": n_unknowns, "redundancy_dof": redundancy,
                "pairs": [{"id": x["record"].get("id"), "reference": str(x["pair"].ref),
                           "secondary": str(x["pair"].sec), "span_days": x["pair"].span_days,
                           "raw_source_sha256": x["source_sha256"], "export_sha256": x["export_sha256"]}
                          for x in sorted(inside, key=lambda y: y["pair"].sec)],
                "grid_aligned": grid_ok,
                "reference_policy": "pending",
            }
            if not grid_ok:
                row.update(status="SKIPPED_GRID_MISMATCH", common_valid_pixels=0, sampled_pixels=0)
                report["network_components"].append(row)
                network_rows.append(row)
                continue
            common = np.logical_and.reduce([x["valid"] for x in inside])
            common_count = int(common.sum())
            common_support_total += common_count
            row["common_valid_pixels_all_pairs"] = common_count
            if common_count < MIN_COMMON_PIXELS:
                row.update(status="INSUFFICIENT_COMMON_SUPPORT", common_valid_pixels=common_count, sampled_pixels=0)
                row["reference_policy"] = "No common valid pixel support; no inversion performed."
                report["network_components"].append(row)
                network_rows.append(row)
                continue

            # Conservative common-support spatial reference. For a target run, remove
            # a 1 km buffer from the reference mask so the target is not its own datum.
            ref_mask = common.copy()
            ref_method = "common-support spatial median proxy; not verified stable ground"
            if target_valid:
                x, y = Transformer.from_crs("EPSG:4326", base["crs"], always_xy=True).transform(target_lon, target_lat)
                rr, cc = rowcol(base["transform"], x, y)
                px_x = max(abs(float(base["transform"].a)), 1e-9)
                px_y = max(abs(float(base["transform"].e)), 1e-9)
                yy, xx = np.ogrid[:common.shape[0], :common.shape[1]]
                dist2 = ((xx - cc) * px_x) ** 2 + ((yy - rr) * px_y) ** 2
                ref_mask &= dist2 > REFERENCE_BUFFER_METRES ** 2
                ref_method = "common valid pixels outside 1 km target buffer; stability assumed, not independently verified"
            ref_count = int(ref_mask.sum())
            row["reference_pixels"] = ref_count
            row["reference_policy"] = ref_method
            if ref_count < MIN_COMMON_PIXELS:
                row.update(status="INSUFFICIENT_REFERENCE_SUPPORT", common_valid_pixels=common_count, sampled_pixels=0)
                report["network_components"].append(row)
                network_rows.append(row)
                continue

            pair_fields = []
            pair_reference_medians = {}
            for item in sorted(inside, key=lambda y: y["pair"].sec):
                vals = item["values"]
                ref_median = float(np.median(vals[ref_mask]))
                pair_reference_medians[item["record"]["id"]] = ref_median
                pair_fields.append((item, vals - ref_median))

                span = item["pair"].span_days
                # The source local_floor primitive is used for the spatial scatter
                # floor. In the absence of target coordinates this is explicitly
                # AOI-wide, not mislabeled as a target detection threshold.
                floor_aoi = detection_floor(vals[item["valid"]], span)
                local_value = None
                local_ci_low = local_ci_high = None
                local_count = 0
                if target_valid:
                    tr, tc = rowcol(base["transform"], x, y)
                    radius = 5
                    r0, r1 = max(0, tr-radius), min(vals.shape[0], tr+radius+1)
                    c0, c1 = max(0, tc-radius), min(vals.shape[1], tc+radius+1)
                    local_window = vals[r0:r1, c0:c1]
                    local_mask = item["valid"][r0:r1, c0:c1]
                    local_clean = np.where(local_mask, local_window, np.nan)
                    local_count = int(local_mask.sum())
                    floor_comparison = compare_floor(np.where(item["valid"], vals, np.nan), local_clean, span)
                    if floor_comparison.get("usable"):
                        local_value = float(floor_comparison["local_floor_mm_day"])
                        local_ci_low = float(floor_comparison["local_floor_ci_lo"])
                        local_ci_high = float(floor_comparison["local_floor_ci_hi"])
                        target_floor_catalogue[track][(item["pair"].ref, item["pair"].sec)] = local_value
                local_floor_rows.append({
                    "component_id": comp_id, "family": family, "track": track,
                    "product_id": item["record"].get("id"), "reference": str(item["pair"].ref),
                    "secondary": str(item["pair"].sec), "span_days": span,
                    "valid_aoi_pixels": int(item["valid"].sum()), "common_pixels": common_count,
                    "reference_pixels": ref_count, "aoi_spatial_scatter_floor_mm_day": floor_aoi,
                    "target_window_valid_pixels": local_count, "target_local_floor_mm_day": local_value,
                    "target_floor_ci95_low_mm_day": local_ci_low, "target_floor_ci95_high_mm_day": local_ci_high,
                    "floor_method": "3 * 1.4826 * MAD / pair span; local floor uses pinned local_floor.compare",
                    "interpretation": ("target-window diagnostic; source pixels and reference stability require scientific review"
                                       if target_valid else "AOI spatial-scatter proxy only; not a local target noise floor"),
                })

            # Invert pixel-relative pair observations through the pinned timeseries module.
            # Sampling is deterministic/capped for storage; pixel_stack remains the full
            # raster screening step and is reported independently in the final bundle.
            flat_indices = np.flatnonzero(common)
            if flat_indices.size > MAX_PIXEL_SERIES_PER_COMPONENT:
                positions = np.linspace(0, flat_indices.size - 1, MAX_PIXEL_SERIES_PER_COMPONENT, dtype=int)
                flat_indices = flat_indices[positions]
            row["sampled_pixels"] = int(flat_indices.size)
            row["status"] = (
                "EXACTLY_DETERMINED_NO_ERROR_ESTIMATE" if redundancy <= 0
                else "REDUNDANT_NETWORK_DIAGNOSTIC_ONLY"
            )
            row["dof_warning"] = (
                "No residual degrees of freedom: inversion cannot estimate residual variance/error."
                if redundancy <= 0 else "Redundancy exists; inspect residuals and independent validation."
            )
            for flat in flat_indices:
                rr, cc = np.unravel_index(int(flat), common.shape)
                pixel_pairs = []
                for item, centered in pair_fields:
                    if not np.isfinite(centered[rr, cc]):
                        continue
                    p = item["pair"]
                    pixel_pairs.append(Pair(
                        path=p.path, direction=p.direction, ref=p.ref, sec=p.sec,
                        value=float(centered[rr, cc]), n_px=1, coherence=None,
                        source=p.source,
                    ))
                if not pixel_pairs:
                    continue
                pixel_result = invert_component(pixel_pairs, epochs)
                if "error" in pixel_result:
                    continue
                try:
                    gx, gy = rasterio.transform.xy(base["transform"], rr, cc, offset="center")
                    lon, lat = Transformer.from_crs(base["crs"], "EPSG:4326", always_xy=True).transform(gx, gy)
                except Exception:
                    lon = lat = None
                pixel_id = f"{comp_id}:r{rr}:c{cc}"
                for ep, displacement, error in zip(
                    pixel_result["epochs"], pixel_result["cumulative_mm"], pixel_result["error_mm"]
                ):
                    pixel_series_rows.append({
                        "component_id": comp_id, "pixel_id": pixel_id, "family": family, "track": track,
                        "longitude": lon, "latitude": lat, "epoch": str(ep),
                        "cumulative_relative_mm": float(displacement),
                        "error_mm": float(error) if np.isfinite(error) else None,
                        "redundancy_dof": int(pixel_result["dof"]),
                        "reference_policy": ref_method,
                    })

            # Explicit target time series, using the median in a local window relative to
            # a shared outside-buffer reference. This is diagnostic unless the reference
            # area is independently known to be stable.
            if target_valid:
                target_pairs = []
                missing_target_pairs = []
                for item, _centered in pair_fields:
                    tr, tc = rowcol(base["transform"], x, y)
                    radius = 5
                    r0, r1 = max(0, tr-radius), min(item["values"].shape[0], tr+radius+1)
                    c0, c1 = max(0, tc-radius), min(item["values"].shape[1], tc+radius+1)
                    m = item["valid"][r0:r1, c0:c1]
                    values = item["values"][r0:r1, c0:c1]
                    if int(m.sum()) < MIN_COMMON_PIXELS:
                        missing_target_pairs.append(item["record"].get("id"))
                        continue
                    measured = float(np.median(values[m])) - pair_reference_medians[item["record"]["id"]]
                    p = item["pair"]
                    target_pairs.append(Pair(path=p.path, direction=p.direction, ref=p.ref, sec=p.sec,
                                             value=measured, n_px=int(m.sum()), coherence=None, source=p.source))
                if not missing_target_pairs and len(target_pairs) == len(inside):
                    target_result = invert_component(target_pairs, epochs)
                    target_row = {
                        "component_id": comp_id, "family": family, "track": track,
                        "target_latitude": target_lat, "target_longitude": target_lon,
                        "reference_policy": ref_method, "reference_pixels": ref_count,
                        "n_pairs": len(target_pairs), "n_epochs": len(target_result.get("epochs", [])),
                        "redundancy_dof": target_result.get("dof"),
                        "status": "EXACTLY_DETERMINED_NO_ERROR_ESTIMATE" if target_result.get("dof", -1) <= 0 else "COMPUTED_DIAGNOSTIC_ONLY",
                        "cumulative_relative_mm": [
                            {"epoch": str(ep), "mm": float(v), "error_mm": float(err) if np.isfinite(err) else None}
                            for ep, v, err in zip(target_result["epochs"], target_result["cumulative_mm"], target_result["error_mm"])
                        ],
                    }
                    target_series_outputs.append(target_row)
                else:
                    target_series_outputs.append({
                        "component_id": comp_id, "family": family, "track": track,
                        "status": "INSUFFICIENT_TARGET_WINDOW_SUPPORT",
                        "missing_product_ids": missing_target_pairs,
                    })
            row["pair_reference_medians_mm"] = pair_reference_medians
            report["network_components"].append(row)
            network_rows.append(row)

    # Write reproducible data products before the viewer is generated.
    write_csv(out / "timeseries-pixel-series.csv", pixel_series_rows, [
        "component_id", "pixel_id", "family", "track", "longitude", "latitude",
        "epoch", "cumulative_relative_mm", "error_mm", "redundancy_dof", "reference_policy",
    ])
    write_csv(out / "timeseries-network.csv", network_rows, [
        "component_id", "family", "track", "direction", "path", "epochs", "n_pairs",
        "n_epochs", "n_unknowns", "redundancy_dof", "grid_aligned", "common_valid_pixels_all_pairs",
        "reference_pixels", "sampled_pixels", "status", "dof_warning", "reference_policy",
    ])
    write_csv(out / "local-floor.csv", local_floor_rows, [
        "component_id", "family", "track", "product_id", "reference", "secondary",
        "span_days", "valid_aoi_pixels", "common_pixels", "reference_pixels",
        "aoi_spatial_scatter_floor_mm_day", "target_window_valid_pixels",
        "target_local_floor_mm_day", "target_floor_ci95_low_mm_day",
        "target_floor_ci95_high_mm_day", "floor_method", "interpretation",
    ])

    target_supported = bool(target_valid and target_series_outputs)
    velocity_rows = []
    eligible_velocity = [
        x for x in target_series_outputs
        if x.get("status") in {"COMPUTED_DIAGNOSTIC_ONLY", "EXACTLY_DETERMINED_NO_ERROR_ESTIMATE"}
        and int(x.get("n_epochs") or 0) >= 4
        and int(x.get("n_pairs") or 0) >= 3
        and int(x.get("redundancy_dof") or 0) > 0
    ]
    if not target_valid:
        inverse_status = "SKIPPED_NO_VALIDATED_TARGET_COORDINATES"
        inverse_detail = "The AOI alone does not identify a landslide target. No inverse-velocity forecast was inferred from AOI medians or sampled pixels."
    elif not eligible_velocity:
        inverse_status = "INSUFFICIENT_TEMPORAL_REDUNDANCY"
        inverse_detail = "No target component has at least 4 epochs, 3 independent pair intervals and positive redundancy degrees of freedom; no defensible inverse-velocity fit."
    else:
        inverse_status = "ELIGIBLE_BUT_REQUIRES_PER_PAIR_LOCAL_FLOORS"
        inverse_detail = "Target network meets the temporal gate; ensure each exact interval has a valid local noise floor before invoking inverse_velocity.analyse_block."
    inverse_report = {
        "schema_version": SCHEMA, "status": inverse_status, "detail": inverse_detail,
        "target_series_components": len(target_series_outputs),
        "eligible_components": len(eligible_velocity),
        "fit_parameters": {"window": 3, "r2_min": 0.70, "forecast_cutoff": None, "event_date": None},
        "policy": "Do not use the source-event default date or forecast cutoff for a generic WKT AOI. No hazard forecast is issued by this stage unless the temporal, target and per-pair floor gates all pass.",
    }
    (out / "inverse-velocity.json").write_text(json.dumps(json_safe(inverse_report), indent=2, allow_nan=False) + "\n", encoding="utf-8")

    has_ascending = any(x["pair"].direction == "A" for x in products if x["family"] == "GUNW")
    has_descending = any(x["pair"].direction == "D" for x in products if x["family"] == "GUNW")
    geometry_report = {
        "schema_version": SCHEMA,
        "status": "SKIPPED_NO_PRODUCT_LOS_UNIT_VECTORS",
        "target_provided": bool(target_valid),
        "ascending_gunw_present": has_ascending,
        "descending_gunw_present": has_descending,
        "detail": "Retained AOI GeoTIFFs contain LOS displacement/coherence but not the per-pixel LOS unit vectors required for a defensible east/vertical decomposition. Do not substitute nominal track geometry or mix GOFF range offsets into a GUNW LOS solve.",
        "required_inputs": ["per-product LOS unit vector at the target or georeferenced losUnitVectorX/Y rasters", "compatible ascending/descending acquisition epochs", "target-specific common-reference time series"],
    }
    (out / "geometry-merge.json").write_text(json.dumps(geometry_report, indent=2) + "\n", encoding="utf-8")

    bound_report = {
        "schema_version": SCHEMA,
        "status": "SKIPPED_NOT_A_GENERIC_AOI_BOUND",
        "detail": "bound.py is a source-event audit with hard-coded Bhote Koshi event date, candidate list, acquisition intervals, elevation band and external precursor rate. Those constants must not be reused for an arbitrary WKT AOI.",
        "required_inputs": ["validated candidate coordinates", "event date/window if a retrospective bound is intended", "source-specific independently cited precursor measurement", "candidate-local GOFF and phase floors"],
    }
    (out / "bound.json").write_text(json.dumps(bound_report, indent=2) + "\n", encoding="utf-8")

    diagnostics = summary.get("science_diagnostics") or {}
    pixel_stack = diagnostics.get("pixel_stack") or {}
    timeseries_status = (
        "COMPUTED_DIAGNOSTIC_ONLY" if pixel_series_rows else "INSUFFICIENT_COMMON_SUPPORT"
    )
    if any(int(x.get("redundancy_dof") or 0) <= 0 for x in network_rows):
        report["warnings"].append("ONE_OR_MORE_NETWORKS_HAVE_NO_RESIDUAL_DEGREES_OF_FREEDOM")
    if str(pixel_stack.get("status", "")).endswith("NO_DETECTION"):
        report["warnings"].append("PIXEL_STACK_NO_DETECTION_IS_NOT_EVIDENCE_OF_NO_HAZARD")
    report["stages"] = {
        "timeseries": {
            "status": timeseries_status,
            "pairs_used": sum(int(x.get("n_pairs") or 0) for x in network_rows),
            "network_components": len(network_rows),
            "pixel_series_rows": len(pixel_series_rows),
            "common_support_pixels_across_components": common_support_total,
            "detail": "Uses the pinned timeseries.Pair/connected_components/invert_component routines. Values are relative to a common-support spatial reference proxy, not absolute ground displacement; disconnected components retain separate zeros.",
            "uncertainty_policy": "An exactly determined component (redundancy_dof <= 0) has no residual-based error estimate and cannot support a significance claim.",
        },
        "local_floor": {
            "status": "TARGET_LOCAL_FLOOR_COMPUTED" if target_valid and any(x.get("target_local_floor_mm_day") is not None for x in local_floor_rows) else "AOI_DIAGNOSTIC_ONLY_NO_TARGET_FLOOR",
            "pairs": len(local_floor_rows),
            "detail": "Uses the pinned local_floor.detection_floor/compare functions. AOI spatial scatter is not mislabeled as a target-local noise floor.",
        },
        "geometry_merge": geometry_report,
        "inverse_velocity": inverse_report,
        "bound": bound_report,
    }
    report["target_series"] = target_series_outputs
    report["pixel_stack"] = pixel_stack
    report["products_used"] = len(products)
    report["products_rejected"] = input_errors
    report["status"] = "PASS_WITH_LIMITATIONS" if products and not any("SCIENCE_COMMIT_MISMATCH" in x for x in report["errors"]) else "FAIL"
    report["outputs"] = {
        "report": "science-engine-report.json",
        "network": "science-engine/timeseries-network.csv",
        "sampled_pixel_series": "science-engine/timeseries-pixel-series.csv",
        "local_floor": "science-engine/local-floor.csv",
        "geometry_merge": "science-engine/geometry-merge.json",
        "inverse_velocity": "science-engine/inverse-velocity.json",
        "bound": "science-engine/bound.json",
        "network_components": component_total,
    }
    final_path = root / "science-engine-report.json"
    final_path.write_text(json.dumps(json_safe(report), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return json_safe(report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard-root", type=Path, required=True)
    parser.add_argument("--science-root", type=Path, required=True)
    args = parser.parse_args()
    report = run_engine(args.dashboard_root, args.science_root)
    print("SCIENCE_ENGINE_STATUS=" + str(report.get("status")))
    for stage, detail in (report.get("stages") or {}).items():
        print("SCIENCE_STAGE_" + stage.upper() + "=" + str(detail.get("status")))
    print("SCIENCE_NETWORK_COMPONENTS=" + str(len(report.get("network_components", []))))
    print("SCIENCE_PIXEL_SERIES_ROWS=" + str(sum(1 for _ in (args.dashboard_root / "science-engine" / "timeseries-pixel-series.csv").open(encoding="utf-8")) - 1 if (args.dashboard_root / "science-engine" / "timeseries-pixel-series.csv").is_file() else 0))
    return 0 if report.get("status") == "PASS_WITH_LIMITATIONS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
