from __future__ import annotations

import time
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import NullPool


def main() -> None:
    """Benchmark connection pooling strategies using SQLAlchemy."""
    # Connection URL for CUBRID
    cubrid_url = "cubrid+pycubrid://dba:@localhost:33000/testdb"
    num_queries = 50

    # Count the real DBAPI connections each strategy opens: SQLAlchemy fires the
    # "connect" event once per new connection, never for one reused from a pool.
    opened = {"no_pool": 0, "pooled": 0}

    def count_connections(strategy: str):
        def on_connect(dbapi_connection, connection_record) -> None:
            opened[strategy] += 1

        return on_connect

    # Strategy 1: No pooling (new engine per query)
    print("Starting connection pool benchmark...")
    start = time.time()
    for _ in range(num_queries):
        engine = create_engine(cubrid_url, poolclass=NullPool)
        event.listen(engine, "connect", count_connections("no_pool"))
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    no_pool_time = time.time() - start
    no_pool_avg = no_pool_time / num_queries

    # Strategy 2: Pooled engine (pool_size=5)
    engine = create_engine(cubrid_url, pool_size=5, max_overflow=0)
    event.listen(engine, "connect", count_connections("pooled"))
    start = time.time()
    for _ in range(num_queries):
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    pooled_time = time.time() - start
    pooled_avg = pooled_time / num_queries
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
    print(
        f"Connections opened:              NullPool {opened['no_pool']}, "
        f"pooled {opened['pooled']} ({num_queries} queries each)"
    )
    print()


if __name__ == "__main__":
    main()
