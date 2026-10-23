from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.know_place.select_threshold import main as select_threshold_main
from tools.know_place.event_validation import (
    EventValidationError,
    REGISTRY_SCHEMA,
    THRESHOLD_SCHEMA,
    evaluate_heldout_events,
    select_validation_threshold,
    main,
    seal_threshold_policy,
    validate_event_registry,
)

WKT = "POLYGON ((85.52 28.28, 85.54 28.28, 85.54 28.30, 85.52 28.30, 85.52 28.28))"


def case(case_id, site_id, split, label, *, event_time=None, with_product=True):
    return {
        "case_id": case_id,
        "site_id": site_id,
        "split": split,
        "event_label": label,
        "hazard_type": "landslide" if label else "non_event",
        "aoi_wkt": WKT,
        "independent_label_evidence": {
            "source_url_or_doi": f"https://example.org/independent-inventory/{case_id}",
            "label_method": "independent published event inventory and manual review",
            "reviewed_independently": True,
        },
        "observation_window_utc": {
            "start": "2026-06-20T00:00:00Z",
            "end": "2026-07-20T00:00:00Z",
        },
        "event_time_utc": event_time if label else None,
        "monitoring_exposure_aoi_months": 1.0 if with_product else 0.0,
        "source_products": [{
            "granule_name": f"fixture-{case_id}.h5",
            "sha256": hashlib.sha256(f"synthetic-source-for-{case_id}".encode("ascii")).hexdigest(),
        }] if with_product else [],
    }


def registry():
    cases = [
        case("DEV-E1", "DEV-SITE", "development", True, event_time="2026-06-25T00:00:00Z"),
        case("VAL-E1", "VAL-SITE", "validation", True, event_time="2026-07-15T00:00:00Z"),
        case("VAL-N1", "VAL-CTRL", "validation", False),
        case("T1", "S1", "test", True, event_time="2026-08-01T00:00:00Z"),
        case("T2", "S2", "test", True, event_time="2026-08-02T00:00:00Z"),
        case("T3", "S3", "test", True, event_time="2026-08-03T00:00:00Z", with_product=False),
        case("T4", "S4", "test", False),
        case("T5", "S5", "test", False),
        case("T6", "S6", "test", False, with_product=False),
    ]
    return {
        "schema_version": REGISTRY_SCHEMA,
        "label_policy": "Labels reviewed independently from all detector outputs; one AOI-window is one case.",
        "cases": cases,
    }


def threshold_policy(reg):
    validated = validate_event_registry(reg)
    return seal_threshold_policy({
        "schema_version": THRESHOLD_SCHEMA,
        "model_policy_name": "synthetic_known_answer_v1",
        "score_name": "mocked_validation_score",
        "threshold": 0.7,
        "decision_rule": ">=",
        "threshold_selection_split": "validation",
        "frozen_before_test": True,
        "registry_sha256": validated["registry_sha256"],
        "selection_evidence": "Selected only on validation cases; this synthetic fixture does not validate a real detector.",
    })


def prediction(case_id, state, score=None, alarm=None):
    item = {"case_id": case_id, "state": state}
    if score is not None:
        item["score"] = score
    if alarm is not None:
        item["first_alarm_time_utc"] = alarm
    return item


def prediction_payload():
    return {
        "schema_version": "know-place-event-predictions/1.0",
        "cases": [
            prediction("T1", "ALERT", 0.9, "2026-07-30T00:00:00Z"),
            prediction("T2", "NO_ALERT", 0.4),
            prediction("T3", "NO_RESULT"),
            prediction("T4", "ALERT", 0.8, "2026-07-25T00:00:00Z"),
            prediction("T5", "NO_ALERT", 0.1),
            prediction("T6", "NO_RESULT"),
        ],
    }


