# Performance Optimization Patterns

Practical patterns to maximize performance with CUBRID + Python.

> 📊 All numbers are based on [cubrid-benchmark](https://github.com/cubrid-lab/cubrid-benchmark) experiment data.
> Environment: Intel i5-4200M, CUBRID 11.2, Python 3.12, pycubrid 0.5.0+16a8634

## Benchmark Evidence

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

### Row Count Scaling (pycubrid, optimized)

| Rows | Execute (ms) | Fetch (ms) | Total (ms) | Fetch % |
|------|-------------|------------|------------|---------|
| 100 | 1.76 | 0.03 | 1.78 | 1.4% |
| 500 | 3.44 | 2.18 | 5.63 | 38.8% |
| 1,000 | 4.32 | 6.46 | 10.78 | 59.9% |
| 5,000 | 9.85 | 39.09 | 48.94 | 79.9% |
| 10,000 | 16.72 | 81.33 | 98.05 | 83.0% |

**Key insight**: Beyond ~500 rows, Python-side parsing dominates total query time.

## Sections

| Section | Description |
|---------|-------------|
| [fetch-optimization/](./fetch-optimization/) | Optimize fetch patterns for large result sets |
| [bulk-insert/](./bulk-insert/) | Batch strategies for bulk INSERT operations |
| [connection-pooling/](./connection-pooling/) | Connection pool configuration and reuse |

## Key Takeaways

1. **≤ 500 rows**: Network + server time dominates — client-side optimization has minimal effect
2. **≥ 1,000 rows**: Fetch parsing is 60%+ of total time — use `fetchall()`, SELECT only needed columns
3. **Connections**: Creation cost is 1.66ms — pooling is essential (creating per-request kills throughput)
4. **Transactions**: COMMIT is the most expensive operation at ~47ms — batch your COMMITs

---

*Data source: [cubrid-benchmark/experiments/driver-comparison](https://github.com/cubrid-lab/cubrid-benchmark/tree/main/experiments/driver-comparison)*
