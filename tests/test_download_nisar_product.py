from __future__ import annotations

import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "download_nisar_product.py"
spec = importlib.util.spec_from_file_location("download_nisar_product", TOOL)
assert spec and spec.loader
download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download)


WANTED = (
    "NISAR_L2_PR_GUNW_006_048_D_074_007_2000_SH_"
    "20251125T125813_20251125T125848_20251207T125814_20251207T125849_X05010_N_F_J_001"
)
ASF_URL = "https://datapool.asf.alaska.edu/NISAR/test-product.h5"


class FakeSourceAcquisition:
    INTERFEROMETRIC = ["GUNW", "GOFF", "RUNW", "ROFF", "RIFG"]

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query_by_year(self, start, end, **params):
        self.calls.append((start, end, params))
        return self.rows


def row(name=WANTED + ".h5", url=ASF_URL, **extra):
    return {
        "granuleName": name,
        "productType": "GUNW",
        "downloadUrl": url,
        "sizeMB": 50.0,
        **extra,
    }


def test_exact_product_lookup_reuses_original_recon_nisar_query_and_date_window():
    source = FakeSourceAcquisition([row(WANTED + "_nearby.h5"), row()])
    match, start, end = download.find_exact_source_product(source, WANTED, "GUNW", "PROVISIONAL", catalog_end="2026-10-20")

    assert match["granuleName"] == WANTED + ".h5"
    assert start == "2025-01-01"
    assert end == "2026-10-20"
    assert source.calls == [
        (
            "2025-01-01",
            "2026-10-20",
            {"platform": "NISAR", "processingLevel": "GUNW,GOFF,RUNW,ROFF,RIFG"},
        )
    ]


def test_exact_product_lookup_rejects_missing_or_ambiguous_matches():
    with __import__("pytest").raises(LookupError, match="MATCH_COUNT_0"):
        download.find_exact_source_product(
            FakeSourceAcquisition([row(WANTED + "_different.h5")]), WANTED, "GUNW", "PROVISIONAL"
        )

    with __import__("pytest").raises(LookupError, match="MATCH_COUNT_2"):
        download.find_exact_source_product(
            FakeSourceAcquisition([row(), row()]), WANTED, "GUNW", "PROVISIONAL"
        )


def test_exact_product_lookup_checks_maturity_when_catalog_exposes_it():
    source = FakeSourceAcquisition([row(dataMaturity="BETA")])
    with __import__("pytest").raises(ValueError, match="MATURITY_MISMATCH"):
        download.find_exact_source_product(source, WANTED, "GUNW", "PROVISIONAL")


def test_exact_product_lookup_rejects_wrong_product_family():
    wrong = row()
    wrong["productType"] = "GOFF"
    with __import__("pytest").raises(LookupError, match="MATCH_COUNT_0"):
        download.find_exact_source_product(
            FakeSourceAcquisition([wrong]), WANTED, "GUNW", "PROVISIONAL"
        )


def test_catalog_url_must_be_https_and_from_asf():
    assert download.trusted_asf_url("https://datapool.asf.alaska.edu/a.h5")
    assert download.trusted_asf_url("https://nisar.asf.earthdatacloud.nasa.gov/a.h5")
    assert not download.trusted_asf_url("http://datapool.asf.alaska.edu/a.h5")
    assert not download.trusted_asf_url("https://example.invalid/a.h5")


def test_catalog_size_estimate_supports_asf_size_mb_and_byte_fields():
    assert download.size_estimate_bytes({"sizeMB": 2}) == 2 * 1024 * 1024
    assert download.size_estimate_bytes({"size_mb": 3}) == 3 * 1024 * 1024
    assert download.size_estimate_bytes({"sizeBytes": "5678"}) == 5678
    assert download.size_estimate_bytes({"sizeMB": -1}) is None


def test_load_source_acquisition_sets_requested_aoi_and_records_module_hash(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    module_file = src / "nisar_acquisition.py"
    module_file.write_text(
        "AOI_NAME = None\n"
        "def set_aoi(name):\n"
        "    global AOI_NAME\n"
        "    AOI_NAME = name\n",
        encoding="utf-8",
    )
    module, module_hash = download.load_source_acquisition(tmp_path, "source")
    assert module.AOI_NAME == "source"
    assert len(module_hash) == 64


class FakeASFProduct:
    def __init__(self, name=WANTED + ".h5", url=ASF_URL, **extra):
        self.properties = {
            "sceneName": name,
            "fileName": name,
            "url": url,
            "bytes": 50 * 1024 * 1024,
            "processingLevel": "GUNW",
            **extra,
        }

    def get_urls(self):
        return [self.properties["url"]]


class FailedSourceAcquisition(FakeSourceAcquisition):
    def query_by_year(self, start, end, **params):
        self.calls.append((start, end, params))
        raise RuntimeError("ASF Search API returned HTTP 400")


def test_official_asf_search_client_is_used_when_source_query_returns_http_error(monkeypatch):
    source = FailedSourceAcquisition([])
    calls = []
    product = FakeASFProduct()

    def search(**kwargs):
        calls.append(kwargs)
        if kwargs["start"].startswith("2025-"):
            return [product]
        return []

    monkeypatch.setitem(sys.modules, "asf_search", SimpleNamespace(search=search))
    record, start, end = download.find_exact_source_product(
        source, WANTED, "GUNW", "PROVISIONAL", catalog_end="2026-10-20"
    )

    assert record["granuleName"] == WANTED
    assert record["downloadUrl"] == ASF_URL
    assert record["_sarguardian_discovery_backend"] == "asf_search.search"
    assert start == "2025-01-01" and end == "2026-10-20"
    assert len(calls) == 2
    assert calls[0] == {
        "dataset": "NISAR",
        "intersectsWith": "POLYGON((85.4 28.2,85.5 28.2,85.5 28.3,85.4 28.3,85.4 28.2))",
        "processingLevel": ["GUNW", "GOFF", "RUNW", "ROFF", "RIFG"],
        "start": "2025-01-01T00:00:00Z",
        "end": "2025-12-31T23:59:59Z",
        "maxResults": 2000,
    }


def test_official_asf_search_client_requires_exact_name_and_trusted_url(monkeypatch):
    source = FailedSourceAcquisition([])
    monkeypatch.setitem(
        sys.modules,
        "asf_search",
        SimpleNamespace(
            search=lambda **kwargs: [
                FakeASFProduct(WANTED + "_nearby.h5"),
                FakeASFProduct(WANTED + ".h5", "https://example.invalid/raw.h5"),
            ]
        ),
    )
    import pytest
    with pytest.raises(LookupError, match="MATCH_COUNT_0"):
        download.find_exact_source_product(
            source, WANTED, "GUNW", "PROVISIONAL", catalog_end="2025-12-31"
        )
