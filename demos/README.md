# Demo recordings

The README GIFs and the docs-site videos are screen recordings of the cookbook's
own examples running against a real CUBRID server. Nothing in them is typed in
by hand or drawn afterwards: the terminal output is what the recipe printed, and
the browser shows the running app. `recording-provenance.json` records the
versions, image digests, tool versions and media hashes of the committed files.

| Published file | Source | Shows |
|---|---|---|
| `docs/demo-agent-state.gif` (README) | `agent-state.tape` | `templates/ai-agent/01_agent_state.py` |
| `docs/demo-fastapi.gif` (README) | `record_browser.py fastapi` | `quickstart/5min-fastapi` Swagger UI: `POST /items`, then `GET /items` |
| `docs/demo-dashboard.gif` (README) | `record_browser.py dashboard` | `templates/dashboard` table viewer, Reset Demo Data, Refresh |
| `docs/assets/videos/dashboard.mp4` | `dashboard.tape` + `record_browser.py dashboard` | `docker compose up -d` in `templates/dashboard`, then the browser |
| `docs/assets/videos/agent-state.mp4` | `agent-state-video.tape` | `01_agent_state.py`, then `04_agent_loop.py` |
| `docs/assets/videos/mcp-toolchain.mp4` | `mcp-toolchain.tape` | `02_mcp_toolchain.py` driving `cubrid-mcp-server` over stdio |

## What is cut

- `dashboard.tape` hides (VHS `Hide`/`Show`) the wait for the CUBRID health
  check and for the dashboard container's `pip install`; the commands and their
  output are real, the waiting time is removed.
- The dashboard MP4 joins the terminal recording and the browser recording,
  which are captured one after the other against the same running stack.
- The GIFs are excerpts of the browser recordings (`build_media.sh`).

The AI agent recipes use a heuristic planner and no LLM (see the template
README); no recording here shows an LLM client such as Claude Desktop.

## Requirements

- Docker, `curl`, `ffmpeg` and Chrome or Chromium.
- [VHS](https://github.com/charmbracelet/vhs) **0.12.1** or later, with its ttyd
  dependency. VHS 0.12.0 exits successfully without writing any GIF or MP4
  (fixed upstream in 0.12.1); check the output files, not only the exit code.
- A Python 3.11+ virtual environment with `templates/ai-agent/requirements.txt`,
  `quickstart/5min-fastapi/requirements.txt` and `playwright`. Set `DEMO_CHROME`
  to a Chrome binary, or run `playwright install chromium`.

Use a disposable CUBRID server and database that you own. The recipes create and
reset their own `agent_*`, `cookbook_*` tables; `01_agent_state.py` and
`04_agent_loop.py` currently need an empty database for each run.

## Record

From the repository root, with the virtual environment active:

```bash
# 1. Terminal demos against a fresh CUBRID 11.4 (CUBRID_PORT if not 33000)
docker run -d --name demo-cubrid -p 127.0.0.1:33000:33000 -e CUBRID_DB=testdb cubrid/cubrid:11.4
timeout 180 bash -c 'until docker exec demo-cubrid csql -u dba testdb -c "SELECT 1" > /dev/null 2>&1; do sleep 2; done'
vhs validate demos/*.tape
vhs demos/agent-state.tape
# 01 and 04 need an empty database (#302): drop their tables, children first
docker exec demo-cubrid csql -u dba testdb -c "DROP TABLE IF EXISTS agent_tool_calls, agent_messages, agent_sessions, cookbook_agent_products"
vhs demos/agent-state-video.tape
vhs demos/mcp-toolchain.tape
docker rm -f demo-cubrid

# 2. FastAPI quickstart in the browser
(cd quickstart/5min-fastapi && docker compose up -d --wait cubrid)
(cd quickstart/5min-fastapi && uvicorn app:app --port 8000) &   # stop it afterwards
python demos/record_browser.py fastapi
(cd quickstart/5min-fastapi && docker compose down -v)

# 3. Dashboard: the tape starts the stack, the browser recording uses it
vhs demos/dashboard.tape
python demos/record_browser.py dashboard
(cd templates/dashboard && docker compose down -v)

# 4. Convert, then review before copying into docs/
bash demos/build_media.sh
```

All outputs go to the ignored `.demo-artifacts/` directory. `build_media.sh`
writes `.demo-artifacts/out/`; watch every file in full and check it with
`ffprobe` before copying it over the published file. Targets: README GIFs 8–12
seconds and under about 2 MB; docs-site MP4s 30–60 seconds, H.264, `yuv420p`.
Update `recording-provenance.json` and the hashes in it in the same change.

No VHS publish, external upload or release step is part of this workflow.
