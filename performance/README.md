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
| fetch-optimization | `SELECT *` + `fetchall()`, 10K rows | 50 ms (50–56) |
| bulk-insert | per-row COMMIT, 500 rows | 17.98 s (14.54–19.64), 28 rows/s (25–34) |
| bulk-insert | COMMIT every 500 rows, 5,000 rows | 3.91 s (3.60–4.65), 1,279 rows/s (1,075–1,388) |
| bulk-insert | single COMMIT, 5,000 rows | 3.39 s (3.36–3.84), 1,477 rows/s (1,301–1,489) |
| connection-pooling | `NullPool`, 50 x `SELECT 1` | 293 ms total, 5.9 ms/query (5.6–5.9) |
| connection-pooling | pool_size=5, 50 x `SELECT 1` | 40 ms total, 0.8 ms/query (0.8–0.9) |
| connection-pooling | speedup | 7.2x (6.2–7.3) |

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

## Key Takeaways

1. **≤ 500 rows** (historical, pycubrid 0.5.0): Network + server time dominates — client-side optimization has minimal effect
2. **≥ 1,000 rows**: Fetch parsing was 60%+ of total time (historical, pycubrid 0.5.0 data) — SELECT only needed columns (2 vs 5 columns: 28 vs 52 ms for 10K rows on 1.10.0)
3. **Connections**: a query on a fresh connection took ~5.9 ms vs ~0.8 ms pooled (pycubrid 1.10.0, 2026-10-09) — pooling is essential
4. **Transactions**: INSERT + COMMIT per row ran at ~28 rows/s vs ~1,279 rows/s with a COMMIT every 500 rows (pycubrid 1.10.0, 2026-10-09) — batch your COMMITs

---

*Data source: [cubrid-benchmark/experiments/driver-comparison](https://github.com/cubrid-lab/cubrid-benchmark/tree/main/experiments/driver-comparison)*
