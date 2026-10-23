"""Verify processed site-field rasters from the CC BY 4.0 author ZIP.

Example:
    python -m tools.know_place.verify_author_fields archive.zip --output report.json

This validates the archive manifest and recomputes stored R from the exported
dE/dN bands. It does not reproduce raw GOFF inputs or the full-footprint screen.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile, BadZipFile

import numpy as np
import rasterio
from rasterio.io import MemoryFile

from .author_parity import author_coherence_map


def _hash(data: bytes, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    digest.update(data)
    return digest.hexdigest()


def _check_field_payload(filename: str, payload: bytes) -> dict[str, Any]:
    with MemoryFile(payload) as mem:
        with mem.open() as src:
            if src.count != 3:
                raise ValueError(f"FIELD_BAND_COUNT_NOT_3:{filename}:{src.count}")
            if (src.width, src.height) != (80, 73):
                raise ValueError(f"FIELD_SHAPE_NOT_80x73:{filename}:{src.width}x{src.height}")
            if src.crs is None or src.crs.to_epsg() != 4326:
                raise ValueError(f"FIELD_CRS_NOT_EPSG4326:{filename}:{src.crs}")
            if src.descriptions[0] != "dE_m ground-referenced east displacement":
                raise ValueError(f"FIELD_BAND_1_DESCRIPTION_MISMATCH:{filename}")
            if src.descriptions[1] != "dN_m ground-referenced north displacement":
                raise ValueError(f"FIELD_BAND_2_DESCRIPTION_MISMATCH:{filename}")
            if src.descriptions[2] != "R directional coherence, 5x5 window":
                raise ValueError(f"FIELD_BAND_3_DESCRIPTION_MISMATCH:{filename}")
            east, north, reference_r = src.read([1, 2, 3]).astype(np.float64)
            nodata = src.nodata
            profile = {
                "width": src.width,
                "height": src.height,
                "crs": src.crs.to_string(),
                "bands": src.count,
                "dtypes": list(src.dtypes),
                "nodata": "NaN" if nodata is not None and np.isnan(nodata) else nodata,
                "bounds": [float(v) for v in src.bounds],
                "transform": [float(v) for v in src.transform],
            }

    calculated_r = author_coherence_map(east, north)
    finite_calc = np.isfinite(calculated_r)
    finite_ref = np.isfinite(reference_r)
    common = finite_calc & finite_ref
    if not common.any():
        raise ValueError(f"FIELD_NO_COMMON_FINITE_R:{filename}")
    difference = np.abs(calculated_r[common] - reference_r[common])
    result = {
        "filename": filename,
        "bytes": len(payload),
        "md5": _hash(payload, "md5"),
        "sha256": _hash(payload, "sha256"),
        "profile": profile,
        "finite_dE_dN_cells": int((np.isfinite(east) & np.isfinite(north)).sum()),
        "finite_reference_R_cells": int(finite_ref.sum()),
        "finite_recomputed_R_cells": int(finite_calc.sum()),
        "common_finite_R_cells": int(common.sum()),
        "finite_masks_equal": bool(np.array_equal(finite_calc, finite_ref)),
        "median_absolute_error": float(np.median(difference)),
        "p95_absolute_error": float(np.percentile(difference, 95)),
        "maximum_absolute_error": float(difference.max()),
        "errors_above_1e_6": int((difference > 1e-6).sum()),
        "R_band_match": bool(np.array_equal(finite_calc, finite_ref) and float(difference.max()) <= 1e-6),
    }
    return result


def verify_author_archive(archive_path: str | Path, expected_field_count: int = 5) -> dict[str, Any]:
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"AUTHOR_ARCHIVE_NOT_FOUND:{archive}")
    if not isinstance(expected_field_count, int) or expected_field_count < 1:
        raise ValueError("EXPECTED_FIELD_COUNT_MUST_BE_POSITIVE")
    archive_bytes = archive.read_bytes()
    report: dict[str, Any] = {
        "schema_version": "know-place-author-field-verification/1.0",
        "archive": {
            "filename": archive.name,
            "bytes": len(archive_bytes),
            "md5": _hash(archive_bytes, "md5"),
            "sha256": _hash(archive_bytes, "sha256"),
        },
        "manifest": {},
        "site_fields": [],
        "raw_goff_h5_in_archive": False,
        "full_footprint_per_pair_offset_rasters_in_archive": False,
        "status": "BLOCKED",
    }

    try:
        with ZipFile(archive) as zf:
            names = set(zf.namelist())
            broken = zf.testzip()
            if broken is not None:
                raise ValueError(f"ZIP_CRC_FAILURE:{broken}")
            if "MANIFEST.json" not in names:
                raise ValueError("ARCHIVE_MANIFEST_MISSING")
            manifest = json.loads(zf.read("MANIFEST.json"))
            listed = manifest.get("manifest")
            if not isinstance(listed, list):
                raise ValueError("ARCHIVE_MANIFEST_LIST_INVALID")
            payloads: dict[str, bytes] = {}
            missing: list[str] = []
            mismatches: list[dict[str, Any]] = []
            present = 0
            for entry in listed:
                path = str(entry.get("path", ""))
                if not path:
                    mismatches.append({"path": path, "reason": "EMPTY_PATH"})
                    continue
                if path not in names:
                    missing.append(path)
                    continue
                payload = zf.read(path)
                present += 1
                actual_size = len(payload)
                actual_md5 = _hash(payload, "md5")
                if actual_size != int(entry["bytes"]) or actual_md5 != str(entry["md5"]):
                    mismatches.append({
                        "path": path,
                        "expected_bytes": int(entry["bytes"]),
                        "actual_bytes": actual_size,
                        "expected_md5": str(entry["md5"]),
                        "actual_md5": actual_md5,
                    })
                if path.startswith("fields/offsets_") and path.endswith(".tif"):
                    payloads[path] = payload
            fields: list[dict[str, Any]] = []
            for path in sorted(payloads):
                fields.append(_check_field_payload(path, payloads[path]))
            report["manifest"] = {
                "declared_files": int(manifest.get("files", len(listed))),
                "zip_entry_count": len(names),
                "manifest_payloads_present": present,
                "manifest_paths_missing_from_zip": missing,
                "payload_size_or_md5_mismatches": mismatches,
                "zip_entries_not_listed_in_manifest": sorted(names - {str(x.get("path", "")) for x in listed}),
                "declared_bytes": int(manifest.get("total_bytes", 0)),
            }
            report["site_fields"] = fields
            report["raw_goff_h5_in_archive"] = any(name.lower().endswith((".h5", ".hdf5")) for name in names)
            report["full_footprint_per_pair_offset_rasters_in_archive"] = any(
                field["profile"]["width"] >= 4000 and field["profile"]["height"] >= 4000 for field in fields
            )
            all_payloads_verified = present > 0 and not missing and not mismatches
            fields_valid = len(fields) == expected_field_count and all(x["R_band_match"] for x in fields)
            report["status"] = "PASS_PROCESSED_FIELD_R_VERIFIED" if all_payloads_verified and fields_valid else "BLOCKED"
    except BadZipFile as exc:
        raise ValueError(f"INVALID_ZIP_ARCHIVE:{archive}") from exc

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Original Zenodo CC BY 4.0 data-and-code ZIP")
    parser.add_argument("--output", type=Path, help="Optional path for a JSON verification report")
    parser.add_argument("--expected-fields", type=int, default=5, help="Expected number of per-pair site-field TIFFs")
    args = parser.parse_args()
    report = verify_author_archive(args.archive, expected_field_count=args.expected_fields)
    rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "PASS_PROCESSED_FIELD_R_VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