def test_heldout_evaluation_has_known_answer_and_counts_no_result_conservatively():
    reg = registry()
    result = evaluate_heldout_events(
        reg, prediction_payload(), threshold_policy(reg),
        bootstrap_replicates=100, bootstrap_seed=12, minimum_independent_sites_for_ci=4,
    )

    metrics = result["event_level_metrics_on_evaluable_cases"]
    assert result["status"] == "EVALUATED_EXPLORATORY_HELDOUT_TEST"
    assert result["test_only"] is True
    assert result["total_heldout_cases"] == 6
    assert result["independent_heldout_sites"] == 6
    assert result["availability"] == {
        "evaluable_cases": 4,
        "no_result_cases": 2,
        "coverage_fraction": pytest.approx(4 / 6),
        "no_result_policy": "not counted as a negative observation; all labelled events without an alert reduce conservative_recall_all_events",
    }
    assert {name: metrics[name] for name in ("tp", "fp", "tn", "fn")} == {
        "tp": 1, "fp": 1, "tn": 1, "fn": 1,
    }
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)
    assert metrics["specificity"] == pytest.approx(0.5)
    assert metrics["f1"] == pytest.approx(0.5)
    assert result["conservative_recall_all_labelled_events"] == pytest.approx(1 / 3)
    assert result["false_alarms_per_aoi_month"] == pytest.approx(1 / 2)
    assert result["lead_time_hours_before_event"]["median"] == pytest.approx(48.0)
    assert result["uncertainty"]["status"] == "COMPUTED_SITE_CLUSTER_BOOTSTRAP"
    assert result["uncertainty"]["independent_sites"] == 4


def test_threshold_must_be_frozen_and_selected_on_validation_split():
    reg = registry()
    policy = threshold_policy(reg)
    policy["threshold_selection_split"] = "test"
    policy.pop("policy_sha256")
    policy = seal_threshold_policy(policy)
    with pytest.raises(EventValidationError, match="THRESHOLD_MUST_BE_SELECTED_ON_VALIDATION_SPLIT"):
        evaluate_heldout_events(reg, prediction_payload(), policy, bootstrap_replicates=100)

    policy = threshold_policy(reg)
    policy["frozen_before_test"] = False
    policy.pop("policy_sha256")
    policy = seal_threshold_policy(policy)
    with pytest.raises(EventValidationError, match="THRESHOLD_POLICY_NOT_FROZEN_BEFORE_TEST"):
        evaluate_heldout_events(reg, prediction_payload(), policy, bootstrap_replicates=100)


def test_threshold_policy_and_registry_hashes_are_verified():
    reg = registry()
    policy = threshold_policy(reg)
    policy["threshold"] = 0.1
    with pytest.raises(EventValidationError, match="THRESHOLD_POLICY_CHECKSUM_MISMATCH"):
        evaluate_heldout_events(reg, prediction_payload(), policy, bootstrap_replicates=100)

    wrong_reg = copy.deepcopy(reg)
    wrong_reg["cases"][0]["site_id"] = "edited-after-freeze"
    with pytest.raises(EventValidationError, match="THRESHOLD_POLICY_REGISTRY_CHECKSUM_MISMATCH"):
        evaluate_heldout_events(wrong_reg, prediction_payload(), threshold_policy(reg), bootstrap_replicates=100)


def test_no_result_with_score_and_prediction_outside_test_split_are_rejected():
    reg = registry()
    bad_predictions = prediction_payload()
    bad_predictions["cases"][2]["score"] = 0.0
    with pytest.raises(EventValidationError, match="NO_RESULT_MUST_NOT_HAVE_SCORE"):
        evaluate_heldout_events(reg, bad_predictions, threshold_policy(reg), bootstrap_replicates=100)

    bad_predictions = prediction_payload()
    bad_predictions["cases"].append(prediction("VAL-E1", "ALERT", 0.9))
    with pytest.raises(EventValidationError, match="PREDICTION_NOT_HELDOUT_TEST_CASE"):
        evaluate_heldout_events(reg, bad_predictions, threshold_policy(reg), bootstrap_replicates=100)


