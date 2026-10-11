"""03_transactions.py — Topic redirect to the canonical transactions recipe.

This entry exists for discovery under the "transactions" topic, but the canonical,
golden-verified recipe lives at ``fundamentals/pycubrid/03_transactions.py``. It is
intentionally a thin redirect (no ``expected/`` golden) so the same recipe is not
double-counted as distinct ``make verify`` coverage.

Run the canonical recipe instead, from the repository root::

    python fundamentals/pycubrid/03_transactions.py

The canonical recipe demonstrates manual commit/rollback, autocommit mode, savepoints and transaction isolation.
"""

from __future__ import annotations

CANONICAL_RECIPE = "fundamentals/pycubrid/03_transactions.py"

if __name__ == "__main__":
    print(
        "This is a topic redirect. The canonical, verified recipe lives at "
        f"{CANONICAL_RECIPE}. Run: python {CANONICAL_RECIPE} from the repository root."
    )
