"""02_crud.py — Topic redirect to the canonical crud recipe.

This entry exists for discovery under the "crud" topic, but the canonical,
golden-verified recipe lives at ``fundamentals/pycubrid/02_crud.py``. It is
intentionally a thin redirect (no ``expected/`` golden) so the same recipe is not
double-counted as distinct ``make verify`` coverage.

Run the canonical recipe instead, from the repository root::

    python fundamentals/pycubrid/02_crud.py

The canonical recipe demonstrates CREATE TABLE, INSERT, SELECT with filtering, UPDATE, DELETE and DROP TABLE cleanup.
"""

from __future__ import annotations

CANONICAL_RECIPE = "fundamentals/pycubrid/02_crud.py"

if __name__ == "__main__":
    print(
        "This is a topic redirect. The canonical, verified recipe lives at "
        f"{CANONICAL_RECIPE}. Run: python {CANONICAL_RECIPE} from the repository root."
    )
