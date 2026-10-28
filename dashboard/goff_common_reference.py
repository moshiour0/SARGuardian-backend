"""Target-aware GOFF common-reference diagnostic from retained AOI rasters.

This stage does not read raw HDF5. It validates the retained, AOI-clipped
range/azimuth/correlation bands, re-references each compatible acquisition
network to a data-derived common pixel set outside the target buffer, and
reports graph inversions only as diagnostics. The common reference is not
independently surveyed stable ground; this is not 3-D fusion or a hazard alert.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _empty_report(status: str, reason: str, aoi_wkt_sha256: str | None) -> dict[str, Any]:
    return {
        "schema_version": "sarguardian-goff-common-reference-timeseries/1.0",
        "status": status,
        "series_are_independent_geophysical_validation": False,
        "common_reference_is_independently_validated_stable_ground": False,
        "aoi_wkt_sha256": aoi_wkt_sha256,
        "common_reference_method": (
            "median over pixels valid in every pair, inside the exact submitted AOI "
            "and outside a 2 km buffer around the explicit target"
        ),
        "reason": reason,
        "networks": [],
        "pairwise_measurements": [],
        "components": [],
        "warnings": [
            "GOFF range and azimuth offsets are not automatically vertical motion or full 3-D displacement.",
            "The common datum is inferred from this AOI's common pixels and is not independently certified stable ground.",
            "Cumulative graph solutions are diagnostic only; they are not a hazard alarm or forecast.",
        ],
    }


def _point_in_ring(longitude: float, latitude: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    for index in range(len(ring) - 1):
        x1, y1 = ring[index]
        x2, y2 = ring[index + 1]
        cross = (longitude - x1) * (y2 - y1) - (latitude - y1) * (x2 - x1)
        if (abs(cross) <= 1e-10
                and min(x1, x2) - 1e-10 <= longitude <= max(x1, x2) + 1e-10
                and min(y1, y2) - 1e-10 <= latitude <= max(y1, y2) + 1e-10):
            return True
        if (y1 > latitude) != (y2 > latitude):
            crossing = x1 + (latitude - y1) * (x2 - x1) / (y2 - y1)
            if longitude < crossing:
                inside = not inside
    return inside


def _safe_child(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _write_report(output_root: Path, report: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "goff-common-reference-timeseries.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    pairs = report.get("pairwise_measurements") or []
    if pairs:
        with (output_root / "goff-common-reference-pairs.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(pairs[0]), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(pairs)
    series_rows = []
    for component in report.get("components") or []:
        for point in component.get("series") or []:
            series_rows.append({
                "network": component.get("network"),
                "component": component.get("component"),
                **point,
            })
    if series_rows:
        with (output_root / "goff-common-reference-series.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(series_rows[0]), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(series_rows)


def build_goff_common_reference_report(
    products: list[dict[str, Any]],
    output_root: Path,
    science_root: Path,
    aoi_wkt: str,
    aoi_wkt_sha256: str | None,
    site_context: dict[str, Any] | None,
    *,
    min_target_pixels: int = 6,
    target_radius_px: int = 5,
    buffer_km: float = 2.0,
    minimum_common_reference_pixels: int = 200,
    correlation_minimum: float = 0.3,
) -> dict[str, Any]:
    """Create a gated GOFF range/azimuth diagnostic using retained exports only."""
    output_root = output_root.resolve()
    target = ((site_context or {}).get("measurement_target") or {})
    if target.get("status") != "IN_AOI_TARGET_CAPTURED":
        report = _empty_report(
            "BLOCKED_NO_VALID_IN_AOI_TARGET",
            "The request has no explicit measurement target validated inside its AOI.",
            aoi_wkt_sha256,
        )
        _write_report(output_root, report)
        return report
    target_lat, target_lon = _number(target.get("latitude")), _number(target.get("longitude"))
    if target_lat is None or target_lon is None:
        report = _empty_report(
            "BLOCKED_INVALID_TARGET_COORDINATES",
            "The target is missing a finite WGS84 latitude/longitude pair.",
            aoi_wkt_sha256,
        )
        _write_report(output_root, report)
        return report
    if not (0 <= target_radius_px and buffer_km >= 0 and min_target_pixels >= 1
            and minimum_common_reference_pixels >= 1 and 0 <= correlation_minimum <= 1):
        report = _empty_report("INVALID_ANALYSIS_PARAMETERS", "One or more numeric gates are invalid.", aoi_wkt_sha256)
        _write_report(output_root, report)
        return report

    src = science_root.resolve() / "src"
    if not src.is_dir():
        report = _empty_report("UNAVAILABLE_PINNED_SCIENCE_SOURCE", "Pinned science source directory is missing.", aoi_wkt_sha256)
        _write_report(output_root, report)
        return report
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    os.environ["SARGUARDIAN_AOI_WKT"] = aoi_wkt
    rejected: list[dict[str, Any]] = []
    try:
        from aoi_wkt import parse_polygon_wkt
        import gunw_reader
        import common_ref
        import timeseries
        import rasterio
        from pyproj import Transformer
        from rasterio.features import geometry_mask
        from rasterio.warp import transform_geom
        from rasterio.transform import rowcol
        ring = [(float(x), float(y)) for x, y in parse_polygon_wkt(aoi_wkt)]
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        if len(ring) < 4 or not _point_in_ring(target_lon, target_lat, ring):
            report = _empty_report("BLOCKED_TARGET_OUTSIDE_EXACT_AOI", "The target is not inside the exact submitted WKT polygon.", aoi_wkt_sha256)
            _write_report(output_root, report)
            return report
        gunw_reader.AOIS["custom"] = ring
        gunw_reader.set_aoi("custom")
    except Exception as exc:
        report = _empty_report(
            "UNAVAILABLE_SCIENCE_IMPORT",
            f"Pinned GOFF/common-reference dependencies could not be loaded: {type(exc).__name__}: {str(exc)[:200]}",
            aoi_wkt_sha256,
        )
        _write_report(output_root, report)
        return report

    report = _empty_report(
        "NO_ELIGIBLE_GOFF_NETWORK",
        "No GOFF network met the retained-raster, exact-AOI, common-grid and target-support gates.",
        aoi_wkt_sha256,
    )
    report.update({
        "target": {"latitude": target_lat, "longitude": target_lon},
        "target_radius_pixels": target_radius_px,
        "buffer_km": buffer_km,
        "minimum_target_pixels": min_target_pixels,
        "minimum_common_reference_pixels": minimum_common_reference_pixels,
        "correlation_minimum": correlation_minimum,
    })

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for product in products:
        if str(product.get("product_type", "")).upper() != "GOFF":
            continue
        name = Path(str(product.get("granule_name") or "")).name
        metadata = timeseries.granule_metadata(name)
        if not metadata or str(metadata.get("product", "")).upper() != "GOFF":
            rejected.append({"product_id": product.get("id"), "status": "REJECTED_IDENTITY", "reason": "Pinned timeseries.py could not parse the exact GOFF granule identity."})
            continue
        ref_date = _parse_date(product.get("reference_date"))
        sec_date = _parse_date(product.get("secondary_date"))
        if ref_date is None or sec_date is None or sec_date <= ref_date:
            stamps = re.findall(r"_(\d{8})T\d{6}", name)
            if len(stamps) >= 4:
                try:
                    ref_date = date.fromisoformat(f"{stamps[0][:4]}-{stamps[0][4:6]}-{stamps[0][6:]}")
                    sec_date = date.fromisoformat(f"{stamps[2][:4]}-{stamps[2][4:6]}-{stamps[2][6:]}")
                except ValueError:
                    ref_date = sec_date = None
        if ref_date is None or sec_date is None or sec_date <= ref_date:
            rejected.append({"product_id": product.get("id"), "status": "REJECTED_DATES", "reason": "Valid, increasing GOFF acquisition dates were not available."})
            continue
        exports = product.get("exports") if isinstance(product.get("exports"), list) else []
        if len(exports) != 1 or not isinstance(exports[0], dict):
            rejected.append({"product_id": product.get("id"), "status": "REJECTED_EXPORT_COUNT", "reason": "Exactly one retained GOFF export is required per product."})
            continue
        relative = str(exports[0].get("relative_path") or "")
        try:
            raster_path = _safe_child(output_root, relative)
        except (OSError, ValueError):
            rejected.append({"product_id": product.get("id"), "status": "REJECTED_EXPORT_PATH", "reason": "Export path is not contained within the result bundle."})
            continue
        if not raster_path.is_file():
            rejected.append({"product_id": product.get("id"), "status": "REJECTED_EXPORT_MISSING", "reason": "Retained GOFF raster is missing."})
            continue
        network_key = (
            metadata.get("direction"), metadata.get("path"), metadata.get("frame"),
            metadata.get("subswath"), metadata.get("bandwidth"), metadata.get("polarisation"),
            metadata.get("crid"), metadata.get("product"), metadata.get("processing"),
        )
        grouped[network_key].append({
            "product": product, "name": name, "metadata": metadata,
            "reference": ref_date, "secondary": sec_date, "raster_path": raster_path,
        })

    networks: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    components_out: list[dict[str, Any]] = []
    any_common_datum = False
    any_series = False
    ring_closed = list(ring)
    polygon = {"type": "Polygon", "coordinates": [ring_closed]}

    for network_key, rows in sorted(grouped.items(), key=lambda item: str(item[0])):
        meta0 = rows[0]["metadata"]
        label = (
            f"{'ASC' if str(meta0.get('direction')).upper() == 'A' else 'DESC'} "
            f"path {meta0.get('path')} frame {meta0.get('frame')} "
            f"subswath {meta0.get('subswath')} bandwidth {meta0.get('bandwidth')} "
            f"pol {meta0.get('polarisation')} CRID {meta0.get('crid')} GOFF {meta0.get('processing')}"
        )
        interval_keys = [(row["reference"], row["secondary"]) for row in rows]
        if len(interval_keys) != len(set(interval_keys)):
            networks.append({
                "network": label, "status": "WITHHELD_AMBIGUOUS_DUPLICATE_INTERVALS",
                "pairs": len(rows),
                "reason": "Duplicate intervals exist within the same exact track/frame/subswath/polarisation/CRID/processing network; choose a source explicitly.",
            })
            continue
        if len(rows) < 2:
            networks.append({"network": label, "status": "WITHHELD_TOO_FEW_PAIRS", "pairs": len(rows), "reason": "At least two compatible GOFF pairs are required."})
            continue

        grids = []
        grid_problem = None
        for row in sorted(rows, key=lambda value: (value["reference"], value["secondary"], value["name"])):
            try:
                with rasterio.open(row["raster_path"]) as ds:
                    tags = ds.tags()
                    if ds.count < 3 or ds.crs is None or not ds.crs.is_projected or ds.crs.to_epsg() is None:
                        grid_problem = "GOFF export must have range, azimuth and correlation bands in an identifiable projected CRS."
                        break
                    if tags.get("aoi_name") != "custom" or str(tags.get("aoi_mask_applied", "")).lower() != "true":
                        grid_problem = "GOFF export does not prove masking against this exact custom AOI."
                        break
                    if tags.get("grid_policy") != "common_aoi_lattice":
                        grid_problem = "GOFF export is not on the reader's fixed common AOI lattice."
                        break
                    source_name = Path(str(tags.get("source") or "")).name
                    source_stem = source_name[:-3] if source_name.lower().endswith(".h5") else source_name
                    row_stem = row["name"][:-3] if row["name"].lower().endswith(".h5") else row["name"]
                    if source_stem != row_stem:
                        grid_problem = "GOFF export's embedded source identity does not match the exact selected granule."
                        break
                    correlation_tag = _number(tags.get("correlation_min"))
                    threshold = max(correlation_minimum, correlation_tag if correlation_tag is not None else correlation_minimum)
                    range_values = ds.read(1, masked=True).filled(np.nan).astype("float64")
                    azimuth_values = ds.read(2, masked=True).filled(np.nan).astype("float64")
                    correlation = ds.read(3, masked=True).filled(np.nan).astype("float64")
                    valid = (
                        np.isfinite(range_values) & np.isfinite(azimuth_values)
                        & np.isfinite(correlation) & (correlation >= threshold)
                    )
                    range_values[~valid] = np.nan
                    azimuth_values[~valid] = np.nan
                    correlation[~valid] = np.nan
                    rx, ry = abs(float(ds.res[0])), abs(float(ds.res[1]))
                    if rx <= 0 or ry <= 0 or abs(rx - ry) / max(rx, ry) > 0.02:
                        grid_problem = "The 2-km target-buffer gate requires a near-square projected pixel grid."
                        break
                    grids.append({
                        "row": row, "crs": ds.crs, "epsg": ds.crs.to_epsg(),
                        "transform": ds.transform, "shape": (ds.height, ds.width),
                        "res_x": rx, "res_y": ry, "range": range_values,
                        "azimuth": azimuth_values, "correlation": correlation, "valid": valid,
                        "valid_pixels": int(valid.sum()), "correlation_threshold": threshold,
                    })
            except Exception as exc:
                grid_problem = f"GOFF raster read/validation failed: {type(exc).__name__}: {str(exc)[:160]}"
                break
        if grid_problem:
            networks.append({"network": label, "status": "WITHHELD_GRID_OR_MASK_CONTRACT", "pairs": len(rows), "reason": grid_problem})
            continue
        first = grids[0]
        if any(
            item["crs"] != first["crs"] or item["shape"] != first["shape"]
            or not np.allclose(tuple(item["transform"]), tuple(first["transform"]), rtol=0, atol=1e-9)
            for item in grids[1:]
        ):
            networks.append({"network": label, "status": "WITHHELD_GRID_MISMATCH", "pairs": len(grids), "reason": "Every pair in a network must share exact CRS, shape and affine transform."})
            continue

        transformer = Transformer.from_crs("EPSG:4326", first["crs"], always_xy=True)
        target_x, target_y = transformer.transform(target_lon, target_lat)
        target_row, target_col = rowcol(first["transform"], target_x, target_y)
        if not (0 <= target_row < first["shape"][0] and 0 <= target_col < first["shape"][1]):
            networks.append({"network": label, "status": "WITHHELD_TARGET_OUTSIDE_GRID", "pairs": len(grids), "reason": "The explicit in-AOI target is not covered by the GOFF export grid."})
            continue
        geo = transform_geom("EPSG:4326", first["crs"], polygon)
        inside_aoi = geometry_mask([geo], out_shape=first["shape"], transform=first["transform"], all_touched=False, invert=True)
        if not inside_aoi[target_row, target_col]:
            networks.append({"network": label, "status": "WITHHELD_TARGET_OUTSIDE_MASK", "pairs": len(grids), "reason": "Target cell is outside the exact AOI mask on the exported grid."})
            continue
        common = np.logical_and.reduce([item["valid"] for item in grids]) & inside_aoi
        resolution = (first["res_x"] + first["res_y"]) / 2
        buffer_px = int(round(buffer_km * 1000 / resolution))
        stable = common & ~common_ref.buffer_mask(common.shape, [(target_row, target_col)], buffer_px)
        common_count, stable_count = int(common.sum()), int(stable.sum())
        if stable_count < minimum_common_reference_pixels:
            networks.append({
                "network": label, "status": "WITHHELD_INSUFFICIENT_COMMON_REFERENCE_PIXELS",
                "pairs": len(grids), "common_valid_aoi_pixels": common_count,
                "common_pixels_outside_target_buffer": stable_count,
                "required_pixels": minimum_common_reference_pixels,
                "reason": "The GOFF stack does not contain the minimum number of pixels valid in every pair outside the target buffer.",
            })
            continue
        try:
            range_fixed, range_constants = common_ref.rereference([item["range"] for item in grids], stable)
            azimuth_fixed, azimuth_constants = common_ref.rereference([item["azimuth"] for item in grids], stable)
        except Exception as exc:
            networks.append({"network": label, "status": "WITHHELD_COMMON_REFERENCE_FAILED", "pairs": len(grids), "common_pixels_outside_target_buffer": stable_count, "reason": str(exc)[:240]})
            continue
        any_common_datum = True
        axis_results: list[dict[str, Any]] = []
        for axis, fixed_stack, constants, description in (
            ("range_offset", range_fixed, range_constants, "GOFF slant-range offset component"),
            ("azimuth_offset", azimuth_fixed, azimuth_constants, "GOFF along-track offset component"),
        ):
            pair_objects = []
            axis_rows = []
            for item, values, datum in zip(grids, fixed_stack, constants):
                measured, valid_count = common_ref.window_median(values, (target_row, target_col), target_radius_px)
                measured_value = float(measured) if np.isfinite(measured) and valid_count >= min_target_pixels else None
                row = item["row"]
                pair = timeseries.Pair(
                    path=int(row["metadata"]["path"]),
                    direction=str(row["metadata"]["direction"]),
                    ref=row["reference"], sec=row["secondary"],
                    value=measured_value, n_px=valid_count,
                    coherence=None, source=row["name"], metadata=row["metadata"],
                )
                pair_objects.append(pair)
                axis_rows.append({
                    "product_id": row["product"].get("id"),
                    "granule_name": row["name"], "component": axis,
                    "network": label, "reference_date": row["reference"].isoformat(),
                    "secondary_date": row["secondary"].isoformat(),
                    "span_days": pair.span_days,
                    "target_offset_common_datum_mm": _number(measured_value),
                    "target_valid_pixels": valid_count,
                    "common_pixels_outside_target_buffer": stable_count,
                    "datum_offset_removed_mm": _number(datum),
                    "status": "MEASURED_COMMON_DATUM_PAIR" if measured_value is not None else "WITHHELD_INSUFFICIENT_TARGET_PIXELS",
                    "interpretation": description,
                })
            pair_rows.extend(axis_rows)
            usable = [pair for pair in pair_objects if pair.value is not None]
            epochs_sets = timeseries.connected_components(usable) if usable else []
            network_components = []
            for component_index, epochs in enumerate(epochs_sets, 1):
                component_pairs = [pair for pair in usable if pair.ref in epochs and pair.sec in epochs]
                n_epochs = len(epochs)
                redundancy = len(component_pairs) - max(0, n_epochs - 1)
                try:
                    fit = timeseries.invert_component(component_pairs, epochs)
                    jackknife = timeseries.jackknife(label + " " + axis, component_index, component_pairs, epochs)
                except Exception as exc:
                    fit = {"error": f"{type(exc).__name__}:{str(exc)[:200]}"}
                    jackknife = None
                fit_ok = isinstance(fit, dict) and not fit.get("error")
                series_available = (
                    fit_ok and n_epochs >= 3 and redundancy > 0
                    and int(fit.get("dof", 0)) > 0
                    and isinstance(jackknife, dict)
                    and jackknife.get("testable") is True
                    and jackknife.get("robust") is True
                )
                series_rows = []
                if series_available:
                    cumulative = list(fit.get("cumulative_mm", []))
                    errors = list(fit.get("error_mm", []))
                    fit_epochs = list(fit.get("epochs", []))
                    if len(cumulative) != len(fit_epochs) or len(errors) != len(fit_epochs):
                        series_available = False
                    else:
                        for idx, epoch in enumerate(fit_epochs):
                            value = _number(cumulative[idx])
                            error = _number(errors[idx])
                            if value is None:
                                series_available = False
                                break
                            series_rows.append({
                                "epoch": epoch.isoformat() if hasattr(epoch, "isoformat") else str(epoch),
                                "cumulative_offset_mm": value,
                                "graph_fit_standard_error_mm": error,
                                "graph_fit_ci95_low_mm": value - 1.96 * error if error is not None else None,
                                "graph_fit_ci95_high_mm": value + 1.96 * error if error is not None else None,
                            })
                component_status = (
                    "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED"
                    if series_available else "WITHHELD_NO_REDUNDANT_ROBUST_NETWORK"
                )
                component_report = {
                    "network": label, "component": axis, "component_index": component_index,
                    "status": component_status,
                    "first_epoch": epochs[0].isoformat() if epochs else None,
                    "last_epoch": epochs[-1].isoformat() if epochs else None,
                    "epochs_count": n_epochs, "pairs_count": len(component_pairs),
                    "redundancy": redundancy,
                    "degrees_of_freedom": fit.get("dof") if fit_ok else None,
                    "residual_rms_mm": _number(fit.get("residual_rms_mm")) if fit_ok else None,
                    "velocity_mm_per_day": _number(fit.get("velocity_mm_per_day")) if fit_ok else None,
                    "velocity_fit_error_mm_per_day": _number(fit.get("velocity_err_mm_per_day")) if fit_ok else None,
                    "jackknife": jackknife, "series": series_rows if series_available else [],
                    "interpretation": description + "; graph inversion remains diagnostic with an unvalidated common datum.",
                }
                network_components.append(component_report)
                components_out.append(component_report)
                if series_available:
                    any_series = True
            axis_results.append({
                "component": axis, "status": (
                    "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED"
                    if any(x["status"] == "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED" for x in network_components)
                    else "COMMON_DATUM_PAIRWISE_ONLY"
                ),
                "pairs": len(grids), "networks": network_components,
            })
        networks.append({
            "network": label,
            "status": "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED" if any(
                x["status"] == "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED"
                for axis in axis_results for x in axis["networks"]
            ) else "COMMON_DATUM_PAIRWISE_ONLY",
            "pairs": len(grids), "common_valid_aoi_pixels": common_count,
            "common_pixels_outside_target_buffer": stable_count,
            "target_window_radius_px": target_radius_px,
            "target_window_minimum_valid_pixels": min_target_pixels,
            "components": axis_results,
            "assumption_warning": "The reference median is inferred from common valid AOI pixels outside the 2 km buffer; independently surveyed stable ground was not supplied.",
        })

    report["networks"] = networks
    report["pairwise_measurements"] = pair_rows
    report["components"] = components_out
    report["rejected_products"] = rejected
    if any_series:
        report["status"] = "DIAGNOSTIC_SERIES_AVAILABLE_REFERENCE_UNVALIDATED"
        report["reason"] = "At least one GOFF range/azimuth network produced a redundant, jackknife-stable diagnostic inversion; the common reference is not independently validated."
    elif any_common_datum:
        report["status"] = "COMMON_DATUM_PAIRWISE_ONLY"
        report["reason"] = "Common-reference pair values were computed, but no connected redundant jackknife-stable graph inversion met the diagnostic gate."
    elif networks:
        report["status"] = "CUMULATIVE_SERIES_WITHHELD"
        report["reason"] = "No GOFF network met the fixed-grid, common-pixel and target-window requirements; no cumulative values were inferred."
    _write_report(output_root, report)
    return report


__all__ = ["build_goff_common_reference_report"]
