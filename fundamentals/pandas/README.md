# Pandas + CUBRID Recipes

Six standalone scripts that demonstrate pandas workflows with CUBRID through a SQLAlchemy engine.

## Connection

All scripts use:

`cubrid+pycubrid://dba@localhost:33000/testdb`

## Setup

```bash
cd python/pandas
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Recipes

- `01_read_sql.py`
  - Load a full table into a DataFrame with `pd.read_sql`.
  - Prints full rows, dtypes, and `head()`.
- `02_read_sql_query_params.py`
  - Run a filtered query using `sqlalchemy.text()` parameters.
  - Demonstrates safe parameter binding in `pd.read_sql_query`.
- `03_clean_and_transform.py`
  - Clean raw columns using `.rename()`, `.assign()`, and `.apply()`.
  - Converts cents to dollars and integer flags to booleans.
- `04_groupby_report.py`
  - Aggregate data by category and region with `groupby().agg()`.
  - Demonstrates `sum`, `mean`, `count`, and sorted output.
- `05_to_sql_append_replace.py`
  - Write DataFrames with `to_sql` using `if_exists="replace"` and `if_exists="append"`.
  - Reads back and prints final table state.
- `06_export_csv.py`
  - End-to-end query, summary build, and CSV export.
  - Writes `cookbook_monthly_sales_summary.csv`.

## Run

```bash
python3 01_read_sql.py
python3 02_read_sql_query_params.py
python3 03_clean_and_transform.py
python3 04_groupby_report.py
python3 05_to_sql_append_replace.py
python3 06_export_csv.py
```

## Notes

- Each script is self-contained.
- Each script creates `cookbook_` tables, seeds sample rows, and drops tables in a `finally` block.
- Boolean data is stored as `INTEGER` (`0/1`), and money is stored as integer cents.