def test_incomplete_or_threshold_inconsistent_test_predictions_fail_closed():
    reg = registry()
    missing = prediction_payload()
    missing["cases"].pop()
    with pytest.raises(EventValidationError, match="HELDOUT_TEST_PREDICTIONS_INCOMPLETE"):
        evaluate_heldout_events(reg, missing, threshold_policy(reg), bootstrap_replicates=100)

    inconsistent = prediction_payload()
    inconsistent["cases"][0]["state"] = "NO_ALERT"
    with pytest.raises(EventValidationError, match="PREDICTION_THRESHOLD_RULE_MISMATCH"):
        evaluate_heldout_events(reg, inconsistent, threshold_policy(reg), bootstrap_replicates=100)


def test_registry_rejects_unreviewed_labels_geometry_conflicts_and_duplicate_ids():
    reg = registry()
    reg["cases"][0]["independent_label_evidence"]["reviewed_independently"] = False
    with pytest.raises(EventValidationError, match="LABEL_NOT_INDEPENDENTLY_REVIEWED"):
        validate_event_registry(reg)

    reg = registry()
    reg["cases"][0]["aoi_geometry_sha256"] = "0" * 64
    with pytest.raises(EventValidationError, match="AOI_GEOMETRY_CHECKSUM_MISMATCH"):
        validate_event_registry(reg)

    reg = registry()
    reg["cases"].append(copy.deepcopy(reg["cases"][0]))
    with pytest.raises(EventValidationError, match="CASE_ID_DUPLICATE"):
        validate_event_registry(reg)


def test_cluster_confidence_intervals_are_withheld_for_too_few_sites():
    reg = registry()
    reg["cases"] = [
        case("VAL-E1", "VAL-SITE", "validation", True, event_time="2026-07-15T00:00:00Z"),
        case("T1", "ONLY-SITE", "test", True, event_time="2026-08-01T00:00:00Z"),
        case("T2", "ONLY-SITE", "test", False),
    ]
    # Build a policy against the compact test registry.
    policy = threshold_policy(reg)
    predictions = {
        "schema_version": "know-place-event-predictions/1.0",
        "cases": [prediction("T1", "ALERT", 0.9), prediction("T2", "NO_ALERT", 0.1)],
    }
    result = evaluate_heldout_events(
        reg, predictions, policy,
        bootstrap_replicates=100, minimum_independent_sites_for_ci=5,
    )
    assert result["uncertainty"]["status"] == "INSUFFICIENT_INDEPENDENT_SITES"
    assert result["uncertainty"]["intervals"]["recall"] is None


def test_event_evaluation_cli_writes_a_checksummed_result(tmp_path, capsys):
    reg = registry()
    policy = threshold_policy(reg)
    registry_path = tmp_path / "registry.json"
    predictions_path = tmp_path / "predictions.json"
    policy_path = tmp_path / "threshold-policy.json"
    output_path = tmp_path / "out" / "evaluation.json"
    registry_path.write_text(json.dumps(reg), encoding="utf-8")
    predictions_path.write_text(json.dumps(prediction_payload()), encoding="utf-8")
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    code = main([
        "--registry", str(registry_path),
        "--predictions", str(predictions_path),
        "--threshold-policy", str(policy_path),
        "--out", str(output_path),
        "--bootstrap-replicates", "100",
        "--minimum-independent-sites-for-ci", "4",
    ])

    assert code == 0
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["test_only"] is True
    assert result["registry_sha256"] == validate_event_registry(reg)["registry_sha256"]
    output = capsys.readouterr().out
    assert "EVENT_VALIDATION_STATUS=EVALUATED_EXPLORATORY_HELDOUT_TEST" in output


def validation_scores(*, positive_score=0.9, negative_score=0.2):
    return {
        "schema_version": "know-place-validation-scores/1.0",
        "cases": [
            {"case_id": "VAL-E1", "state": "SCORED", "score": positive_score},
            {"case_id": "VAL-N1", "state": "SCORED", "score": negative_score},
        ],
    }


