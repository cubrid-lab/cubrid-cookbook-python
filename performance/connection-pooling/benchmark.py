from __future__ import annotations

import time
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool, QueuePool


def main() -> None:
    """Benchmark connection pooling strategies using SQLAlchemy."""
    # Connection URL for CUBRID
    cubrid_url = "cubrid+pycubrid://dba:@localhost:33000/testdb"

    # Strategy 1: No pooling (new engine per query)
    print("Starting connection pool benchmark...")
    start = time.time()
    for _ in range(50):
        engine = create_engine(cubrid_url, poolclass=NullPool)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    no_pool_time = time.time() - start
    no_pool_avg = no_pool_time / 50

    # Strategy 2: Pooled engine (pool_size=5)
    engine = create_engine(cubrid_url, pool_size=5, max_overflow=0)
    start = time.time()
    for _ in range(50):
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    pooled_time = time.time() - start
    pooled_avg = pooled_time / 50
    engine.dispose()

    # Print results
    print("\n=== Connection Pooling Benchmark ===")
    print(
        f"No pooling (NullPool):           {no_pool_time:.3f}s total ({no_pool_avg:.4f}s per query)"
    )
    print(
        f"Pooled (pool_size=5):            {pooled_time:.3f}s total ({pooled_avg:.4f}s per query)"
    )
    print(f"Speedup factor:                  {no_pool_time / pooled_time:.1f}x")
    print()


if __name__ == "__main__":
    main()
