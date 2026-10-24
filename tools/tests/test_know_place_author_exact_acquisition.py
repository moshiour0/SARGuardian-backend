"""Offline contract tests for author-exact NASA CMR acquisition."""
from __future__ import annotations

import json

import pytest

import tools.know_place.author_exact_acquisition as acquisition
from tools.know_place.author_catalog import (
    CMR_COLLECTION_CONCEPT_ID,
    EXPECTED_COLLECTION,
    load_author_granules,
)


def _cmr_row(target: dict) -> dict:
    name = target["granule_name"]
    url = (
        "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/"
        f"{EXPECTED_COLLECTION}/{name}/{name}.h5"
    )
    return {
        "granule_name": name,
        "interval": target["interval"],
        "processing": "PR",
        "track": "098",
        "direction": "A",
        "release_id": "P05023",
        "collection": EXPECTED_COLLECTION,
        "catalog_maturity": "PROVISIONAL",
        "catalog_url_host": "cmr.earthdata.nasa.gov",
        "catalog_identity_status": "EXACT_CMR_GRANULE_CONFIRMED",
        "catalog_identity_discovery_method": "NASA_CMR_COLLECTION_SCOPED_EXACT_QUERY",
        "cmr_collection_concept_id": CMR_COLLECTION_CONCEPT_ID,
        "cmr_metadata": {
            "id": "G1234567890-ASF",
            "producer_granule_id": name,
            "granule_ur": name,
            "title": name,
            "collection_concept_id": CMR_COLLECTION_CONCEPT_ID,
            "time_start": "2026-06-20T23:39:21.000Z",
            "time_end": "2026-07-02T23:39:55.999Z",
            "links": [{
                "rel": "http://esipfed.org/ns/fedsearch/1.1/data#",
                "title": name + ".h5",
                "type": "application/x-hdf5",
                "href": url,
                "inherited": False,
            }],
        },
        "source_sha256": None,
        "source_sha256_status": "NOT_DOWNLOADED",
        "cmr_source_payload_downloaded": False,
    }


def test_consent_marker_requires_exact_literal() -> None:
    acquisition.require_consent_marker("[run-know-place]")
    for value in (None, "", "run-know-place", "[run-know-place] ", "prefix [run-know-place]"):
        with pytest.raises(
            acquisition.AuthorExactAcquisitionError,
            match="EXPLICIT_RAW_DOWNLOAD_CONSENT_MARKER_REQUIRED",
        ):
            acquisition.require_consent_marker(value)


def test_exact_hdf5_data_url_comes_only_from_exact_author_cmr_data_link() -> None:
    target = load_author_granules()[0]
    row = _cmr_row(target)
    chosen = acquisition.select_exact_hdf5_data_url(row, target["granule_name"])
    assert chosen.endswith("/" + target["granule_name"] + ".h5")
    assert "NISAR_L2_GOFF_PROVISIONAL_V1" in chosen
    assert row["source_sha256"] is None


@pytest.mark.parametrize("edit", [
    lambda row: row.update(release_id="X05026"),
    lambda row: row.update(cmr_collection_concept_id="C_WRONG"),
    lambda row: row["cmr_metadata"]["links"][0].update(
        href="https://example.invalid/NISAR/NISAR_L2_GOFF_PROVISIONAL_V1/"
        + row["granule_name"] + "/" + row["granule_name"] + ".h5"
    ),
    lambda row: row["cmr_metadata"]["links"][0].update(
        href="https://nisar.asf.earthdatacloud.nasa.gov/OTHER_COLLECTION/"
        + row["granule_name"] + "/" + row["granule_name"] + ".h5"
    ),
    lambda row: row["cmr_metadata"]["links"][0].update(title="Browse image"),
])
def test_exact_data_url_rejects_wrong_release_collection_host_path_or_link(edit) -> None:
    target = load_author_granules()[0]
    row = _cmr_row(target)
    edit(row)
    with pytest.raises(acquisition.AuthorExactAcquisitionError):
        acquisition.select_exact_hdf5_data_url(row, target["granule_name"])


def test_discovery_requires_five_exact_p05023_cmr_rows_without_downloading(monkeypatch) -> None:
    targets = load_author_granules()
    calls = []

    def fake_query(target):
        calls.append(target["granule_name"])
        return _cmr_row(target), {
            "status": "EXACT_AUTHOR_ID_CONFIRMED",
            "exact_author_id_found": True,
            "source_downloads": 0,
        }

    monkeypatch.setattr(acquisition, "query_cmr_exact_author_product", fake_query)
    rows, manifest = acquisition.discover_exact_author_sources()
    assert calls == [row["granule_name"] for row in targets]
    assert len(rows) == 5
    assert manifest["status"] == "PASS"
    assert manifest["exact_cmr_confirmed_count"] == 5
    assert manifest["source_downloads"] == 0
    assert all(row["release_id"] == "P05023" for row in rows)
    assert all(row["source_sha256"] is None for row in rows)
    assert all(row["download_status"] == "NOT_DOWNLOADED" for row in rows)


