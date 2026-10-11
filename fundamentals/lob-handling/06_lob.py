"""06_lob.py — Topic redirect to the canonical lob-handling recipe.

This entry exists for discovery under the "lob-handling" topic, but the canonical,
golden-verified recipe lives at ``fundamentals/pycubrid/06_lob.py``. It is
intentionally a thin redirect (no ``expected/`` golden) so the same recipe is not
double-counted as distinct ``make verify`` coverage.

Run the canonical recipe instead, from the repository root::

    python fundamentals/pycubrid/06_lob.py

The canonical recipe demonstrates CLOB and BLOB columns, inserting text and binary data and reading LOB data back through the Lob handle.
"""

from __future__ import annotations

CANONICAL_RECIPE = "fundamentals/pycubrid/06_lob.py"

if __name__ == "__main__":
    print(
        "This is a topic redirect. The canonical, verified recipe lives at "
        f"{CANONICAL_RECIPE}. Run: python {CANONICAL_RECIPE} from the repository root."
    )
