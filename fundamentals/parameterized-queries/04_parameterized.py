"""04_parameterized.py — Topic redirect to the canonical parameterized-queries recipe.

This entry exists for discovery under the "parameterized-queries" topic, but the
canonical, golden-verified recipe lives at ``fundamentals/pycubrid/04_prepared.py``.
It is intentionally a thin redirect (no ``expected/`` golden) so the same recipe is
not double-counted as distinct ``make verify`` coverage.

Run the canonical recipe instead::

    python ../pycubrid/04_prepared.py

The canonical recipe demonstrates parameterized queries (qmark ``?`` style), SQL
injection safety, and batch operations with ``executemany``. See also this folder's
``README.md`` for pycubrid's client-side (not server-side prepare) binding model.
"""

from __future__ import annotations

CANONICAL_RECIPE = "fundamentals/pycubrid/04_prepared.py"

if __name__ == "__main__":
    print(
        "This is a topic redirect. The canonical, verified recipe lives at "
        f"{CANONICAL_RECIPE}. Run: python ../pycubrid/04_prepared.py"
    )
