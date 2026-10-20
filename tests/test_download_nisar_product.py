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
        if isinstance(self.head_response, list):
            return self.head_response.pop(0)
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


def test_direct_url_uses_requested_maturity_and_product_family():
    other = download.direct_product_url(WANTED.replace("GUNW", "GOFF"), "GOFF", "BETA")
    assert "/NISAR_L2_GOFF_BETA_V1/" in other
    assert other.endswith(f"/{WANTED.replace('GUNW', 'GOFF')}.h5")


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


def test_trusted_asf_url_accepts_https_asf_hosts_only():
    assert download.trusted_asf_url("https://datapool.asf.alaska.edu/a.h5")
    assert download.trusted_asf_url("https://nisar.asf.earthdatacloud.nasa.gov/a.h5")
    assert not download.trusted_asf_url("http://datapool.asf.alaska.edu/a.h5")
    assert not download.trusted_asf_url("https://example.invalid/a.h5")


def test_safe_remote_error_redacts_urls_and_secret_like_fields():
    exc = RuntimeError("failed https://host.invalid/file.h5 token=secret-value")
    text = download.safe_remote_error(exc)
    assert "[URL]" in text
    assert "secret-value" not in text
    assert "[REDACTED]" in text


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

def test_probe_url_retries_transient_http_status(monkeypatch):
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)
    session = FakeSession(
        head_response=[
            FakeResponse(503, reason="Service Unavailable"),
            FakeResponse(200, {"Content-Length": "123456"}),
        ]
    )
    size = download.probe_url_content_length(
        session,
        "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/example.h5",
    )
    assert size == 123456
    assert len(session.head_calls) == 2


def test_authenticated_session_retries_connection_error(monkeypatch):
    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)
    session = FakeSession(head_response=FakeResponse(200, {"Content-Length": "123"}))

    class FlakyAcquisition:
        def __init__(self):
            self.calls = 0

        def build_session(self):
            self.calls += 1
            if self.calls == 1:
                raise download.requests.exceptions.ConnectionError("temporary endpoint outage")
            return session

    acquisition = FlakyAcquisition()
    assert download.build_authenticated_session_with_retry(acquisition) is session
    assert acquisition.calls == 2


def test_urgent_response_product_uses_exact_asf_catalog_url(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)
    urgent = WANTED.replace("_PR_GUNW_", "_UR_GUNW_")
    url = f"https://nisar.asf.earthdatacloud.nasa.gov/UR/{urgent}/{urgent}.h5"

    class FakeCatalogProduct:
        properties = {"fileName": f"{urgent}.h5", "bytes": 123}

        def get_urls(self):
            return [url]

    calls = []
    monkeypatch.setitem(
        download.sys.modules,
        "asf_search",
        SimpleNamespace(search=lambda **kwargs: (calls.append(kwargs) or [FakeCatalogProduct()])),
    )
    session = FakeSession(head_response=FakeResponse(200, {"Content-Length": "123"}))
    acquisition = FakeSourceAcquisition(session)

    record, returned_session, size = download.probe_known_product(
        acquisition, urgent, "GUNW", "BETA"
    )

    assert calls == [{"dataset": "NISAR", "granule_list": [urgent]}]
    assert record["downloadUrl"] == url
    assert record["_sarguardian_discovery_backend"] == "asf_catalog_exact_granule"
    assert returned_session is session
    assert size == 123


def test_missing_urgent_response_catalog_entry_is_actionable(monkeypatch):
    from types import SimpleNamespace

    urgent = WANTED.replace("_PR_GUNW_", "_UR_GUNW_")
    monkeypatch.setitem(
        download.sys.modules,
        "asf_search",
        SimpleNamespace(search=lambda **kwargs: []),
    )
    with pytest.raises(RuntimeError, match="UR_GRANULE_NOT_FOUND_IN_ASF_CATALOG"):
        download._catalog_record_for_exact_granule(urgent, "GUNW", "BETA")


def test_non_urgent_direct_404_falls_back_to_exact_catalog_url(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(download.time, "sleep", lambda _seconds: None)
    catalog_url = f"https://datapool.asf.alaska.edu/{WANTED}.h5"

    class FakeCatalogProduct:
        properties = {"fileName": f"{WANTED}.h5"}

        def get_urls(self):
            return [catalog_url]

    monkeypatch.setitem(
        download.sys.modules,
        "asf_search",
        SimpleNamespace(search=lambda **kwargs: [FakeCatalogProduct()]),
    )
    session = FakeSession(
        head_response=[
            FakeResponse(404, reason="Not Found"),
            FakeResponse(200, {"Content-Length": "987"}),
        ]
    )
    record, returned_session, size = download.probe_known_product(
        FakeSourceAcquisition(session), WANTED, "GUNW", "PROVISIONAL"
    )

    assert record["downloadUrl"] == catalog_url
    assert record["_sarguardian_discovery_backend"] == "asf_catalog_exact_granule"
    assert returned_session is session
    assert size == 987
    assert len(session.head_calls) == 2

