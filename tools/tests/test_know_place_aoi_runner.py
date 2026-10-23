from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.know_place.aoi_request import REQUEST_SCHEMA, validate_aoi_request
from tools.know_place.aoi_runner import (
    AOIRunError,
    _download_exact_product,
    _exact_bytes,
    _maturity,
    _product_name,
    _preview,
    _trusted_download_url,
    discover_nisar_goff,
)
import numpy as np

PAIR_NAMES = [
    "NISAR_L2_PR_GOFF_023_098_A_016_024_4000_SH_20260620T233921_20260620T233956_20260702T233920_20260702T233955_X05026_N_F_J_001.h5",
    "NISAR_L2_PR_GOFF_024_098_A_016_025_4000_SH_20260702T233920_20260702T233955_20260714T233920_20260714T233954_P05023_F_F_J_001.h5",
]

def request():
    return validate_aoi_request({
        "schema_version": REQUEST_SCHEMA,
        "aoi": {"type": "Polygon", "wkt": "POLYGON ((85.52 28.28, 85.54 28.28, 85.54 28.30, 85.52 28.30, 85.52 28.28))", "crs": "EPSG:4326"},
        "date_range": {"start": "2026-06-20", "end": "2026-07-14", "inclusive": True},
        "hazard_mode": "landslide",
        "analysis_mode": "retrospective_validation",
        "source_adapters": ["NISAR_GOFF"],
        "product_selection": {"allowed_maturities": ["PROVISIONAL"]},
    })

def product(name, *, maturity="PROVISIONAL", polarization="HH", bytes_size=101):
    url = f"https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GOFF_{maturity}_V1/{name}"
    return SimpleNamespace(
        properties={
            "granuleName": name,
            "dataMaturity": maturity,
            "mainBandPolarization": polarization,
            "fileSizeBytes": bytes_size,
        },
        get_urls=lambda: [url],
    )

def test_asf_catalog_contract_preserves_exact_ids_and_query_evidence(monkeypatch):
    calls = {}
    fake = SimpleNamespace(search=lambda **kwargs: (calls.update(kwargs) or [product(n) for n in PAIR_NAMES]))
    monkeypatch.setitem(sys.modules, "asf_search", fake)

    products, manifest = discover_nisar_goff(request())

    assert [item["granule_name"] for item in products] == PAIR_NAMES
    assert manifest["eligible_count"] == 2
    assert manifest["query"]["start_utc"] == "2026-06-20T00:00:00Z"
    assert manifest["query"]["end_utc"] == "2026-07-14T23:59:59Z"
    assert calls["processingLevel"] == "GOFF"
    assert calls["intersectsWith"].startswith("POLYGON ((")
    assert calls["mainBandPolarization"] == "HH"
    assert all(row["decision"] == "ELIGIBLE_CATALOG_CANDIDATE" for row in manifest["candidates"])

def test_catalog_maturity_allowlist_excludes_unselected_variants(monkeypatch):
    fake = SimpleNamespace(search=lambda **kwargs: [product(PAIR_NAMES[0], maturity="BETA")])
    monkeypatch.setitem(sys.modules, "asf_search", fake)

    products, manifest = discover_nisar_goff(request())

    assert products == []
    assert manifest["eligible_count"] == 0
    assert manifest["candidates"][0]["decision"] == "EXCLUDED_MATURITY_NOT_ALLOWED"

def test_catalog_product_identity_and_trusted_host_gates():
    good_url = f"https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GOFF_PROVISIONAL_V1/{PAIR_NAMES[0]}"
    assert _trusted_download_url(good_url)
    assert not _trusted_download_url(good_url.replace("https://", "http://"))
    assert not _trusted_download_url("https://not-asf.example.com/a.h5")
    assert _product_name({"granuleName": PAIR_NAMES[0]}, [good_url]) == PAIR_NAMES[0]
    assert _maturity({"dataMaturity": "PROVISIONAL"}, [good_url])[0] == "PROVISIONAL"
    assert _exact_bytes({"fileSizeBytes": "101"}) == 101
    assert _exact_bytes({"fileSizeBytes": "101.5"}) is None
    with pytest.raises(AOIRunError, match="CATALOG_MATURITY_UNRESOLVED"):
        _maturity({}, ["https://nisar.asf.earthdatacloud.nasa.gov/unknown/a.h5"])

def test_download_cache_reuses_only_source_receipt_with_matching_sha256(tmp_path, monkeypatch):
    name = PAIR_NAMES[0]
    url = f"https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GOFF_PROVISIONAL_V1/{name}"
    cache_root = tmp_path / "cache"
    product_dir = cache_root / hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    product_dir.mkdir(parents=True)
    target = product_dir / name
    data = b"synthetic-source-data-for-cache-contract"
    target.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    url_fingerprint = hashlib.sha256(url.encode("utf-8")).hexdigest()
    (product_dir / f"{name}.source-receipt.json").write_text(json.dumps({
        "schema_version": "know-place-source-receipt/1.0",
        "granule_name": name, "release_id": "X05026", "maturity": "PROVISIONAL",
        "source_url_fingerprint": url_fingerprint, "source_sha256": digest,
        "source_bytes": len(data),
    }))
    fake = SimpleNamespace(download_urls=lambda **kwargs: pytest.fail("valid cache should not download again"))
    monkeypatch.setitem(sys.modules, "asf_search", fake)

    path, evidence = _download_exact_product({
        "granule_name": name, "release_id": "X05026", "maturity": "PROVISIONAL",
        "download_url": url, "source_bytes": len(data),
    }, cache_root, session=object())

    assert path == target
    assert evidence["source_sha256"] == digest
    assert evidence["cache_status"] == "REUSED_HASH_VERIFIED"

def test_preview_is_downsampled_visual_only_and_keeps_nodata_explicit():
    values = np.arange(10000, dtype=float).reshape(100, 100)
    values[0:10, 0:10] = np.nan
    preview = _preview(values, np.arange(100, dtype=float), np.arange(100, dtype=float),
                       ((10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0), (10.0, 10.0)))
    assert max(preview["width"], preview["height"]) <= 72
    assert preview["description"].startswith("Median magnitude per block")
    assert len(preview["aoi_ring_xy"]) == 5
