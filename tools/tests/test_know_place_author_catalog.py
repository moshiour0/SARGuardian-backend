"""Offline tests for the exact author-product catalog gate."""
from __future__ import annotations

import pytest

from tools.know_place.author_catalog import (
    load_author_granules,
    validate_author_catalog_product,
)
from tools.know_place.catalog import EXPECTED_COLLECTION, CatalogIdentityError


def _fake_product(target: dict, *, maturity: str = "PROVISIONAL") -> dict:
    name = target["granule_name"]
    return {
        "properties": {
            "granuleName": name,
            "url": f"https://asf.alaska.edu/{EXPECTED_COLLECTION}/{name}",
            "dataMaturity": maturity,
            "collectionName": EXPECTED_COLLECTION,
        }
    }


def test_author_manifest_contains_exactly_five_p05023_pairs_and_no_historical_x05026() -> None:
    products = load_author_granules()
    assert len(products) == 5
    assert [row["days"] for row in products] == [12, 12, 12, 24, 12]
    assert all("_P05023_" in row["granule_name"] for row in products)
    assert all("X05026" not in row["granule_name"] for row in products)
    assert products[0]["interval"] == "2026-06-20/2026-07-02"


def test_exact_author_product_identity_accepts_trusted_single_asf_result_without_source_hash() -> None:
    target = load_author_granules()[0]
    output = validate_author_catalog_product(target, [_fake_product(target)])
    assert output["granule_name"] == target["granule_name"]
    assert output["release_id"] == "P05023"
    assert output["catalog_identity_status"] == "EXACT_URL_CONFIRMED"
    assert output["source_sha256"] is None
    assert output["source_sha256_status"] == "NOT_DOWNLOADED"


def test_author_identity_gate_rejects_missing_or_ambiguous_product() -> None:
    target = load_author_granules()[0]
    with pytest.raises(CatalogIdentityError, match="ASF_AUTHOR_EXACT_GRANULE_NOT_FOUND"):
        validate_author_catalog_product(target, [])
    with pytest.raises(CatalogIdentityError, match="ASF_AUTHOR_EXACT_GRANULE_AMBIGUOUS"):
        validate_author_catalog_product(target, [_fake_product(target), _fake_product(target)])


def test_author_identity_gate_rejects_conflicting_maturity() -> None:
    target = load_author_granules()[0]
    with pytest.raises(CatalogIdentityError, match="ASF_AUTHOR_MATURITY_CONFLICT"):
        validate_author_catalog_product(target, [_fake_product(target, maturity="OPERATIONAL")])
