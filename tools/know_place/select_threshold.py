"""CLI: select and checksum a score threshold using validation cases only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .event_validation import EventValidationError, select_validation_threshold


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select a frozen event score threshold on validation cases; test labels are rejected."
    )
    parser.add_argument("--registry", required=True, type=Path, help="Validation-only registry JSON; development/test cases are rejected")
    parser.add_argument("--validation-scores", required=True, type=Path)
    parser.add_argument("--model-policy-name", required=True)
    parser.add_argument("--score-name", required=True)
    parser.add_argument("--objective", choices=["max_youden_j", "max_f1", "max_recall_at_min_specificity"], default="max_youden_j")
    parser.add_argument("--decision-rule", choices=[">=", ">"], default=">=")
    parser.add_argument("--minimum-specificity", type=float, default=None)
    parser.add_argument("--out", required=True, type=Path, help="Full threshold-selection report JSON")
    parser.add_argument("--threshold-policy-out", required=True, type=Path, help="Frozen, checksum-addressed threshold policy JSON")
    args = parser.parse_args(argv)

    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        scores = json.loads(args.validation_scores.read_text(encoding="utf-8"))
        result = select_validation_threshold(
            registry,
            scores,
            model_policy_name=args.model_policy_name,
            score_name=args.score_name,
            objective=args.objective,
            decision_rule=args.decision_rule,
            minimum_specificity=args.minimum_specificity,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.threshold_policy_out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        args.threshold_policy_out.write_text(
            json.dumps(result["threshold_policy"], indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, json.JSONDecodeError) as exc:
        print("THRESHOLD_SELECTION_STATUS=FAIL")
        print(f"ERROR={type(exc).__name__}:INPUT_OR_OUTPUT_IO_FAILED")
        return 2
    except EventValidationError as exc:
        print("THRESHOLD_SELECTION_STATUS=FAIL")
        print(f"ERROR={str(exc).split(':', 1)[0]}")
        return 2

    print(f"THRESHOLD_SELECTION_STATUS={result['status']}")
    print(f"VALIDATION_REGISTRY_SHA256={result['validation_registry_sha256']}")
    print(f"VALIDATION_SCORES_SHA256={result['validation_scores_sha256']}")
    print(f"THRESHOLD={result['threshold_policy']['threshold']:.17g}")
    print(f"POLICY_SHA256={result['threshold_policy']['policy_sha256']}")
    print(f"THRESHOLD_POLICY={args.threshold_policy_out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
