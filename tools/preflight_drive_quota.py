"""Fail before any product download if the selected run cannot fit in Drive."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from tools.drive_resumable_upload import Drive, DriveError
except ModuleNotFoundError:  # direct execution as python tools/preflight_drive_quota.py
    from drive_resumable_upload import Drive, DriveError


DEFAULT_SAFETY_FACTOR = 1.15
PER_PRODUCT_OVERHEAD_BYTES = 8 * 1024 * 1024
RUN_OVERHEAD_BYTES = 256 * 1024 * 1024
GIB = 1024 ** 3


def estimate_required_bytes(
    manifest: dict[str, Any],
    safety_factor: float = DEFAULT_SAFETY_FACTOR,
) -> int:
    """Conservatively estimate Drive storage for this run's new versioned assets.

    Source-size estimates are used as archive-size upper proxies, then enlarged
    by a configurable margin plus explicit allowances for each product's
    metadata/exports and the run-level bundle/report. The estimate does not
    replace per-upload Drive quota and checksum checks.
    """
    if not isinstance(safety_factor, (int, float)) or isinstance(safety_factor, bool):
        raise ValueError("safety_factor must be numeric")
    if not math.isfinite(float(safety_factor)) or not 1.0 <= float(safety_factor) <= 3.0:
        raise ValueError("safety_factor must be between 1.0 and 3.0")

    products = manifest.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("manifest must contain at least one selected product")

    source_estimate = 0
    for product in products:
        if not isinstance(product, dict):
            raise ValueError("every manifest product must be an object")
        value = product.get("expected_source_bytes")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("each product must have a positive expected_source_bytes integer")
        source_estimate += value

    return (
        math.ceil(source_estimate * float(safety_factor))
        + len(products) * PER_PRODUCT_OVERHEAD_BYTES
        + RUN_OVERHEAD_BYTES
    )


def preflight_capacity(
    manifest: dict[str, Any],
    drive: Any,
    safety_factor: float = DEFAULT_SAFETY_FACTOR,
) -> dict[str, int]:
    """Check available Drive quota without logging the user's total storage usage."""
    if manifest.get("aoi") != "source":
        raise ValueError("manifest AOI must be the pinned source AOI")
    estimate = estimate_required_bytes(manifest, safety_factor)
    limit, usage = drive.quota()
    remaining = int(limit) - int(usage)
    if remaining < 0 or estimate > remaining:
        # Expose required capacity only; do not publish exact account usage.
        required_gib = estimate / GIB
        raise DriveError(
            "DRIVE_QUOTA_INSUFFICIENT_FOR_SELECTED_RUN "
            f"required_gib={required_gib:.2f} available=below_required"
        )
    return {
        "selected_products": len(manifest["products"]),
        "estimated_required_bytes": estimate,
        "estimated_required_gib": estimate / GIB,
        "remaining_bytes": remaining,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--safety-factor",
        type=float,
        default=DEFAULT_SAFETY_FACTOR,
        help="margin multiplier on expected source bytes (default: 1.15)",
    )
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = preflight_capacity(manifest, Drive(), args.safety_factor)
    except (OSError, json.JSONDecodeError, ValueError, DriveError) as exc:
        code = str(exc) if isinstance(exc, DriveError) else f"INVALID_PREFLIGHT_INPUT:{type(exc).__name__}"
        print(f"ERROR={code}")
        return 2

    print(
        "DRIVE_QUOTA_PREFLIGHT=PASS "
        f"PRODUCTS={result['selected_products']} "
        f"RUN_PROFILE={manifest.get('run_profile', 'unknown')} "
        f"REQUIRED_GIB={result['estimated_required_gib']:.2f}"
    )
    # Do not print account limit/usage values into public GitHub Actions logs.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
