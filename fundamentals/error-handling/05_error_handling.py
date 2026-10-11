"""05_error_handling.py — Topic redirect to the canonical error-handling recipe.

This entry exists for discovery under the "error-handling" topic, but the canonical,
golden-verified recipe lives at ``fundamentals/pycubrid/05_error_handling.py``. It is
intentionally a thin redirect (no ``expected/`` golden) so the same recipe is not
double-counted as distinct ``make verify`` coverage.

Run the canonical recipe instead, from the repository root::

    python fundamentals/pycubrid/05_error_handling.py

The canonical recipe demonstrates the PEP 249 exception hierarchy, catching specific database errors, handling connection failures and graceful recovery.
"""

from __future__ import annotations

CANONICAL_RECIPE = "fundamentals/pycubrid/05_error_handling.py"

if __name__ == "__main__":
    print(
        "This is a topic redirect. The canonical, verified recipe lives at "
        f"{CANONICAL_RECIPE}. Run: python {CANONICAL_RECIPE} from the repository root."
    )
