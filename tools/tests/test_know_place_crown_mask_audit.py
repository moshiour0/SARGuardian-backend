from __future__ import annotations
import hashlib
import io
import json
import zipfile

import numpy as np
import pytest

import tools.know_place.crown_mask_audit as audit


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _npz_bytes(**arrays) -> bytes:
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    return buffer.getvalue()


def _write_fixture(tmp_path, monkeypatch, *, corrupt_pair_zero_mask=False):
    # Tiny but internally complete native grid; monkeypatching keeps the audit
    # logic identical while making its zip/manifest contract test run in CI.
    monkeypatch.setattr(audit, "EPSG", 4326)
    monkeypatch.setattr(audit, "WIDTH", 8)
    monkeypatch.setattr(audit, "HEIGHT", 8)
    monkeypatch.setattr(audit, "X0", 0.0)
    monkeypatch.setattr(audit, "Y0", 6.0)
    monkeypatch.setattr(audit, "DX", 1.0)
    monkeypatch.setattr(audit, "DY", -1.0)
    monkeypatch.setattr(audit, "CROWN", (1.0, 1.0, 4.0, 4.0))
    monkeypatch.setattr(audit, "BOX", (0.0, 0.0, 7.0, 7.0))
    monkeypatch.setattr(audit, "EXPECTED_CROWN_CELLS", 9)
    pairs = tuple((row[0], row[1], 4, 3) for row in audit.PAIRS)
    monkeypatch.setattr(audit, "PAIRS", pairs)

    x_site = (np.arange(6, dtype=float) + 0.5)
    y_site = 6.0 - (np.arange(6, dtype=float) + 0.5)
    site_mask = audit.geographic_mask(x_site, y_site)
    extent = [0.5, 5.5, 0.5, 5.5]
    crop = audit.endpoint_crop((6, 6), extent)
    np.testing.assert_array_equal(site_mask, crop)
    assert int(site_mask.sum()) == 9

    x_diag = np.arange(8, dtype=float) + 0.5
    y_diag = 6.0 - (np.arange(8, dtype=float) + 0.5)
    diag_mask = audit.geographic_mask(x_diag, y_diag)
    assert int(diag_mask.sum()) == 9

    site_files = {}
    diag_files = {}
    report_rows = []
    for i, (interval, prefix, _, _) in enumerate(pairs):
        site = site_mask.astype(np.uint8).copy()
        if i == 0 and corrupt_pair_zero_mask:
            site[0, 0] = 1
        valid = np.zeros((6, 6), dtype=np.uint8)
        positions = np.argwhere(site_mask)[:4]
        for row, col in positions:
            valid[row, col] = 1
        r = np.full((6, 6), np.nan, dtype=np.float32)
        for row, col in np.argwhere(site_mask)[:3]:
            r[row, col] = 0.5
        site_name = prefix + "_author_site_series_arrays.npz"
        diag_name = prefix + "_diagnostic_arrays.npz"
        site_bytes = _npz_bytes(
            east_m=np.ones((6, 6), dtype=np.float32),
            north_m=np.ones((6, 6), dtype=np.float32),
            horizontal_magnitude_m=np.ones((6, 6), dtype=np.float32),
            directional_coherence_R=r,
            valid_mask=valid,
            crown_mask=site,
        )
        diag_r = np.full((8, 8), np.nan, dtype=np.float32)
        diag_bytes = _npz_bytes(
            east_m=np.ones((8, 8), dtype=np.float32),
            north_m=np.ones((8, 8), dtype=np.float32),
            horizontal_magnitude_m=np.ones((8, 8), dtype=np.float32),
            directional_coherence_R=diag_r,
            valid_mask=np.zeros((8, 8), dtype=np.uint8),
            crown_mask=diag_mask.astype(np.uint8),
            x_coordinates_m=x_diag,
            y_coordinates_m=y_diag,
        )
        site_files[site_name] = site_bytes
        diag_files[diag_name] = diag_bytes
        start, end = interval.split("/")
        report_rows.append({
            "pair": start + "->" + end,
            "source_grid": {
                "epsg": 4326,
                "original_width": 8,
                "original_height": 8,
                "window_shape": [6, 6],
                "x_posting_m": 1.0,
                "y_posting_m": -1.0,
                "window_slices": {
                    "row_start": 0, "row_stop": 6,
                    "column_start": 0, "column_stop": 6,
                },
            },
            "extent_lonlat": extent,
            # Historical author report uses this field for the site-array NPZ.
            "diagnostic_npz": site_name,
            "diagnostic_arrays_sha256": hashlib.sha256(site_bytes).hexdigest(),
        })

    crown_wkt = "POLYGON ((1.0 1.0, 4.0 1.0, 4.0 4.0, 1.0 4.0, 1.0 1.0))"
    box_wkt = "POLYGON ((0.0 0.0, 7.0 0.0, 7.0 7.0, 0.0 7.0, 0.0 0.0))"
    inputs = {"crown_wkt": crown_wkt, "reference_box_wkt": box_wkt}
    source = {
        "repository_branch": "test",
        "repository_commit": "deadbeef",
        "source_sha256_count": 5,
        "author_exact_source_sha256_count": 5,
        "author_release_id": "P05023",
        "products": [{"release_id": "P05023"} for _ in range(5)],
    }
    cleanup = {
        "workflow_run_id": "fixture-123",
        "status": "PASS",
        "raw_hdf5_deleted_count": 5,
        "raw_hdf5_files_remaining_count": 0,
        "raw_hdf5_uploaded": False,
        "remote_derived_bundle_verification": "PASS",
        "remote_upload_receipt_copy_verification": "PASS",
    }
    status = {"status": "OUTPUTS_WRITTEN", "analysis_metrics_complete": True}
    report = {"pair_reports": report_rows}
    inner_zip = _zip_bytes({"derived-only-placeholder.txt": b"no raw products"})
    outer_files = {
        "author-exact-derived-results.zip": inner_zip,
        "know-place-inputs.json": _json_bytes(inputs),
        "author-exact-source-manifest.json": _json_bytes(source),
        "author-exact-raw-cleanup-receipt.json": _json_bytes(cleanup),
        "author-exact-analysis-status.json": _json_bytes(status),
        "author-raw-site-series-report.json": _json_bytes(report),
        **site_files,
        **diag_files,
    }
    run_path = tmp_path / "synthetic-run.zip"
    run_path.write_bytes(_zip_bytes(outer_files))

    author_rows = []
    null_rows = []
    for interval, _, disp_n, r_n in pairs:
        start, end = interval.split("/")
        author_rows.append({"a": start.replace("-", ""), "b": end.replace("-", ""), "n": disp_n})
        null_rows.append({"pair": start + "->" + end, "n_px": r_n})
    author_path = tmp_path / "synthetic-author.zip"
    author_path.write_bytes(_zip_bytes({
        "tables/nisar_pot_series.json": _json_bytes(author_rows),
        "tables/polygon_null.json": _json_bytes(null_rows),
    }))
    monkeypatch.setattr(audit, "AUTHOR_ARCHIVE_SHA256", hashlib.sha256(author_path.read_bytes()).hexdigest())
    return run_path, author_path


