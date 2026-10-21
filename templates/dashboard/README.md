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

1. `01_table_viewer.py` - Query display with `st.dataframe`, re-read when you click Refresh (no auto-refresh)
2. `02_filters.py` - Sidebar category and price filters with dynamic `WHERE` clauses
3. `03_kpis.py` - KPI cards with `st.metric` using `COUNT`, `SUM`, and `AVG`
4. `04_charts.py` - Grouped bar and line charts using native Streamlit chart APIs
5. `05_form_crud.py` - Insert/update/delete flows using `st.form`

## One-command demo (Docker)

```bash
docker compose up -d
# → CUBRID 11.4 on localhost:33000 + dashboard at http://localhost:8501
```

The compose file starts CUBRID 11.4 and a Streamlit service that installs the
pinned requirements on first start (a few minutes; later runs reuse the pip
cache). Recipes read `DATABASE_URL` from the environment (default
`cubrid+pycubrid://dba@localhost:33000/testdb`), and the compose service points
it at the co-located container. `docker compose down` keeps the database in named
volumes; `docker compose down -v` resets everything.

### Upgrading a dashboard started from an earlier compose file

Before #413 the database lived in a volume without a name, and the container had
no fixed host name. The new file mounts a new, empty named volume, so a stack
started from the earlier file would come up with an empty database. Your data is
still in the old volume; move it once, from this folder. **Do not run
`docker compose down -v`, which deletes the data.** Before you update the
template, note the old volume and stop the stack:

```bash
OLD=$(docker inspect cubrid-dashboard --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker compose stop
```

Then update the template (`git pull`), copy the database into the new named
volume, point it at the new host name and start the stack:

```bash
docker compose create cubrid
NEW=$(docker inspect cubrid-dashboard --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker run --rm -v "$OLD":/from:ro -v "$NEW":/to --entrypoint sh cubrid/cubrid:11.4 -c 'cp -a /from/. /to/ && sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1cubrid-dashboard/" /to/databases.txt && chown cubrid:cubrid /to/databases.txt'
docker compose up -d
```

When your data is back, `docker volume rm "$OLD"` removes the old copy.

## Local setup (no Docker for the app)

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
