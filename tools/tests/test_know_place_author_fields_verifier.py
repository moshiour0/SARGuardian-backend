from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from tools.know_place.author_parity import author_coherence_map
from tools.know_place.verify_author_fields import verify_author_archive


def _tiny_field_tiff() -> bytes:
    east = np.ones((73, 80), dtype=np.float32)
    north = np.zeros((73, 80), dtype=np.float32)
    east[0, 0] = np.nan
    north[0, 0] = np.nan
    r = author_coherence_map(east.astype(float), north.astype(float)).astype(np.float32)
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=80,
            height=73,
            count=3,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(85.5, 28.32, 0.001, 0.001),
            nodata=np.nan,
        ) as dst:
            dst.write(east, 1)
            dst.write(north, 2)
            dst.write(r, 3)
            dst.set_band_description(1, "dE_m ground-referenced east displacement")
            dst.set_band_description(2, "dN_m ground-referenced north displacement")
            dst.set_band_description(3, "R directional coherence, 5x5 window")
        return mem.read()


def _write_archive(path: Path, tiff_bytes: bytes) -> None:
    entry = {
        "path": "fields/offsets_synthetic.tif",
        "bytes": len(tiff_bytes),
        "md5": hashlib.md5(tiff_bytes).hexdigest(),
    }
    manifest = {"record": "synthetic-test", "files": 1, "total_bytes": len(tiff_bytes), "manifest": [entry]}
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr(entry["path"], tiff_bytes)
        zf.writestr("MANIFEST.json", json.dumps(manifest))


def test_field_verifier_accepts_manifest_valid_author_r_band(tmp_path: Path) -> None:
    archive = tmp_path / "synthetic-author.zip"
    _write_archive(archive, _tiny_field_tiff())
    report = verify_author_archive(archive, expected_field_count=1)
    assert report["status"] == "PASS_PROCESSED_FIELD_R_VERIFIED"
    assert report["manifest"]["payload_size_or_md5_mismatches"] == []
    assert len(report["site_fields"]) == 1
    assert report["site_fields"][0]["R_band_match"] is True
    assert report["site_fields"][0]["maximum_absolute_error"] <= 1e-6


def test_field_verifier_flags_r_band_mismatch(tmp_path: Path) -> None:
    archive = tmp_path / "synthetic-author-bad-r.zip"
    payload = _tiny_field_tiff()
    import io
    with MemoryFile(payload) as mem:
        with mem.open() as src:
            arrays = src.read().astype(np.float32)
            profile = src.profile
            descriptions = src.descriptions
    arrays[2, 3, 3] = np.float32(0.25)
    out = io.BytesIO()
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(arrays)
            for index, description in enumerate(descriptions, 1):
                dst.set_band_description(index, description)
        out.write(mem.read())
    bad_payload = out.getvalue()
    archive.unlink(missing_ok=True)
    _write_archive(archive, bad_payload)
    report = verify_author_archive(archive, expected_field_count=1)
    assert report["status"] == "BLOCKED"
    assert report["site_fields"][0]["R_band_match"] is False


def test_field_verifier_checks_each_manifest_payload_hash(tmp_path: Path) -> None:
    archive = tmp_path / "synthetic-manifest-bad.zip"
    payload = _tiny_field_tiff()
    _write_archive(archive, payload)
    # Damage the manifest MD5 while preserving a readable ZIP member.
    with ZipFile(archive, "r") as zf:
        members = {name: zf.read(name) for name in zf.namelist()}
    manifest = json.loads(members["MANIFEST.json"])
    manifest["manifest"][0]["md5"] = "0" * 32
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zf:
        for name, value in members.items():
            zf.writestr(name, json.dumps(manifest) if name == "MANIFEST.json" else value)
    report = verify_author_archive(archive, expected_field_count=1)
    assert report["status"] == "BLOCKED"
    assert report["manifest"]["payload_size_or_md5_mismatches"][0]["path"] == "fields/offsets_synthetic.tif"


def test_manifest_allows_readme_and_nc_component_as_separate_zenodo_record_files(tmp_path: Path) -> None:
    archive = tmp_path / "multipart-record.zip"
    payload = _tiny_field_tiff()
    entry = {
        "path": "fields/offsets_synthetic.tif",
        "bytes": len(payload),
        "md5": hashlib.md5(payload).hexdigest(),
    }
    external_readme = {"path": "README.md", "bytes": 10, "md5": "1" * 32}
    external_extent = {
        "path": "extent_CC-BY-NC-4.0/flow_extent.shp",
        "bytes": 10,
        "md5": "2" * 32,
    }
    manifest = {
        "record": "synthetic-multipart-record",
        "files": 3,
        "total_bytes": len(payload) + 20,
        "manifest": [entry, external_readme, external_extent],
    }
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr(entry["path"], payload)
        zf.writestr("MANIFEST.json", json.dumps(manifest))
    report = verify_author_archive(archive, expected_field_count=1)
    assert report["status"] == "PASS_PROCESSED_FIELD_R_VERIFIED"
    assert report["manifest"]["unexpected_missing_paths"] == []
    assert report["manifest"]["payload_size_or_md5_mismatches"] == []