def test_full_archive_audit_passes_on_synthetic_known_answer_package(tmp_path, monkeypatch):
    run_path, author_path = _write_fixture(tmp_path, monkeypatch)
    result = audit.audit_crown_masks(run_path, author_path)
    assert result["status"] == "PASS"
    assert result["pair_count"] == 5
    assert all(row["status"] == "PASS" for row in result["pairs"])
    assert all(row["site_vs_geographic_xor_cells"] == 0 for row in result["pairs"])
    assert all(row["site_vs_endpoint_crop_xor_cells"] == 0 for row in result["pairs"])
    assert all(row["site_vs_diagnostic_global_xor_cells"] == 0 for row in result["pairs"])
    assert result["inputs"]["raw_hdf5_outer_members"] == 0
    assert result["inputs"]["raw_hdf5_nested_members"] == 0
    assert result["author_original_vector_mask_parity"].startswith("UNVERIFIED")
    assert result["hazard_detection_status"] == "NOT_EVALUATED"


def test_full_archive_audit_fails_closed_when_a_saved_mask_is_corrupted(tmp_path, monkeypatch):
    run_path, author_path = _write_fixture(tmp_path, monkeypatch, corrupt_pair_zero_mask=True)
    result = audit.audit_crown_masks(run_path, author_path)
    assert result["status"] == "FAIL"
    assert result["pairs"][0]["status"] == "FAIL"
    assert result["pairs"][0]["site_vs_geographic_xor_cells"] == 1
    assert result["pairs"][0]["site_vs_endpoint_crop_xor_cells"] == 1
    assert "CROSS_PAIR_MASK_HASH_MISMATCH" in result["failures"]


def test_audit_rejects_author_archive_hash_mismatch(tmp_path, monkeypatch):
    run_path, author_path = _write_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(audit, "AUTHOR_ARCHIVE_SHA256", "0" * 64)
    with pytest.raises(audit.CrownMaskAuditError, match="AUTHOR_ARCHIVE_SHA256_MISMATCH"):
        audit.audit_crown_masks(run_path, author_path)
