# One-time safety cancellation trigger

Created on 2026-10-26 for the isolated Know Place Analysis branch.

The automatic push-triggered legacy replay run 40231488633 uses the historical manifest in `tools/know_place/catalog.py`, whose first interval is `X05026`. That is not the exact author-published `P05023` source the user authorized. The matching one-time cancellation workflow must verify the target run ID, branch, name, and triggering commit SHA before requesting cancellation.

This marker is operational safety evidence only; it is not scientific output and does not authorize any source substitution.
