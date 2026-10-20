from __future__ import annotations

import importlib.util
import io
import json
import urllib.error
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "download_nisar_product.py"
spec = importlib.util.spec_from_file_location("download_nisar_product", TOOL)
assert spec and spec.loader
download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download)


def _row(name: str, url: str = "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/test.h5") -> dict:
    return {"granuleName": name, "downloadUrl": url, "sizeMB": 123.5}


def test_exact_asf_match_requires_full_public_name_match():
    wanted = "NISAR_L2_PR_GUNW_006_048_D_074_007_2000_SH_X05010"
    rows = [
        _row(wanted + "_other"),
        _row(wanted + ".h5"),
    ]
    match, count = download.exact_asf_match(rows, wanted)
    assert count == 1
    assert match is rows[1]


def test_exact_asf_match_refuses_duplicate_catalog_records():
    wanted = "NISAR_L2_PR_GOFF_006_048_D_074_007_2000_SH_X05010"
    match, count = download.exact_asf_match([_row(wanted), _row(wanted + ".h5")], wanted)
    assert match is None
    assert count == 2


def test_asf_size_bytes_supports_size_mb_and_byte_fields():
    assert download.asf_size_bytes({"sizeMB": 2}) == 2 * 1024 * 1024
    assert download.asf_size_bytes({"sizeBytes": "5678", "sizeMB": 2}) == 5678
    assert download.asf_size_bytes({"sizeMB": -1}) is None


def test_asf_search_retries_http_500_then_returns_exact_match(monkeypatch):
    wanted = "NISAR_L2_PR_GUNW_006_048_D_074_007_2000_SH_X05010"
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        assert timeout == 45
        if calls["count"] == 1:
            raise urllib.error.HTTPError(request.full_url, 500, "Internal Server Error", {}, None)
        return io.BytesIO(json.dumps({"results": [_row(wanted + ".h5")]}).encode())

    monkeypatch.setattr(download.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)
    match, diagnostic = download.search_asf_exact_granule(wanted, "GUNW")
    assert calls["count"] == 2
    assert diagnostic["attempts"] == 2
    assert diagnostic["http_status"] == "200"
    assert diagnostic["match_count"] == 1
    assert match is not None
    assert match["granuleName"] == wanted + ".h5"


def test_asf_search_fails_closed_when_download_url_is_not_trusted(monkeypatch):
    wanted = "NISAR_L2_PR_GOFF_006_048_D_074_007_2000_SH_X05010"
    body = {"results": [_row(wanted, "http://example.invalid/raw.h5")]}

    monkeypatch.setattr(
        download.urllib.request, "urlopen",
        lambda _request, timeout: io.BytesIO(json.dumps(body).encode()),
    )
    match, diagnostic = download.search_asf_exact_granule(wanted, "GOFF")
    assert match is None
    assert diagnostic["error_type"] == "UNTRUSTED_ASF_DOWNLOAD_URL"


def test_asf_search_zero_result_is_not_misreported_as_success(monkeypatch):
    wanted = "NISAR_L2_PR_GOFF_006_048_D_074_007_2000_SH_X05010"
    body = {"results": [_row(wanted + "_different")]}

    monkeypatch.setattr(
        download.urllib.request, "urlopen",
        lambda _request, timeout: io.BytesIO(json.dumps(body).encode()),
    )
    match, diagnostic = download.search_asf_exact_granule(wanted, "GOFF")
    assert match is None
    assert diagnostic["http_status"] == "200"
    assert diagnostic["match_count"] == 0
    assert diagnostic["error_type"] is None
