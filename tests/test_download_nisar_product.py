from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "download_nisar_product.py"
spec = importlib.util.spec_from_file_location("download_nisar_product", TOOL)
assert spec and spec.loader
download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download)


WANTED = (
    "NISAR_L2_PR_GUNW_006_048_D_074_007_2000_SH_"
    "20251125T125813_20251125T125848_20251207T125814_20251207T125849_X05010_N_F_J_001"
)


class FakeResponse:
    def __init__(self, status_code, headers=None, reason="OK"):
        self.status_code = status_code
        self.headers = headers or {}
        self.reason = reason
        self.closed = False

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, head_response=None, get_response=None):
        self.head_response = head_response
        self.get_response = get_response
        self.head_calls = []
        self.get_calls = []

    def head(self, url, **kwargs):
        self.head_calls.append((url, kwargs))
        return self.head_response

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.get_response


class FakeSourceAcquisition:
    def __init__(self, session):
        self.session = session
        self.AOI_NAME = None

    def build_session(self):
        return self.session


def test_direct_url_uses_documented_collection_folder_and_exact_file_path():
    expected = (
        "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/"
        f"NISAR_L2_GUNW_PROVISIONAL_V1/{WANTED}/{WANTED}.h5"
    )
    assert download.direct_product_url(WANTED, "GUNW", "PROVISIONAL") == expected
    assert download.trusted_asf_url(expected)


def test_probe_direct_product_reads_exact_remote_content_length():
    url = download.direct_product_url(WANTED, "GUNW", "PROVISIONAL")
    response = FakeResponse(200, {"Content-Length": "123456789"})
    session = FakeSession(head_response=response)
    acquisition = FakeSourceAcquisition(session)

    record, returned_session, size = download.probe_direct_product(
        acquisition, WANTED, "GUNW", "PROVISIONAL"
    )

    assert session.head_calls[0][0] == url
    assert session.head_calls[0][1] == {"allow_redirects": True, "timeout": 60}
    assert session.get_calls == []
    assert record["granuleName"] == WANTED
    assert record["productType"] == "GUNW"
    assert record["maturity"] == "PROVISIONAL"
    assert record["downloadUrl"] == url
    assert record["_sarguardian_discovery_backend"] == "direct_https_known_granule"
    assert returned_session is session
    assert size == 123456789
    assert response.closed is True


def test_probe_direct_product_uses_range_get_when_head_is_not_supported():
    url = download.direct_product_url(WANTED, "GUNW", "PROVISIONAL")
    head = FakeResponse(405, reason="Method Not Allowed")
    ranged = FakeResponse(206, {"Content-Range": "bytes 0-0/987654321"}, reason="Partial Content")
    session = FakeSession(head_response=head, get_response=ranged)

    _record, _session, size = download.probe_direct_product(
        FakeSourceAcquisition(session), WANTED, "GUNW", "PROVISIONAL"
    )

    assert head.closed is True
    assert session.get_calls[0][0] == url
    assert session.get_calls[0][1] == {
        "headers": {"Range": "bytes=0-0"},
        "allow_redirects": True,
        "stream": True,
        "timeout": 60,
    }
    assert ranged.closed is True
    assert size == 987654321


def test_probe_direct_product_fails_closed_for_missing_direct_object():
    response = FakeResponse(404, reason="Not Found")
    session = FakeSession(head_response=response)
    with pytest.raises(RuntimeError, match="DIRECT_PRODUCT_HTTP_STATUS_404"):
        download.probe_direct_product(
            FakeSourceAcquisition(session), WANTED, "GUNW", "PROVISIONAL"
        )
    assert response.closed is True


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
