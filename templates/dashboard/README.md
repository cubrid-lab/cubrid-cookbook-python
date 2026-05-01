# Streamlit Recipes for CUBRID

Five standalone Streamlit recipes are provided in this directory. Each recipe is one `.py` file and can be run directly with `streamlit run <file>.py`.

All recipes use:

- Connection: `cubrid+pycubrid://dba@localhost:33000/testdb`
- `@st.cache_resource` for SQLAlchemy engine caching
- Tables prefixed with `cookbook_`
- Integer `0/1` for booleans (`is_active`)
- Integer cents for money (`unit_price_cents`)
- A **Reset Demo Data** button that drops and recreates demo tables

## Recipes

1. `01_table_viewer.py` - Live query display with `st.dataframe` and auto-refresh
2. `02_filters.py` - Sidebar category and price filters with dynamic `WHERE` clauses
3. `03_kpis.py` - KPI cards with `st.metric` using `COUNT`, `SUM`, and `AVG`
4. `04_charts.py` - Grouped bar and line charts using native Streamlit chart APIs
5. `05_form_crud.py` - Insert/update/delete flows using `st.form`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run 01_table_viewer.py
streamlit run 02_filters.py
streamlit run 03_kpis.py
streamlit run 04_charts.py
streamlit run 05_form_crud.py
```

## Notes

- On first run, each recipe ensures demo tables exist and seeds sample rows when empty.
- If you want a clean state for a recipe, use its **Reset Demo Data** button.