def test_validation_threshold_selection_recovers_known_answer_without_touching_test_labels():
    reg = registry()
    selected = select_validation_threshold(
        reg, validation_scores(),
        model_policy_name="synthetic_detector_v1",
        score_name="mocked_alert_score",
        objective="max_youden_j",
    )

    policy = selected["threshold_policy"]
    assert selected["status"] == "THRESHOLD_SELECTED_ON_VALIDATION_SPLIT"
    assert selected["validation_case_count"] == 2
    assert selected["validation_scored_case_count"] == 2
    assert selected["selected_validation_metrics"]["tp"] == 1
    assert selected["selected_validation_metrics"]["fp"] == 0
    assert selected["selected_validation_metrics"]["tn"] == 1
    assert selected["selected_validation_metrics"]["fn"] == 0
    assert policy["threshold"] == pytest.approx(0.9)
    assert policy["threshold_selection_split"] == "validation"
    assert policy["frozen_before_test"] is True
    assert policy["registry_sha256"] == validate_event_registry(reg)["registry_sha256"]
    assert len(policy["validation_scores_sha256"]) == 64
    assert len(policy["policy_sha256"]) == 64
    # Held-out cases are not accepted in the threshold-selection inputs.
    leaked = validation_scores()
    leaked["cases"].append({"case_id": "T1", "state": "SCORED", "score": 1.0})
    with pytest.raises(EventValidationError, match="VALIDATION_SCORE_NOT_VALIDATION_CASE"):
        select_validation_threshold(
            reg, leaked, model_policy_name="synthetic_detector_v1",
            score_name="mocked_alert_score",
        )


def test_threshold_selection_supports_predeclared_minimum_specificity_objective():
    reg = registry()
    selected = select_validation_threshold(
        reg, validation_scores(positive_score=0.8, negative_score=0.7),
        model_policy_name="synthetic_detector_v1",
        score_name="mocked_alert_score",
        objective="max_recall_at_min_specificity",
        minimum_specificity=1.0,
    )
    assert selected["objective"] == "max_recall_at_min_specificity"
    assert selected["selected_validation_metrics"]["specificity"] == pytest.approx(1.0)
    assert selected["selected_validation_metrics"]["recall"] == pytest.approx(1.0)
    assert selected["threshold_policy"]["minimum_specificity"] == pytest.approx(1.0)


def test_threshold_selection_rejects_objectives_without_independent_validation_classes():
    reg = registry()
    scores = {
        "schema_version": "know-place-validation-scores/1.0",
        "cases": [
            {"case_id": "VAL-E1", "state": "NO_RESULT", "score": None},
            {"case_id": "VAL-N1", "state": "SCORED", "score": 0.2},
        ],
    }
    with pytest.raises(EventValidationError, match="VALIDATION_SCORES_HAVE_NO_POSITIVE_EVENTS"):
        select_validation_threshold(
            reg, scores, model_policy_name="synthetic_detector_v1",
            score_name="mocked_alert_score",
        )


def test_threshold_selection_cli_writes_report_and_frozen_policy(tmp_path, capsys):
    reg = registry()
    scores = validation_scores()
    registry_path = tmp_path / "registry.json"
    scores_path = tmp_path / "validation-scores.json"
    report_path = tmp_path / "out" / "threshold-selection.json"
    policy_path = tmp_path / "out" / "frozen-threshold-policy.json"
    registry_path.write_text(json.dumps(reg), encoding="utf-8")
    scores_path.write_text(json.dumps(scores), encoding="utf-8")

    code = select_threshold_main([
        "--registry", str(registry_path),
        "--validation-scores", str(scores_path),
        "--model-policy-name", "synthetic_detector_v1",
        "--score-name", "mocked_alert_score",
        "--objective", "max_youden_j",
        "--out", str(report_path),
        "--threshold-policy-out", str(policy_path),
    ])

    assert code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    assert policy == report["threshold_policy"]
    assert policy["threshold"] == pytest.approx(0.9)
    assert policy["threshold_selection_split"] == "validation"
    assert policy["frozen_before_test"] is True
    assert len(policy["policy_sha256"]) == 64
    assert "THRESHOLD_SELECTION_STATUS=THRESHOLD_SELECTED_ON_VALIDATION_SPLIT" in capsys.readouterr().out
