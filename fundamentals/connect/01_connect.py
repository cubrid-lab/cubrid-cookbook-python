"""01_connect.py — Topic redirect to the canonical connect recipe.

This entry exists for discovery under the "connect" topic, but the canonical,
golden-verified recipe lives at ``fundamentals/pycubrid/01_connect.py``. It is
intentionally a thin redirect (no ``expected/`` golden) so the same recipe is not
double-counted as distinct ``make verify`` coverage.

Run the canonical recipe instead, from the repository root::

    python fundamentals/pycubrid/01_connect.py

The canonical recipe demonstrates connecting to CUBRID, running a simple query, reading ``cursor.description`` and using the connection as a context manager.
"""

from __future__ import annotations

CANONICAL_RECIPE = "fundamentals/pycubrid/01_connect.py"

if __name__ == "__main__":
    print(
        "This is a topic redirect. The canonical, verified recipe lives at "
        f"{CANONICAL_RECIPE}. Run: python {CANONICAL_RECIPE} from the repository root."
    )
