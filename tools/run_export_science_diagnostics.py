#!/usr/bin/env python3
"""Run SARGuardian's unchanged per-pixel and candidate-screening tools on retained exports.

The pixel stack can be run for any AOI whose GUNW exports share a usable grid.
The current candidate_check implementation is restricted to the named scientific
AOIs (source/langtang/lhende); it is therefore enabled only for that explicit
mode and never silently applied to an arbitrary WKT polygon.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

LEGACY_SOURCE_SCIENCE_COMMIT = "ab547ecc82bcc4d6ccef545a59852536c2beacc6"
EXPORT_NAME = re.compile(r"^GUNW_(\d{8})_(\d{8})(?:_([A-Z]{2}))?\.tif$", re.IGNORECASE)
GRANULE_NETWORK = re.compile(
    r"NISAR_L2_(?P<processing>PR|UR)_GUNW_\d{3}_(?P<path>\d{3})_"
    r"(?P<direction>[AD])_(?P<frame>\d{3})_(?P<subswath>\d{3})_"
    r"(?P<bandwidth>\d{4})_(?P<polarisation>[A-Z]{2})_.*?_(?P<crid>[PX]\d{5})_(?:N|F)_",
    re.IGNORECASE,
)
KNOWN_INSUFFICIENT = (
    "no winter rasters", "no summer rasters", "no all rasters",
    "no contiguous chain of 2+ pairs", "no rasters",
)


def help_has_exact_option(help_text: str, option: str) -> bool:
    """Return true only for a standalone argparse option, not a longer prefix.

    The option --aoi-csv must not be mistaken for a separate --aoi option:
    argparse accepts abbreviated long options by default, so passing
    --aoi source can otherwise overwrite the required --aoi-csv value.
    """
    return re.search(rf"(?m)^\s*{re.escape(option)}(?:[\s,]|$)", help_text) is not None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_identity(path: Path) -> tuple[str, str, str] | None:
    match = EXPORT_NAME.fullmatch(path.name)
    if not match:
        return None
    processing = (match.group(3) or "PR").upper()
    return match.group(1), match.group(2), processing


def parse_gunw_network_identity(granule_name: str) -> tuple[str, ...] | None:
    """Return the exact acquisition-network identity used to isolate legacy pixel stacks.

    Dates and cycle may vary along a temporal series. Processing, path, direction,
    frame, subswath, bandwidth, polarization, and CRID may not be silently mixed.
    """
    match = GRANULE_NETWORK.search(Path(str(granule_name or "")).name)
    if not match:
        return None
    fields = ("processing", "path", "direction", "frame", "subswath",
              "bandwidth", "polarisation", "crid")
    values = match.groupdict()
    return tuple(values[key].upper() if key in {"processing", "direction", "polarisation", "crid"}
                 else values[key] for key in fields)


def collect_pr_gunw_exports(exports_root: Path, target_dir: Path) -> dict[str, Any]:
    """Collect PR GUNW rasters into isolated, exact-identity network directories.

    The legacy pixel_stack.py chains on dates and coarse orbit geometry only.
    Invoking it once over a mixed directory can combine different subswaths or
    CRIDs. A separate input folder per exact network prevents that accidental
    cross-product chaining. Unknown source identity is withheld rather than guessed.
    """
    import rasterio

    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        path for path in sorted(exports_root.rglob("*.tif"))
        if (identity := export_identity(path)) and identity[2] == "PR"
    ]

    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    collisions: list[dict[str, str]] = []
    total_copied = 0

    for source in candidates:
        try:
            with rasterio.open(source) as dataset:
                source_name = dataset.tags().get("source", "")
                granule_identity = parse_gunw_network_identity(source_name)
                if granule_identity is None:
                    rejected.append({
                        "source": source.name,
                        "status": "WITHHELD_UNPARSEABLE_SOURCE_IDENTITY",
                        "reason": "The raster source tag does not identify a full NISAR GUNW network; safe temporal grouping is not possible.",
                    })
                    continue
                if dataset.crs is None:
                    raise ValueError("SOURCE_CRS_MISSING")
                transform = dataset.transform
                grid_identity = (
                    dataset.crs.to_string(),
                    round(float(transform.a), 9),
                    round(float(transform.b), 9),
                    round(float(transform.d), 9),
                    round(float(transform.e), 9),
                )
        except Exception as exc:
            rejected.append({
                "source": source.name,
                "status": "WITHHELD_INVALID_RASTER_IDENTITY",
                "reason": type(exc).__name__ + ":" + str(exc)[:180],
            })
            continue

        key = (*granule_identity, *grid_identity)
        if key not in groups:
            label = (
                f"{granule_identity[2]}{granule_identity[1]} "
                f"frame {granule_identity[3]} subswath {granule_identity[4]} "
                f"bw {granule_identity[5]} pol {granule_identity[6]} CRID {granule_identity[7]}"
            )
            digest = hashlib.sha256("|".join(map(str, key)).encode("utf-8")).hexdigest()[:12]
            network_dir = target_dir / f"network-{digest}"
            network_dir.mkdir(parents=True, exist_ok=True)
            groups[key] = {
                "network_id": digest,
                "network_label": label,
                "identity": list(granule_identity),
                "grid_identity": list(grid_identity),
                "input_directory": str(network_dir),
                "source_files_matched": 0,
                "files_copied": 0,
                "files": [],
                "duplicate_intervals": [],
                "status": "READY",
            }

        group = groups[key]
        group["source_files_matched"] += 1
        destination = Path(group["input_directory"]) / source.name
        if destination.exists():
            if file_sha256(source) != file_sha256(destination):
                collisions.append({
                    "name": source.name,
                    "source": str(source),
                    "network_id": str(group["network_id"]),
                })
            continue
        shutil.copy2(source, destination)
        group["files"].append(destination.name)
        group["files_copied"] += 1
        total_copied += 1

    network_rows: list[dict[str, Any]] = []
    for key, group in sorted(groups.items(), key=lambda item: str(item[0])):
        intervals = [export_identity(Path(name))[:2] for name in group["files"]]
        counts: dict[tuple[str, str], int] = {}
        for interval in intervals:
            counts[interval] = counts.get(interval, 0) + 1
        duplicates = sorted(f"{left}->{right}" for (left, right), count in counts.items() if count > 1)
        group["duplicate_intervals"] = duplicates
        if duplicates:
            group["status"] = "WITHHELD_DUPLICATE_ACQUISITION_INTERVALS"
            group["reason"] = (
                "Duplicate pair intervals exist within this exact network; they cannot add temporal redundancy."
            )
        elif group["files_copied"] < 2:
            group["status"] = "INSUFFICIENT_TEMPORAL_COVERAGE"
            group["reason"] = "Fewer than two distinct retained pairs are available in this exact network."
        network_rows.append(group)

    return {
        "source_root": str(exports_root),
        "input_directory": str(target_dir),
        "source_files_matched": len(candidates),
        "files_copied": total_copied,
        "files": [name for group in network_rows for name in group["files"]],
        "filename_collisions": collisions,
        "rejected_files": rejected,
        "networks": network_rows,
    }


def classify_pixel_stack(returncode: int, output: str) -> str:
    lower = output.lower()
    # A zero exit code only means the script completed. It does not mean a
    # per-pixel fit existed: pixel_stack.py exits 0 after "nothing to fit".
    if "cluster exceeds the noise-only 95th percentile" in lower:
        return "COMPLETED_CANDIDATE_REQUIRES_CROSS_CHECK" if returncode == 0 else "FAIL"
    if "pixels with a complete series" in lower and re.search(
        r"pixels with a complete series\s*:\s*0\s+of\s+", lower
    ):
        return "INSUFFICIENT_TEMPORAL_COVERAGE"
    if "nothing to fit" in lower:
        return "INSUFFICIENT_TEMPORAL_COVERAGE"
    if any(fragment in lower for fragment in KNOWN_INSUFFICIENT):
        return "INSUFFICIENT_TEMPORAL_COVERAGE"
    if "verdict: no detection" in lower:
        return "COMPLETED_NO_DETECTION" if returncode == 0 else "FAIL"
    if returncode == 0:
        # A fit was calculated but no recognized verdict was emitted. Keep it
        # explicitly indeterminate; never convert it to a no-detection result.
        if "pixels with a complete series" in lower:
            return "COMPLETED_INDETERMINATE"
        return "COMPLETED_INDETERMINATE"
    return "FAIL"


def read_candidate_points(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    points = []
    for row in rows:
        reading = str(row.get("reading", "")).strip()
        if "detach" not in reading.lower():
            continue
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
            candidate_id = str(row.get("id") or f"{lat:.6f}_{lon:.6f}").strip()
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        points.append({"id": candidate_id, "lat": lat, "lon": lon, "reading": reading})
    return points


def candidate_export_mask_policy(
    tags: dict[str, Any], *, aoi: str, science_commit: str
) -> tuple[bool, str]:
    """Accept only explicit AOI-mask provenance or the known legacy source pin."""
    source = str(tags.get("source", "")).strip()
    if not source:
        return False, "SOURCE_PROVENANCE_TAG_MISSING"
    raw_mask = tags.get("aoi_mask_applied")
    if raw_mask is not None and str(raw_mask).strip():
        if str(raw_mask).strip().lower() == "true":
            return True, "EXPLICIT_AOI_MASK_TAG"
        return False, "AOI_MASK_EXPLICITLY_NOT_TRUE"
    if aoi == "source" and science_commit == LEGACY_SOURCE_SCIENCE_COMMIT:
        return True, "LEGACY_SOURCE_PIN_WITH_SOURCE_PROVENANCE_TAG"
    return False, "AOI_MASK_TAG_MISSING_FOR_THIS_ENGINE_OR_AOI"


def target_window_measurements(
    raster_dir: Path, latitude: float, longitude: float, radius: int = 5,
    coherence_threshold: float = 0.3, *, aoi: str, science_commit: str,
) -> list[dict[str, Any]]:
    """Measure each pair's retained 2-band GUNW export at a target window."""
    import numpy as np
    import rasterio
    from rasterio.transform import rowcol
    from pyproj import Transformer

    measurements: list[dict[str, Any]] = []
    transformers: dict[str, Any] = {}
    for path in sorted(raster_dir.glob("GUNW_*.tif")):
        identity = export_identity(path)
        if not identity or identity[2] != "PR":
            continue
        reference, secondary, _processing = identity
        try:
            with rasterio.open(path) as src:
                if src.count < 2 or src.crs is None:
                    continue
                mask_ok, mask_evidence = candidate_export_mask_policy(
                    src.tags(), aoi=aoi, science_commit=science_commit
                )
                if not mask_ok:
                    continue
                crs_key = str(src.crs)
                transformer = transformers.get(crs_key)
                if transformer is None:
                    transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                    transformers[crs_key] = transformer
                x, y = transformer.transform(longitude, latitude)
                row, col = rowcol(src.transform, x, y)
                if row < 0 or col < 0 or row >= src.height or col >= src.width:
                    continue
                r0, r1 = max(0, row - radius), min(src.height, row + radius + 1)
                c0, c1 = max(0, col - radius), min(src.width, col + radius + 1)
                displacement = src.read(1, window=((r0, r1), (c0, c1)), masked=True).filled(np.nan)
                coherence = src.read(2, window=((r0, r1), (c0, c1)), masked=True).filled(np.nan)
                valid = np.isfinite(displacement) & np.isfinite(coherence) & (coherence >= coherence_threshold)
                count = int(valid.sum())
                if count < 1:
                    continue
                measurements.append({
                    "reference": reference,
                    "secondary": secondary,
                    "median_mm": float(np.median(displacement[valid])),
                    "valid_pixels": count,
                    "median_coherence": float(np.median(coherence[valid])),
                    "aoi_mask_evidence": mask_evidence,
                    "raster": path.name,
                })
        except (OSError, ValueError, RuntimeError):
            # A corrupt/unsupported export is not a zero-motion measurement.
            continue
    return measurements


