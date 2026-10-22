# Performance Optimization Patterns

Practical patterns to maximize performance with CUBRID + Python.

> 📊 All numbers are based on [cubrid-benchmark](https://github.com/cubrid-lab/cubrid-benchmark) experiment data.
> The two tables under **Historical** were measured on an Intel i5-4200M, CUBRID 11.2, Python 3.12,
> pycubrid 0.5.0+16a8634 (undated) and have **not** been re-measured. Current figures are in
> [Measured on pycubrid 1.10.0](#measured-on-pycubrid-1100-2026-10-09).

## Measured on pycubrid 1.10.0 (2026-10-09)

Re-measured with the repo's own scripts (`*/benchmark.py`): median of 5 runs, range in parentheses.
Environment: Intel i5-9400F (6 cores), Python 3.12, pycubrid 1.10.0, sqlalchemy-cubrid 1.10.0,
SQLAlchemy 2.1.4, CUBRID 11.4.6 (`cubrid/cubrid:11.4` in Docker, same host, TCP to localhost).
Numbers are indicative for this host only; rerun the scripts on your own hardware.

| Script | Measurement | Median (min–max) |
|--------|-------------|------------------|
| fetch-optimization | `fetchone()` loop, 10K rows | 52 ms (50–225; first run cold) |
| fetch-optimization | `fetchall()`, 5 columns, 10K rows | 52 ms (51–55) |
| fetch-optimization | `fetchall()`, 2 columns, 10K rows | 28 ms (26–29) |
| fetch-optimization | `fetchmany(500)` loop, 10K rows (pycubrid 1.12.0, 2026-10-13)¹ | 49 ms (47–77) |
| bulk-insert | per-row COMMIT, 500 rows | 17.98 s (14.54–19.64), 28 rows/s (25–34) |
| bulk-insert | COMMIT every 500 rows, 5,000 rows | 3.91 s (3.60–4.65), 1,279 rows/s (1,075–1,388) |
| bulk-insert | single COMMIT, 5,000 rows | 3.39 s (3.36–3.84), 1,477 rows/s (1,301–1,489) |
| connection-pooling | `NullPool`, 50 x `SELECT 1` | 293 ms total, 5.9 ms/query (5.6–5.9) |
| connection-pooling | pool_size=5, 50 x `SELECT 1` | 40 ms total, 0.8 ms/query (0.8–0.9) |
| connection-pooling | speedup | 7.2x (6.2–7.3) |

¹ This row replaces `SELECT *` + `fetchall()` (50 ms), which ran the same query as the 5-column
`fetchall()` row because the test table has only those 5 columns. It was measured on the same host
with pycubrid 1.12.0; the other rows are the pycubrid 1.10.0 runs above.

Not re-measured (the scripts do not cover them; new benchmarks are out of scope): the "Before / After"
driver-optimization table and the row-count scaling table below are historical.

## Historical Benchmark Evidence (pycubrid 0.5.0+16a8634)

### Driver Optimization Results (Before → After)

| Operation | Before (ms) | After (ms) | Improvement |
|-----------|-------------|------------|-------------|
| SELECT 10K fetch | 96.05 | 77.77 | **−19.0%** |
| SELECT 10K total | 110.94 | 91.35 | **−17.7%** |
| SELECT by PK | 1.08 | 0.96 | **−11.4%** |
| Connect | 2.24 | 1.66 | **−26.2%** |
| INSERT execute | 7.81 | 7.10 | **−9.1%** |
| UPDATE execute | 4.52 | 3.89 | **−13.8%** |
| DELETE execute | 4.36 | 3.55 | **−18.8%** |

### Row Count Scaling (pycubrid 0.5.0+16a8634, optimized)

| Rows | Execute (ms) | Fetch (ms) | Total (ms) | Fetch % |
|------|-------------|------------|------------|---------|
| 100 | 1.76 | 0.03 | 1.78 | 1.4% |
| 500 | 3.44 | 2.18 | 5.63 | 38.8% |
| 1,000 | 4.32 | 6.46 | 10.78 | 59.9% |
| 5,000 | 9.85 | 39.09 | 48.94 | 79.9% |
| 10,000 | 16.72 | 81.33 | 98.05 | 83.0% |

**Key insight** (historical, 0.5.0): beyond ~500 rows, Python-side parsing dominated total query time.

## Sections

| Section | Description |
|---------|-------------|
| [fetch-optimization/](./fetch-optimization/) | Optimize fetch patterns for large result sets |
| [bulk-insert/](./bulk-insert/) | Batch strategies for bulk INSERT operations |
| [connection-pooling/](./connection-pooling/) | Connection pool configuration and reuse |

## Running the Benchmarks

Each section directory has a `benchmark.py` that connects to `localhost:33000`, database `testdb`, user `dba`
with an empty password (the repository's `docker-compose.yml` provides this). From the repository root:

```bash
CUBRID_VERSION=11.4 docker compose up -d --wait cubrid   # CUBRID 11.4 on localhost:33000, database testdb
pip install 'sqlalchemy-cubrid[pycubrid]'
python performance/fetch-optimization/benchmark.py
python performance/bulk-insert/benchmark.py
python performance/connection-pooling/benchmark.py
docker compose down                    # stop the database when finished
```

Expect about 15 seconds for `fetch-optimization`, about 45 seconds for `bulk-insert` and a few seconds for
`connection-pooling`. Absolute numbers depend on your hardware and CUBRID version.

## Testing the benchmarks

The benchmarks print timings, so they have no golden file. `make verify-performance` (also part of the full
`make verify`; with the database above running and `make deps` installed) checks them instead, together with the five
[Java → Python migration](../migration/java-to-python/) golden cases:

```bash
make verify-performance   # JUnit report and summary: .live-evidence/performance/
```

`tests/test_performance_benchmarks.py` runs each `benchmark.py` with a time limit and checks that it exits 0,
prints every comparison line with a finite, nonnegative time, ran its whole workload (10,000 fetched rows per
strategy; 500, 5,000 and 5,000 stored rows; 50 connections without a pool and 1 to 5 with one) and printed no
error. It also makes `fetch-optimization` and `bulk-insert` fail on purpose after they create their table and
checks that the table is dropped anyway, and that an unrelated table is unchanged after each run. It never
compares one strategy's time with another's, so a slow or noisy machine does not fail it. The report records
the CUBRID server, Python, pytest and driver versions. `make verify-performance` fails when the database is unreachable,
any test is skipped or a table is left behind; plain `pytest tests/test_performance_benchmarks.py` skips without a database.

The benchmarks and the migration examples use fixed table names (`cookbook_fetch_test`, `cookbook_bulk_test`,
`cookbook_jdbc_*`, `cookbook_sensors`). Do not run `make verify-performance` at the same time as another `make verify-performance`,
`make verify` or a manual benchmark run against the same database: they would drop each other's tables.

## Key Takeaways

1. **≤ 500 rows** (historical, pycubrid 0.5.0): Network + server time dominates — client-side optimization has minimal effect
2. **≥ 1,000 rows**: Fetch parsing was 60%+ of total time (historical, pycubrid 0.5.0 data) — SELECT only needed columns (2 vs 5 columns: 28 vs 52 ms for 10K rows on 1.10.0)
3. **Connections**: a query on a fresh connection took ~5.9 ms vs ~0.8 ms pooled (pycubrid 1.10.0, 2026-10-09) — pooling is essential
4. **Transactions**: INSERT + COMMIT per row ran at ~28 rows/s vs ~1,279 rows/s with a COMMIT every 500 rows (pycubrid 1.10.0, 2026-10-09) — batch your COMMITs

---

*Data source: [cubrid-benchmark/experiments/driver-comparison](https://github.com/cubrid-lab/cubrid-benchmark/tree/main/experiments/driver-comparison)*
