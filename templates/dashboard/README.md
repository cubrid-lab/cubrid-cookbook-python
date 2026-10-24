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

Compose publishes the CUBRID broker (`127.0.0.1:33000`) and the dashboard
(`127.0.0.1:8501`) on this host only; the lab `dba` account has no password, so
the broker is never published on other interfaces. To let other machines reach
the dashboard on purpose, set `DASHBOARD_HOST_IP` (for example
`DASHBOARD_HOST_IP=0.0.0.0 docker compose up -d`).

### Upgrading a dashboard started from an earlier compose file

CUBRID records the host name of the container that created the database. The
current file sets `CUBRID_DB_HOST: localhost` and leaves the container name to
Compose. If your stack was started from a file after #413, its database is
already in the named volumes: point it at `localhost` and restart.

```bash
docker compose up -d cubrid
docker compose exec -T -u cubrid cubrid sh -c 'sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1localhost/" "$CUBRID_DATABASES/databases.txt"'
docker compose restart cubrid
docker compose up -d
```

Before #413 the database lived in a volume without a name. The current file
mounts a new, empty named volume, so a stack started from that earlier file
would come up with an empty database. Your data is
still in the old volume; move it once, from this folder. **Do not run
`docker compose down -v`, which deletes the data.** Before you update the
template, note the old volume and stop the stack:

```bash
OLD=$(docker inspect cubrid-dashboard --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker compose stop
```

Then update the template (`git pull`), copy the database into the new named
volume, point it at `localhost` and start the stack:

```bash
docker compose create cubrid
NEW=$(docker inspect "$(docker compose ps -aq cubrid)" --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker run --rm -v "$OLD":/from:ro -v "$NEW":/to --entrypoint sh cubrid/cubrid:11.4 -c 'cp -a /from/. /to/ && sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1localhost/" /to/databases.txt && chown cubrid:cubrid /to/databases.txt'
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