def write_target_log(path: Path, measurements: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Target-window values extracted from retained AOI-clipped GUNW GeoTIFFs.",
        "Window median and coherence-filter rule are recorded in science-diagnostics.json.",
    ]
    for row in measurements:
        a = datetime.strptime(row["reference"], "%Y%m%d").date().isoformat()
        b = datetime.strptime(row["secondary"], "%Y%m%d").date().isoformat()
        lines.append(
            f"{a} -> {b} : {row['median_mm']:.4f} mm "
            f"({row['valid_pixels']} px, coh {row['median_coherence']:.4f})"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_diagnostics(
    science_root: Path,
    exports_root: Path,
    out_root: Path,
    *,
    expected_science_commit: str,
    aoi: str = "custom",
    stats_csv: Path | None = None,
    candidates_csv: Path | None = None,
    run_candidate_check: bool = False,
) -> dict[str, Any]:
    science_root = science_root.resolve()
    exports_root = exports_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    logs = out_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": "sarguardian-export-science-diagnostics/1.0",
        "expected_science_commit": expected_science_commit,
        "aoi_mode": aoi,
        "export_source": str(exports_root),
        "pixel_stack": {"status": "NOT_STARTED"},
        "candidate_checks": {"status": "NOT_REQUESTED", "results": []},
        "warnings": [],
        "errors": [],
    }

    rev = subprocess.run(
        ["git", "-C", str(science_root), "rev-parse", "HEAD"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=30,
    )
    actual = (rev.stdout or "").strip()
    report["actual_science_commit"] = actual
    if rev.returncode or actual != expected_science_commit:
        report["errors"].append({
            "problem": "SCIENCE_COMMIT_MISMATCH",
            "expected": expected_science_commit,
            "actual": actual,
            "detail": (rev.stdout or "")[-600:],
        })
        report["status"] = "FAIL"
        (out_root / "science-diagnostics.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return report

    flat_dir = out_root / "pixel-stack-input"
    inventory = collect_pr_gunw_exports(exports_root, flat_dir)
    report["export_inventory"] = inventory
    if inventory["filename_collisions"]:
        report["errors"].append({
            "problem": "DUPLICATE_GUNW_EXPORT_BASENAME_WITHIN_NETWORK",
            "collisions": inventory["filename_collisions"],
        })
    if inventory["rejected_files"]:
        report["warnings"].append("PIXEL_STACK_SOURCE_IDENTITY_WITHHELD")
    pixel_script = science_root / "src" / "pixel_stack.py"
    network_results: list[dict[str, Any]] = []
    if not pixel_script.is_file():
        report["pixel_stack"] = {"status": "FAIL", "problem": "SCRIPT_MISSING", "network_results": []}
        report["errors"].append({"problem": "PIXEL_STACK_SCRIPT_MISSING"})
    elif inventory["files_copied"] < 1:
        report["pixel_stack"] = {
            "status": "NO_INPUT_EXPORTS",
            "input_count": 0,
            "detail": "No parseable, provenance-identified PR GUNW GeoTIFF exports were retained.",
            "network_results": [],
        }
        report["warnings"].append("PIXEL_STACK_NOT_RUN_NO_GUNW_EXPORTS")
    else:
        for network in inventory["networks"]:
            result = {
                "network_id": network["network_id"],
                "network": network["network_label"],
                "status": network["status"],
                "input_count": network["files_copied"],
                "input_files": network["files"],
                "duplicate_intervals": network["duplicate_intervals"],
                "log": None,
                "detail": network.get("reason"),
            }
            if network["status"] != "READY":
                network_results.append(result)
                continue
            argv = [
                sys.executable, str(pixel_script),
                "--dir", str(network["input_directory"]), "--season", "all",
            ]
            done = subprocess.run(
                argv, cwd=science_root, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False, timeout=1800,
            )
            log_name = f"pixel_stack-{network['network_id']}.log"
            (logs / log_name).write_text(done.stdout or "", encoding="utf-8")
            state = classify_pixel_stack(done.returncode, done.stdout or "")
            result.update({
                "status": state,
                "argv": argv,
                "returncode": done.returncode,
                "log": f"logs/{log_name}",
                "log_tail": (done.stdout or "")[-2000:],
                "interpretation": (
                    "A significant per-pixel spatial cluster is unconfirmed and requires independent geometry/season/time cross-checks."
                    if state == "COMPLETED_CANDIDATE_REQUIRES_CROSS_CHECK" else
                    "No candidate exceeded this script's internal noise null; this does not prove zero movement or absence of hazard."
                    if state == "COMPLETED_NO_DETECTION" else
                    "No complete per-pixel fit was available in this network; the missing fit is not a zero-motion observation."
                    if state == "INSUFFICIENT_TEMPORAL_COVERAGE" else
                    "The script returned without a recognized candidate/no-detection verdict; treat as indeterminate until its log is reviewed."
                    if state == "COMPLETED_INDETERMINATE" else
                    "The per-network pixel-stack command failed; inspect its log before interpreting this stage."
                ),
            })
            if state == "FAIL":
                report["errors"].append({
                    "problem": "PIXEL_STACK_NETWORK_FAILED",
                    "network_id": network["network_id"],
                    "network": network["network_label"],
                    "returncode": done.returncode,
                    "log_tail": (done.stdout or "")[-1600:],
                })
            network_results.append(result)

        states = [str(row["status"]) for row in network_results]
        if "FAIL" in states:
            overall = "FAIL"
        elif "COMPLETED_CANDIDATE_REQUIRES_CROSS_CHECK" in states:
            overall = "COMPLETED_CANDIDATE_REQUIRES_CROSS_CHECK"
        elif states and all(state == "COMPLETED_NO_DETECTION" for state in states):
            overall = "COMPLETED_NO_DETECTION"
        elif "COMPLETED_NO_DETECTION" in states:
            overall = "COMPLETED_WITH_INSUFFICIENT_NETWORKS"
        elif "COMPLETED_INDETERMINATE" in states:
            overall = "COMPLETED_INDETERMINATE"
        else:
            overall = "INSUFFICIENT_TEMPORAL_COVERAGE"

        report["pixel_stack"] = {
            "status": overall,
            "input_count": inventory["files_copied"],
            "network_count": len(inventory["networks"]),
            "network_results": network_results,
            "identity_policy": [
                "Each legacy pixel_stack invocation receives one exact processing/path/direction/frame/subswath/bandwidth/polarization/CRID network and one CRS/resolution grid.",
                "Unparseable source identities and duplicate intervals are withheld.",
                "The strict AOI-relative pixel inversion report is separate and remains the preferred target-free time-series gate.",
            ],
            "interpretation": (
                "A significant spatial cluster is a candidate that needs independent geometry, season and temporal checks."
                if overall == "COMPLETED_CANDIDATE_REQUIRES_CROSS_CHECK" else
                "No tested network exceeded this script's noise null; insufficient or unsupported networks remain visible and this is not proof of stability."
                if overall in {"COMPLETED_NO_DETECTION", "COMPLETED_WITH_INSUFFICIENT_NETWORKS"} else
                "No complete pixel fit was available for all current networks that need it; this is insufficient evidence, not zero motion."
                if overall == "INSUFFICIENT_TEMPORAL_COVERAGE" else
                "At least one network produced an indeterminate result; inspect per-network logs before interpretation."
                if overall == "COMPLETED_INDETERMINATE" else
                "At least one per-network pixel-stack command failed; resolve its log before interpreting this stage."
            ),
        }
        if overall in {"INSUFFICIENT_TEMPORAL_COVERAGE", "COMPLETED_WITH_INSUFFICIENT_NETWORKS"}:
            report["warnings"].append("PIXEL_STACK_INSUFFICIENT_NETWORK_OR_COMPLETE_PIXEL_SUPPORT")
    if not run_candidate_check:
        report["candidate_checks"] = {
            "status": "NOT_REQUESTED",
            "detail": "Candidate screening was not requested for this workflow mode.",
            "results": [],
        }
    elif aoi not in {"source", "langtang", "lhende"}:
        report["candidate_checks"] = {
            "status": "SKIPPED_UNSUPPORTED_CUSTOM_AOI",
            "detail": (
                "candidate_check.py currently validates only named source/langtang/lhende AOIs, "
                "and timeseries.py enforces those polygons. Applying it to arbitrary WKT would be scientifically invalid."
            ),
            "results": [],
        }
        report["warnings"].append("CANDIDATE_CHECK_SKIPPED_FOR_ARBITRARY_WKT")
    elif stats_csv is None or candidates_csv is None or not stats_csv.is_file() or not candidates_csv.is_file():
        report["candidate_checks"] = {
            "status": "SKIPPED_REQUIRED_INPUT_MISSING",
            "stats_csv": str(stats_csv) if stats_csv else None,
            "candidates_csv": str(candidates_csv) if candidates_csv else None,
            "results": [],
        }
        report["warnings"].append("CANDIDATE_CHECK_REQUIRED_INPUT_MISSING")
    else:
        candidate_script = science_root / "src" / "candidate_check.py"
        if not candidate_script.is_file():
            report["candidate_checks"] = {"status": "FAIL", "problem": "SCRIPT_MISSING", "results": []}
            report["errors"].append({"problem": "CANDIDATE_CHECK_SCRIPT_MISSING"})
        else:
            help_result = subprocess.run(
                [sys.executable, str(candidate_script), "--help"],
                cwd=science_root, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False, timeout=60,
            )
            candidate_help = help_result.stdout or ""
            # Exact option detection is important: --aoi-csv is not --aoi.
            # The pinned legacy checker scopes its reference measurements with the
            # AOI-specific --aoi-csv file and does not accept a separate --aoi flag.
            supports_aoi_flag = help_has_exact_option(candidate_help, "--aoi")
            supports_event_affected_flag = help_has_exact_option(candidate_help, "--allow-event-affected-aoi")
            points = read_candidate_points(candidates_csv)
            rows = []
            if aoi != "source" and not supports_aoi_flag:
                report["candidate_checks"] = {
                    "status": "SKIPPED_LEGACY_CLI_CANNOT_SCOPE_NAMED_AOI",
                    "aoi": aoi,
                    "detail": "The pinned candidate_check.py does not expose --aoi. Skipped rather than treating a named AOI as the default source polygon.",
                    "results": [],
                }
                report["warnings"].append("CANDIDATE_CHECK_SKIPPED_LEGACY_AOI_CLI")
                points = []
            for point in points:
                measurement = target_window_measurements(
                    flat_dir, point["lat"], point["lon"], radius=5, coherence_threshold=0.3,
                    aoi=aoi, science_commit=expected_science_commit,
                )
                log_file = logs / f"candidate-{point['id']}-target.log"
                write_target_log(log_file, measurement)
                if not measurement:
                    rows.append({
                        **point, "status": "NOT_MEASURABLE_IN_RETAINED_EXPORTS",
                        "pairs_measured": 0, "log": str(log_file.relative_to(out_root)),
                        "detail": "No coherence-qualified target-window pixels were present. This does not establish stability.",
                    })
                    continue
                argv = [
                    sys.executable, str(candidate_script),
                    "--target-log", str(log_file),
                    "--aoi-csv", str(stats_csv.resolve()),
                    "--lat", str(point["lat"]), "--lon", str(point["lon"]),
                    "--min-px", "20",
                ]
                if supports_aoi_flag:
                    argv.extend(["--aoi", aoi])
                if aoi == "lhende" and supports_event_affected_flag:
                    argv.append("--allow-event-affected-aoi")
                done = subprocess.run(
                    argv, cwd=science_root, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    check=False, timeout=900,
                )
                output = done.stdout or ""
                (logs / f"candidate-{point['id']}-check.log").write_text(output, encoding="utf-8")
                lower = output.lower()
                if done.returncode != 0:
                    status = "CHECK_FAILED"
                    report["errors"].append({
                        "problem": "CANDIDATE_CHECK_COMMAND_FAILED", "candidate_id": point["id"],
                        "returncode": done.returncode, "log_tail": output[-1200:],
                    })
                elif "not ground motion on this evidence" in lower:
                    status = "REJECTED_BY_CURRENT_EVIDENCE"
                elif "survives every test available here" in lower:
                    status = "SURVIVES_SCREEN_NOT_A_DETECTION"
                else:
                    status = "INCONCLUSIVE"
                rows.append({
                    **point, "status": status, "pairs_measured": len(measurement),
                    "returncode": done.returncode, "measurement_log": str(log_file.relative_to(out_root)),
                    "log": str((logs / f"candidate-{point['id']}-check.log").relative_to(out_root)),
                    "tail": output[-1400:],
                })
            if report.get("candidate_checks", {}).get("status") != "SKIPPED_LEGACY_CLI_CANNOT_SCOPE_NAMED_AOI":
                report["candidate_checks"] = {
                    "status": "COMPLETED" if points else "NO_ELIGIBLE_CANDIDATES",
                    "aoi": aoi,
                    "stats_csv": str(stats_csv.resolve()),
                    "candidate_source_csv": str(candidates_csv.resolve()),
                    "measurement_rule": {
                        "window": "11x11 pixels centered on target, clipped to raster edges",
                        "coherence_threshold": 0.3,
                        "statistic": "median LOS displacement and median coherence over valid window pixels",
                        "processing_policy": "PR GUNW only",
                        "mask_provenance_policy": "explicit aoi_mask_applied tag, or exact legacy source science pin plus source granule tag",
                        "caveat": "The candidate checker rejects or withholds a candidate; it cannot prove a landslide from these data alone.",
                    },
                    "results": rows,
                }
                if any(row.get("status") == "NOT_MEASURABLE_IN_RETAINED_EXPORTS" for row in rows):
                    report["candidate_checks"]["status"] = "COMPLETED_WITH_UNOBSERVED_TARGETS"
                    report["warnings"].append("ONE_OR_MORE_CANDIDATE_TARGETS_NOT_MEASURABLE")

    report["status"] = "FAIL" if report["errors"] else "PASS_WITH_LIMITATIONS" if report["warnings"] else "PASS"
    (out_root / "science-diagnostics.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--science-root", required=True, type=Path)
    parser.add_argument("--exports-root", required=True, type=Path)
    parser.add_argument("--out-root", required=True, type=Path)
    parser.add_argument("--expected-science-commit", required=True)
    parser.add_argument("--aoi", choices=("source", "langtang", "lhende", "custom"), default="custom")
    parser.add_argument("--stats-csv", type=Path)
    parser.add_argument("--candidates-csv", type=Path)
    parser.add_argument("--run-candidate-check", action="store_true")
    args = parser.parse_args()
    report = run_diagnostics(
        args.science_root, args.exports_root, args.out_root,
        expected_science_commit=args.expected_science_commit,
        aoi=args.aoi, stats_csv=args.stats_csv, candidates_csv=args.candidates_csv,
        run_candidate_check=args.run_candidate_check,
    )
    print("EXPORT_SCIENCE_DIAGNOSTICS_STATUS=" + str(report["status"]))
    print("PIXEL_STACK_STATUS=" + str(report["pixel_stack"].get("status")))
    print("CANDIDATE_CHECK_STATUS=" + str(report["candidate_checks"].get("status")))
    print("REPORT_PATH=" + str((args.out_root / "science-diagnostics.json").resolve()))
    return 2 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
