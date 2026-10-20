from __future__ import annotations

import importlib.util
import urllib.error
from pathlib import Path
from types import SimpleNamespace

TOOL = Path(__file__).resolve().parents[1] / "tools" / "download_nisar_product.py"
spec = importlib.util.spec_from_file_location("download_nisar_product", TOOL)
assert spec and spec.loader
download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download)


class FakeASFProduct:
    def __init__(self, name, url="https://nisar.asf.earthdatacloud.nasa.gov/NISAR/test.h5", **extra):
        self.properties = {"granuleName": name, "downloadUrl": url, "sizeMB": 123.5, **extra}

    def get_urls(self):
        return [self.properties["downloadUrl"]]


def _module_with_search(search):
    return SimpleNamespace(search=search)


def test_exact_asf_match_requires_full_public_name_match():
    wanted = "NISAR_L2_PR_GUNW_006_048_D_074_007_2000_SH_X05010"
    rows = [FakeASFProduct(wanted + "_other"), FakeASFProduct(wanted + ".h5")]
    match, count = download.exact_asf_match(rows, wanted)
    assert count == 1
    assert match is rows[1]


def test_exact_asf_match_refuses_duplicate_catalog_records():
    wanted = "NISAR_L2_PR_GOFF_006_048_D_074_007_2000_SH_X05010"
    match, count = download.exact_asf_match(
        [FakeASFProduct(wanted), FakeASFProduct(wanted + ".h5")], wanted
    )
    assert match is None
    assert count == 2


def test_asf_size_bytes_supports_size_mb_and_byte_fields():
    assert download.asf_size_bytes({"sizeMB": 2}) == 2 * 1024 * 1024
    assert download.asf_size_bytes({"sizeBytes": "5678", "sizeMB": 2}) == 5678
    assert download.asf_size_bytes({"sizeMB": -1}) is None


def test_asf_search_uses_supported_nisar_query_and_retries_transient_500(monkeypatch):
    wanted = "NISAR_L2_PR_GUNW_006_048_D_074_007_2000_SH_X05010"
    calls = {"count": 0}
    product = FakeASFProduct(wanted + ".h5")

    def search(**kwargs):
        calls["count"] += 1
        assert kwargs == {
            "dataset": "NISAR",
            "dataMaturity": "BETA",
            "processingLevel": "GUNW",
            "granule_list": [wanted],
        }
        if calls["count"] == 1:
            raise urllib.error.HTTPError("https://api.daac.asf.alaska.edu/search", 500,
                                         "Internal Server Error", {}, None)
        return [product]

    monkeypatch.setitem(__import__("sys").modules, "asf_search", _module_with_search(search))
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)
    match, diagnostic = download.search_asf_exact_granule(wanted, "GUNW", maturity="BETA")
    assert calls["count"] == 2
    assert diagnostic["attempts"] == 2
    assert diagnostic["http_status"] == "200"
    assert diagnostic["match_count"] == 1
    assert match is not None
    assert match["granuleName"] == wanted
    assert match["_sarguardian_download_url"].startswith("https://nisar.asf.earthdatacloud.nasa.gov/")


def test_asf_search_filters_requested_maturity(monkeypatch):
    wanted = "NISAR_L2_PR_GOFF_006_048_D_074_007_2000_SH_X05010"
    product = FakeASFProduct(wanted + ".h5")
    captured = {}

    def search(**kwargs):
        captured.update(kwargs)
        return [product]

    monkeypatch.setitem(__import__("sys").modules, "asf_search", _module_with_search(search))
    match, diagnostic = download.search_asf_exact_granule(wanted, "GOFF", maturity="PROVISIONAL")
    assert captured["dataMaturity"] == "PROVISIONAL"
    assert match is not None
    assert diagnostic["match_count"] == 1


def test_asf_search_fails_closed_when_download_url_is_not_trusted(monkeypatch):
    wanted = "NISAR_L2_PR_GOFF_006_048_D_074_007_2000_SH_X05010"
    product = FakeASFProduct(wanted, "http://example.invalid/raw.h5")
    monkeypatch.setitem(__import__("sys").modules, "asf_search",
                        _module_with_search(lambda **_kwargs: [product]))
    match, diagnostic = download.search_asf_exact_granule(wanted, "GOFF")
    assert match is None
    assert diagnostic["error_type"] == "EXACT_MATCH_WITHOUT_TRUSTED_DOWNLOAD_URL"


def test_asf_search_zero_result_is_not_misreported_as_success(monkeypatch):
    wanted = "NISAR_L2_PR_GOFF_006_048_D_074_007_2000_SH_X05010"
    monkeypatch.setitem(
        __import__("sys").modules, "asf_search",
        _module_with_search(lambda **_kwargs: [FakeASFProduct(wanted + "_different")]),
    )
    match, diagnostic = download.search_asf_exact_granule(wanted, "GOFF")
    assert match is None
    assert diagnostic["http_status"] == "200"
    assert diagnostic["match_count"] == 0
    assert diagnostic["error_type"] is None
