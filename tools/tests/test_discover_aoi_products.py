from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discover_aoi_products as discovery


class FakeResponse:
    status_code = 200
    def raise_for_status(self):
        return None
    def json(self):
        return {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"granuleName": "NISAR_L2_PR_GUNW_001_TEST_20250510T010101_20250510T010202_20250522T010101_20250522T010202_P05023.h5"}}
            ],
        }


class FakeSession:
    def __init__(self):
        self.calls = []
    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return FakeResponse()


def test_record_name_supports_flat_and_case_independent_fields():
    assert discovery.record_name({"granuleName": "NISAR_L2_PR_GUNW_001_TEST.h5"}) == "NISAR_L2_PR_GUNW_001_TEST"
    assert discovery.record_name({"FILE_NAME": "/tmp/EXAMPLE.H5"}) == "EXAMPLE"
    assert discovery.record_name({"properties": {"granuleName": "x"}}) == ""


def test_pair_secondary_date_is_third_timestamp():
    name = "NISAR_L2_PR_GUNW_001_TEST_20250510T010101_20250510T010202_20250522T010101_20250522T010202_P05023"
    dates = discovery.product_dates(name)
    assert dates is not None
    assert dates[0].isoformat() == "2025-05-10"
    assert dates[1].isoformat() == "2025-05-22"


def test_asf_query_uses_documented_nisar_searchable_fields_and_normalizes_geojson_properties():
    session = FakeSession()
    wkt = "POLYGON ((85 28, 86 28, 86 29, 85 29, 85 28))"
    rows = discovery.query_asf_polygon(wkt, "GUNW", discovery.parse_date("2025-12-31", "END_DATE"), session=session)
    assert len(rows) == 1
    assert rows[0]["granuleName"].startswith("NISAR_L2_PR_GUNW")
    assert len(session.calls) == 1
    url, params, timeout = session.calls[0]
    assert url == discovery.ASF_API
    assert params["intersectsWith"] == wkt
    assert "processingLevel" not in params
    assert params["shortName"] == "NISAR_L2_GUNW_V1"
    assert params["dataset"] == "NISAR"
    assert params["platform"] == "NISAR"
    assert params["output"] == "json"
    assert timeout == (30, 180)



def test_realistic_nisar_provisional_granule_name_is_accepted_and_pair_dates_parse():
    name = (
        "NISAR_L2_PR_GUNW_024_098_A_016_025_4000_SH_"
        "20260702T233920_20260702T233955_20260714T233920_"
        "20260714T233954_P05023_F_F_J_001"
    )
    match = discovery.PRODUCT_PATTERN.fullmatch(name)
    assert match is not None
    assert match.group(1) == "GUNW"
    dates = discovery.product_dates(name)
    assert dates is not None
    assert dates[0].isoformat() == "2026-07-02"
    assert dates[1].isoformat() == "2026-07-14"