def test_discovery_fails_closed_when_one_author_cmr_identity_is_missing(monkeypatch) -> None:
    targets = load_author_granules()

    def fake_query(target):
        if target["granule_name"] == targets[0]["granule_name"]:
            return None, {"status": "NOT_FOUND", "source_downloads": 0}
        return _cmr_row(target), {
            "status": "EXACT_AUTHOR_ID_CONFIRMED",
            "source_downloads": 0,
        }

    monkeypatch.setattr(acquisition, "query_cmr_exact_author_product", fake_query)
    rows, manifest = acquisition.discover_exact_author_sources()
    assert manifest["status"] == "BLOCKED"
    assert manifest["exact_cmr_confirmed_count"] == 4
    assert manifest["blocking_count"] == 1
    assert rows[0]["granule_name"] != targets[0]["granule_name"]
    assert manifest["source_downloads"] == 0


def test_authenticated_preflight_probes_five_urls_without_downloads(tmp_path, monkeypatch) -> None:
    targets = load_author_granules()
    rows = [_cmr_row(target) for target in targets]
    checked = []

    class FakeDownloader:
        @staticmethod
        def probe_url_content_length(session, url):
            checked.append(url)
            return 1_000_000

    monkeypatch.setattr(
        acquisition,
        "_load_downloader",
        lambda science_root: (FakeDownloader, "a" * 64, object()),
    )
    out = tmp_path / "preflight.json"
    result = acquisition.authenticated_preflight(
        rows, science_root=tmp_path, output_path=out,
    )
    assert len(checked) == 5
    assert result["status"] == "PASS"
    assert result["passed_count"] == 5
    assert result["raw_payload_downloads"] == 0
    assert all(not item["source_payload_downloaded"] for item in result["products"])
    assert json.loads(out.read_text(encoding="utf-8"))["estimated_total_source_bytes"] == 5_000_000


def test_analysis_success_requires_zero_exit_and_complete_metrics() -> None:
    complete = {"status": "SCIENTIFIC_METRICS_COMPUTED", "structural_status": "PASS"}
    assert acquisition.analysis_result_is_complete(0, complete)
    assert not acquisition.analysis_result_is_complete(2, complete)
    assert not acquisition.analysis_result_is_complete(
        0, {"status": "PARTIAL_INSUFFICIENT_DATA", "structural_status": "PASS"}
    )
    assert not acquisition.analysis_result_is_complete(
        0, {"status": "SCIENTIFIC_METRICS_COMPUTED", "structural_status": "FAIL"}
    )


def test_analysis_config_records_source_manifest_hash(tmp_path) -> None:
    targets = load_author_granules()
    run_root = tmp_path / "source-run"
    raw_dir = run_root / "raw"
    raw_dir.mkdir(parents=True)
    manifest = {
        "source_downloads": 5,
        "products": [{
            "granule_name": row["granule_name"],
            "source_filename": row["granule_name"] + ".h5",
            "release_id": "P05023",
            "download_status": "PASS",
            "source_bytes": 1234,
            "source_sha256": ("a" if index % 2 == 0 else "b") * 64,
        } for index, row in enumerate(targets)],
    }
    config = acquisition._build_analysis_config(
        manifest, raw_dir, run_root, source_manifest_sha256="c" * 64,
    )
    saved = json.loads((run_root / "know-place-inputs.json").read_text(encoding="utf-8"))
    provenance = json.loads((run_root / "run-config-provenance.json").read_text(encoding="utf-8"))
    assert config["schema_version"] == "know-place-analysis-inputs/1.0"
    assert len(config["products"]) == 5
    assert all(product["path"].startswith("raw/") for product in config["products"])
    assert provenance["source_manifest_sha256"] == "c" * 64
    assert provenance["config_sha256"] == acquisition.sha256_file(run_root / "know-place-inputs.json")
    assert saved == config


def test_download_operation_requires_consent_before_any_catalog_query(tmp_path, monkeypatch, capsys) -> None:
    called = False

    def forbidden_query():
        nonlocal called
        called = True
        raise AssertionError("catalog must not be queried without consent")

    monkeypatch.setattr(acquisition, "discover_exact_author_sources", forbidden_query)
    rc = acquisition.main([
        "--operation", "download-and-analyze",
        "--out-root", str(tmp_path / "run"),
        "--science-root", str(tmp_path / "science"),
    ])
    assert rc == 2
    assert not called
    assert "EXPLICIT_RAW_DOWNLOAD_CONSENT_MARKER_REQUIRED" in capsys.readouterr().out
