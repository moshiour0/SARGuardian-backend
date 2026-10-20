from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
from types import SimpleNamespace

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
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def parse_pair_dates(self, granule):
        assert download.normal_name(granule) == download.normal_name(WANTED)
        return date(2025, 11, 25), date(2025, 12, 7)

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


def test_exact_product_lookup_uses_pinned_source_catalog_and_narrow_pair_dates():
    source = FakeSourceAcquisition([row(WANTED + "_nearby.h5"), row()])
    match, start, end = download.find_exact_source_product(source, WANTED, "GUNW", "PROVISIONAL")

    assert match["granuleName"] == WANTED + ".h5"
    assert start == "2025-11-25"
    assert end == "2025-12-07"
    assert source.calls == [
        (
            "2025-11-25",
            "2025-12-07",
            {"platform": "NISAR", "processingLevel": "GUNW"},
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
