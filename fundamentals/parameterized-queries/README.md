# Parameterized Queries

> ⚠️ **Not server-side prepare.** pycubrid implements parameterized queries via
> **client-side escape + interpolation**, not via server-side `PREPARE`/`EXECUTE`.
> This differs from JDBC `PreparedStatement`. See
> [pycubrid PARAMETER_BINDING.md](https://github.com/cubrid-lab/pycubrid/blob/main/docs/PARAMETER_BINDING.md)
> for the full 1.x binding contract.

This directory demonstrates safe parameterized query patterns using pycubrid's
qmark (`?`) placeholder style.

## Recipes

| Recipe | Description |
|--------|-------------|
| [`04_prepared.py`](04_prepared.py) | Parameterized queries, batch operations with `executemany()` |

## Why parameterized queries?

Parameterized queries (passing values via `?` placeholders and a separate
`parameters` argument) are the correct way to send user-supplied values to the
database. **Never** assemble SQL with f-strings or `%` formatting — that path
leads to SQL injection.

## pycubrid binding model

When you call:

```python
cur.execute("SELECT * FROM users WHERE id = ? AND name = ?", [42, "Alice"])
```

pycubrid:

1. Splits the SQL on unquoted `?` placeholders.
2. Formats each Python value as a SQL literal via `_format_parameter()`
   (strings escaped via single-quote doubling, `None` → `NULL`, etc.).
3. Concatenates the segments and literals into one SQL string.
4. Sends the fully-rendered SQL to CUBRID via `PrepareAndExecutePacket`.

The CAS function code is named `PREPARE_AND_EXECUTE`, but the protocol expects
a complete SQL string — there is no separate typed parameter payload. See
[pycubrid PARAMETER_BINDING.md](https://github.com/cubrid-lab/pycubrid/blob/main/docs/PARAMETER_BINDING.md)
for the full per-type mapping and explicit non-guarantees.
