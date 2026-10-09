# Third-Party Software Licenses

This file records the third-party open-source software that the
**cubrid-cookbook-python** examples and templates depend on, and the
third-party material actually stored in this repository. It is an engineering
inventory, not legal advice.

## Scope

- **Covered:** every `requirements*.txt` in the repository; the CI tooling that
  the workflows and the `.github/actions/pr-smoke` action install directly
  (`TOOLING`: `ruff`, `pytest`, `pytest-asyncio`; the action's `pandas`,
  `matplotlib` and `pytest` are covered by other sets); the documentation build
  tools pinned in `.github/requirements-docs.txt` (`DOCS`: `mkdocs`,
  `mkdocs-material`, `pymdown-extensions`, recorded at exactly the pinned
  versions; their transitive dependencies are resolved, not pinned); and the imports of `demos/render_gif.py`, which
  renders the demo GIF (`DEMO`: `imageio`, `pillow`). The repository's
  `pyproject.toml` holds only Ruff configuration and declares no dependencies.
- **Covered by the sets above, not listed separately:** `scripts/release_smoke.py`
  installs the published drivers (`pycubrid`, `sqlalchemy`,
  `sqlalchemy-cubrid`, `cubrid-mcp-server`) to smoke-test a release, and the
  README and docs show `pip install pycubrid` / `sqlalchemy-cubrid` commands;
  all of these packages appear in the table.
- **Not flattened:** each example is installed on its own. Requirement files
  with identical contents form one *requirement set*, and every set was
  installed into its own fresh environment. The package table below
  consolidates those environments and names the sets that pulled each package
  in, with every version observed across them.
- **Snapshot, not contract:** the versions are what the resolver chose when the
  inventory was generated. The ranges in each requirements file remain
  authoritative.
- **Scoped out:** the `cubrid/cubrid` server image and the `python` base images
  used by `Dockerfile`s and `docker-compose.yml` files are pulled at run time
  and are not stored in or distributed from this repository; the server's
  license is recorded below for reference.

> **CUBRID server license, for the record.** The CUBRID server engine is
> distributed under Apache License 2.0 and the official APIs/connectors under
> BSD (upstream `COPYING`, http://www.cubrid.org/cubrid) — the frequently cited
> GPL v2+ no longer applies. This project is an independent wire-protocol client
> that neither includes nor links any CUBRID server code; the `cubrid/cubrid`
> Docker image is used for CI and demo verification only.

## Dependencies versus material stored in this repository

This repository publishes no package. It distributes example source code that
users install dependencies for themselves; it does not bundle or redistribute
any dependency.

Third-party material actually stored in the repository:

- **`docs/demo-agent-state.gif`** is produced by this project: `demos/render_gif.py`
  draws the frames from `demos/agent-state.json` (this project's own recorded
  example output) with Pillow and writes them with imageio, using GitHub-dark
  colors. Its text is rasterised from a system font: DejaVu Sans Mono
  (Bitstream Vera / DejaVu license) when installed, otherwise Liberation Mono
  (the 1.x series that Debian and Ubuntu install at that path is GPL-2.0 with a
  font exception; Liberation 2.x is SIL OFL 1.1), otherwise Pillow's built-in
  default font; which one rendered
  the committed file is not recorded. The GIF contains rendered glyph images,
  not a font file, and no third-party image or code. The `demos/*.tape` VHS
  scripts are an alternative recording setup and did not produce the
  committed GIF.
- No other image, font, video, stylesheet or script asset is stored in the
  repository, and no third-party source code is vendored.

## License categories

- **Permissive**: MIT, MIT-0, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, the
  Unlicense and the Python Software Foundation License, as declared by each
  package. The generator also accepts 0BSD, Public Domain and a generic "BSD
  License" declaration as permissive. Most packages fall here.
- **Weak (file-level) copyleft: MPL**: `certifi` (through `requests` and
  `httpx`) and `pathspec` (through `mkdocs`, tooling only), both MPL-2.0; the
  package table's **Sets** column lists the requirement sets that use them.
  MPL-2.0 is not a permissive license. Its obligations attach to the
  MPL-covered files themselves: anyone distributing those files,
  modified or not, must make their source available under MPL-2.0 and keep
  their notices. Because MPL-2.0 is file-level, it never extends to the
  examples' own files (MPL §3.3, "Larger Work"). Separately, this repository
  does not distribute these packages, so their distribution obligations do not
  arise for it.
- **Needs review**: any package whose metadata mentions a GPL-family license, or
  a license the generator cannot fully classify. Multiple license classifiers do
  not say whether they combine as "or" or "and", so these are never treated as
  permissive automatically. Each one is resolved below.

### Reviewed entries

- **numpy** (2.5.3, pulled in by `pandas`, `matplotlib` and `imageio`; see the
  **Sets** column). Its PEP 639 expression, `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND
  CC0-1.0`, covers numpy's own sources; Zlib and CC0-1.0 are permissive too,
  but the generator does not auto-accept them. The Linux wheel also bundles
  compiled libraries, listed in its own `LICENSE.txt`: OpenBLAS
  (BSD-3-Clause), LAPACK (BSD-3-Clause-Open-MPI), the GCC Fortran runtime
  `libgfortran` (GPL-3.0-or-later WITH GCC-exception-3.1) and the GCC
  quad-precision math library `libquadmath` (LGPL-2.1-or-later, dynamically
  linked). The GCC Runtime Library Exception exists so that non-GPL programs
  can use the runtime; LGPL-2.1 permits dynamic linking from programs under
  other licenses. The examples only import numpy, and this repository does not
  redistribute the wheel. As installed, numpy is permissive plus
  `libgfortran` (GPL-3.0-or-later with the exception) and `libquadmath`
  (LGPL-2.1-or-later) as separate shared libraries.
- **pillow** (12.3.0, pulled in by `matplotlib` and `streamlit`, and imported
  by `demos/render_gif.py`). Pillow itself is `MIT-CMU`, a permissive historical license.
  The Linux wheel bundles image, compression and font libraries whose notices
  its `LICENSE` reproduces, including AOM, Brotli, bzip2, dav1d, HarfBuzz, Little CMS,
  libavif, libjpeg, liblzma, libpng, libtiff, libwebp, libyuv, OpenJPEG, raqm,
  Tcl/Tk, libXau, libxcb, XDMCP, zlib and zstd, all under permissive or
  public-domain terms, plus FreeType. FreeType is dual-licensed: the FreeType License
  (BSD-style, with a credit clause) or GPL-2.0-or-later, at the user's choice.
  The other GPL text in that file belongs to XZ Utils command-line and build
  files that, as it states, do not end up in liblzma. As installed, Pillow is
  permissive, with FreeType usable under the FreeType License.
- **protobuf** (7.36.2, pulled in by `streamlit`). Its metadata says
  only "3-Clause BSD License", a wording the generator does not recognise; its
  `LICENSE` file is the BSD-3-Clause text (Copyright 2008 Google Inc.).

## How the inventory was generated

- Requirement files: commit `277584cc477919edf6e863481199680ab171adee`
- Environment: CPython 3.12.13 on Linux x86_64 (glibc 2.35), uv 0.11.7,
  generated 2026-10-09
- Command (creates one fresh `uv` environment per requirement set and rewrites
  the generated section below):

```bash
python scripts/build_license_inventory.py --python 3.12 \
    --exclude-newer 2026-10-09T00:00:00Z --write
```

`--exclude-newer` limits resolution to what PyPI offered at that instant, so
rerunning the command reproduces the same versions.

`scripts/build_license_inventory.py` and `scripts/generate_third_party_licenses.py`
use only the standard library; the generator is shared with pycubrid,
sqlalchemy-cubrid and cubrid-mcp-server. It reads the PEP 639
`License-Expression` field, then `License ::` classifiers, then a short
`License` field, and never guesses a license. `tests/test_third_party_licenses.py`
fails when a requirements file is not listed in a set, when a file's declared
packages differ from its set's, when a package that a workflow or action installs directly is missing
from the inventory, when a row's category disagrees with what the
generator would assign to its license, or when an MPL or "Needs review" row is
not explained. Version bumps inside a requirements file do not fail it: the
versions here are a dated snapshot, and a bump that makes two files of one set
differ only splits that set at the next regeneration (set IDs are table-local
and are not referenced elsewhere). Regenerate the inventory when a file is
added or removed, or when its declared packages change.

## Inventory

<!-- BEGIN GENERATED INVENTORY: scripts/build_license_inventory.py -->

### Requirement sets

| Set | Requirement files | Declared packages |
|---|---|---|
| S01 | `fundamentals/alembic/requirements.txt` | alembic, pycubrid, sqlalchemy, sqlalchemy-cubrid |
| S02 | `fundamentals/async/requirements.txt` | pycubrid, sqlalchemy, sqlalchemy-cubrid |
| S03 | `fundamentals/connect/requirements.txt` | pycubrid |
| S04 | `fundamentals/isolation-levels/requirements.txt`<br>`fundamentals/json/requirements.txt`<br>`pitfalls/reserved-words/requirements.txt` | pycubrid |
| S05 | `fundamentals/orm-basics/requirements.txt` | pycubrid, sqlalchemy, sqlalchemy-cubrid |
| S06 | `fundamentals/pandas/requirements.txt` | pandas, pycubrid, sqlalchemy, sqlalchemy-cubrid |
| S07 | `fundamentals/pycubrid/requirements.txt` | pycubrid |
| S08 | `fundamentals/sqlalchemy/requirements.txt` | pycubrid, sqlalchemy, sqlalchemy-cubrid |
| S09 | `migration/java-to-python/requirements.txt` | pycubrid, sqlalchemy-cubrid |
| S10 | `quickstart/5min-fastapi/requirements.txt` | fastapi, pycubrid, uvicorn |
| S11 | `quickstart/5min-sqlalchemy/requirements.txt` | pycubrid, sqlalchemy, sqlalchemy-cubrid |
| S12 | `templates/ai-agent/requirements.txt` | cubrid-mcp-server, pycubrid, sqlalchemy-cubrid |
| S13 | `templates/api-service-fastapi/recipes/01-basic-crud/requirements.txt`<br>`templates/api-service-fastapi/recipes/03-catalog-sync/requirements.txt`<br>`templates/api-service-fastapi/recipes/06-price-books/requirements.txt`<br>`templates/api-service-fastapi/recipes/07-document-publishing/requirements.txt`<br>`templates/api-service-fastapi/recipes/08-webhook-inbox/requirements.txt` | fastapi, pycubrid, sqlalchemy, sqlalchemy-cubrid, uvicorn |
| S14 | `templates/api-service-fastapi/recipes/02-orders/requirements.txt`<br>`templates/api-service-fastapi/recipes/04-audit-trail/requirements.txt`<br>`templates/api-service-fastapi/recipes/05-multi-tenant-search/requirements.txt` | email-validator, fastapi, pycubrid, sqlalchemy, sqlalchemy-cubrid, uvicorn |
| S15 | `templates/api-service-fastapi/recipes/09-saga/requirements.txt` | fastapi, httpx, pycubrid, pytest, sqlalchemy, sqlalchemy-cubrid, uvicorn |
| S16 | `templates/api-service-fastapi/recipes/10-cqrs-event-sourcing/requirements.txt` | fastapi, httpx, pycubrid, pydantic, pytest, sqlalchemy, sqlalchemy-cubrid, uvicorn |
| S17 | `templates/api-service-fastapi/recipes/11-rate-limiter/requirements.txt`<br>`templates/api-service-fastapi/recipes/12-reservation-scheduling/requirements.txt` | fastapi, httpx, pycubrid, pydantic, pytest, sqlalchemy, sqlalchemy-cubrid, uvicorn |
| S18 | `templates/api-service-fastapi/requirements.txt` | fastapi, pycubrid, pydantic-settings, sqlalchemy, sqlalchemy-cubrid, uvicorn |
| S19 | `templates/async-worker/requirements.txt` | celery, pycubrid, sqlalchemy, sqlalchemy-cubrid |
| S20 | `templates/batch-etl/requirements.txt` | matplotlib, pandas, pycubrid, sqlalchemy, sqlalchemy-cubrid |
| S21 | `templates/dashboard/requirements.txt` | pandas, pycubrid, sqlalchemy, sqlalchemy-cubrid, streamlit |
| S22 | `templates/django/requirements.txt` | django, pycubrid, sqlalchemy, sqlalchemy-cubrid |
| S23 | `templates/flask/01-basic-crud/requirements.txt`<br>`templates/flask/02-categories/requirements.txt`<br>`templates/flask/03-inventory-ledger/requirements.txt`<br>`templates/flask/04-purchase-orders/requirements.txt`<br>`templates/flask/05-batch-operations/requirements.txt`<br>`templates/flask/06-case-triage/requirements.txt`<br>`templates/flask/07-vendor-feed/requirements.txt`<br>`templates/flask/08-transactional-outbox/requirements.txt`<br>`templates/flask/10-workflow-engine/requirements.txt`<br>`templates/flask/11-inventory-reservation/requirements.txt` | flask, flask-sqlalchemy, pycubrid, sqlalchemy-cubrid |
| S24 | `templates/flask/09-rbac/requirements.txt` | flask, flask-sqlalchemy, pycubrid, pytest, sqlalchemy, sqlalchemy-cubrid |
| S25 | `templates/flask/requirements.txt` | flask, flask-sqlalchemy, httpx, pycubrid, pytest, sqlalchemy, sqlalchemy-cubrid |
| TOOLING | CI and docs workflows and the PR-smoke action (the TOOLING constant in this script) | pytest, pytest-asyncio, ruff |
| DOCS | `.github/requirements-docs.txt` | mkdocs, mkdocs-material, pymdown-extensions |
| DEMO | demos/render_gif.py imports (the DEMO constant in this script) | imageio, pillow |

### Packages (144 rows)

| Name | Observed versions | License | Category | URL | Sets |
|---|---|---|---|---|---|
| aiofile | 3.12.3 | Apache-2.0 | Permissive | https://github.com/mosquito/aiofile | S12 |
| alembic | 1.20.0 | MIT | Permissive | https://alembic.sqlalchemy.org | S01 |
| altair | 6.3.0 | BSD License | Permissive | https://github.com/vega/altair | S21 |
| amqp | 5.4.1 | BSD License | Permissive | http://github.com/celery/py-amqp | S19 |
| annotated-doc | 0.0.5 | MIT | Permissive | https://github.com/fastapi/annotated-doc | S10, S13, S14, S15, S16, S17, S18 |
| annotated-types | 0.8.0 | MIT | Permissive | https://github.com/annotated-types/annotated-types | S10, S12, S13, S14, S15, S16, S17, S18 |
| anyio | 4.15.1 | MIT | Permissive | https://github.com/agronholm/anyio | S10, S12, S13, S14, S15, S16, S17, S18, S21, S25 |
| asgiref | 3.12.1 | BSD License | Permissive | https://github.com/django/asgiref/ | S22 |
| attrs | 26.1.0 | MIT | Permissive | - | S12, S21 |
| Authlib | 1.8.0 | BSD License | Permissive | https://github.com/authlib/authlib | S12 |
| babel | 2.18.0 | BSD License | Permissive | https://github.com/python-babel/babel | DOCS |
| backrefs | 8.0 | MIT | Permissive | https://github.com/facelessuser/backrefs | DOCS |
| beartype | 0.22.9 | MIT License | Permissive | - | S12 |
| billiard | 4.3.1 | BSD License | Permissive | https://github.com/celery/billiard | S19 |
| blinker | 1.9.0 | MIT License | Permissive | https://github.com/pallets-eco/blinker/ | S23, S24, S25 |
| cachetools | 7.2.1 | MIT | Permissive | https://github.com/tkem/cachetools/ | S12 |
| caio | 0.12.9 | Apache-2.0 | Permissive | https://github.com/mosquito/caio/ | S12 |
| celery | 5.6.3 | BSD-3-Clause | Permissive | https://docs.celeryq.dev/ | S19 |
| cffi | 2.1.1 | MIT-0 | Permissive | https://github.com/python-cffi/cffi | S12 |
| charset-normalizer | 3.5.2 | MIT | Permissive | - | DOCS, S21 |
| click | 8.5.0 | BSD-3-Clause | Permissive | https://github.com/pallets/click/ | DOCS, S10, S12, S13, S14, S15, S16, S17, S18, S19, S21, S23, S24, S25 |
| click-didyoumean | 0.3.1 | MIT License | Permissive | https://github.com/click-contrib/click-didyoumean | S19 |
| click-plugins | 1.1.1.2 | BSD License | Permissive | https://github.com/click-contrib/click-plugins | S19 |
| click-repl | 0.4.1 | MIT | Permissive | https://github.com/click-contrib/click-repl | S19 |
| colorama | 0.4.6 | BSD License | Permissive | https://github.com/tartley/colorama | DOCS |
| contourpy | 1.4.0 | BSD-3-Clause | Permissive | https://github.com/contourpy/contourpy | S20 |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Permissive | https://github.com/pyca/cryptography | S12 |
| cubrid-mcp-server | 0.4.0 | MIT | Permissive | https://github.com/cubrid-lab/cubrid-mcp-server | S12 |
| cycler | 0.12.1 | BSD License | Permissive | https://matplotlib.org/cycler/ | S20 |
| cyclopts | 5.2.0 | Apache-2.0 | Permissive | https://github.com/BrianPugh/cyclopts | S12 |
| Django | 6.1.2 | BSD-3-Clause | Permissive | https://www.djangoproject.com/ | S22 |
| dnspython | 2.8.0 | ISC License (ISCL) | Permissive | https://www.dnspython.org | S12, S14 |
| docstring_parser | 0.18.0 | MIT License | Permissive | https://github.com/rr-/docstring_parser | S12 |
| email-validator | 2.3.0 | The Unlicense (Unlicense) | Permissive | https://github.com/JoshData/python-email-validator | S12, S14 |
| exceptiongroup | 1.3.1 | MIT License | Permissive | https://github.com/agronholm/exceptiongroup | S12 |
| fastapi | 0.141.1, 0.143.0 | MIT | Permissive | https://github.com/fastapi/fastapi | S10, S13, S14, S15, S16, S17, S18 |
| fastmcp | 3.4.8 | Apache-2.0 | Permissive | https://gofastmcp.com | S12 |
| fastmcp-slim | 3.4.8 | Apache-2.0 | Permissive | https://gofastmcp.com | S12 |
| Flask | 3.1.3 | BSD-3-Clause | Permissive | https://github.com/pallets/flask/ | S23, S24, S25 |
| Flask-SQLAlchemy | 3.1.1 | BSD License | Permissive | https://github.com/pallets-eco/flask-sqlalchemy/ | S23, S24, S25 |
| fonttools | 4.66.1 | MIT | Permissive | http://github.com/fonttools/fonttools | S20 |
| ghp-import | 2.1.0 | Apache Software License | Permissive | https://github.com/c-w/ghp-import | DOCS |
| greenlet | 3.5.6 | MIT AND PSF-2.0 | Permissive | https://greenlet.readthedocs.io | S02 |
| griffelib | 2.3.2 | ISC | Permissive | - | S12 |
| h11 | 0.16.0 | MIT License | Permissive | https://github.com/python-hyper/h11 | S10, S12, S13, S14, S15, S16, S17, S18, S21, S25 |
| httpcore | 1.0.9 | BSD-3-Clause | Permissive | https://www.encode.io/httpcore/ | S12, S15, S16, S17, S25 |
| httptools | 0.8.0 | MIT | Permissive | https://github.com/MagicStack/httptools | S15, S21 |
| httpx | 0.28.1 | BSD License | Permissive | https://github.com/encode/httpx | S12, S15, S16, S17, S25 |
| httpx-sse | 0.4.3 | MIT | Permissive | https://github.com/florimondmanca/httpx-sse | S12 |
| idna | 3.20 | BSD-3-Clause | Permissive | https://github.com/kjd/idna | DOCS, S10, S12, S13, S14, S15, S16, S17, S18, S21, S25 |
| ImageIO | 2.38.1 | BSD-2-Clause | Permissive | https://github.com/imageio/imageio | DEMO |
| iniconfig | 2.3.1 | MIT | Permissive | https://github.com/pytest-dev/iniconfig | S15, S16, S17, S24, S25, TOOLING |
| itsdangerous | 2.2.0 | BSD License | Permissive | https://github.com/pallets/itsdangerous/ | S21, S23, S24, S25 |
| jaraco.classes | 3.4.0 | MIT License | Permissive | https://github.com/jaraco/jaraco.classes | S12 |
| jaraco.context | 6.1.2 | MIT | Permissive | https://github.com/jaraco/jaraco.context | S12 |
| jaraco.functools | 4.6.0 | MIT | Permissive | https://github.com/jaraco/jaraco.functools | S12 |
| jeepney | 0.9.0 | MIT | Permissive | https://gitlab.com/takluyver/jeepney | S12 |
| Jinja2 | 3.1.6 | BSD License | Permissive | https://github.com/pallets/jinja/ | DOCS, S21, S23, S24, S25 |
| joserfc | 1.7.5 | BSD License | Permissive | https://github.com/authlib/joserfc | S12 |
| jsonref | 1.1.0 | MIT | Permissive | https://github.com/gazpachoking/jsonref | S12 |
| jsonschema | 4.26.0 | MIT | Permissive | https://github.com/python-jsonschema/jsonschema | S12, S21 |
| jsonschema-path | 0.5.0 | Apache Software License | Permissive | https://github.com/p1c2u/jsonschema-path | S12 |
| jsonschema-specifications | 2025.9.1 | MIT | Permissive | https://github.com/python-jsonschema/jsonschema-specifications | S12, S21 |
| keyring | 25.7.0 | MIT | Permissive | https://github.com/jaraco/keyring | S12 |
| kiwisolver | 1.5.1 | BSD License | Permissive | https://github.com/nucleic/kiwi | S20 |
| kombu | 5.6.2 | BSD-3-Clause | Permissive | https://github.com/celery/kombu | S19 |
| Mako | 1.4.3 | MIT | Permissive | https://www.makotemplates.org/ | S01 |
| Markdown | 3.11 | BSD-3-Clause | Permissive | https://Python-Markdown.github.io/ | DOCS |
| markdown-it-py | 4.2.0 | MIT License | Permissive | https://github.com/executablebooks/markdown-it-py | S12 |
| MarkupSafe | 3.0.4 | BSD-3-Clause | Permissive | https://github.com/pallets/markupsafe/ | DOCS, S01, S21, S23, S24, S25 |
| matplotlib | 3.11.2 | Python Software Foundation License | Permissive | https://matplotlib.org | S20 |
| mcp | 1.30.0 | MIT License | Permissive | https://modelcontextprotocol.io | S12 |
| mdurl | 0.1.2 | MIT License | Permissive | https://github.com/executablebooks/mdurl | S12 |
| mergedeep | 1.3.4 | MIT License | Permissive | https://github.com/clarketm/mergedeep | DOCS |
| mkdocs | 1.6.1 | BSD-2-Clause | Permissive | https://github.com/mkdocs/mkdocs | DOCS |
| mkdocs-get-deps | 0.2.2 | MIT | Permissive | https://github.com/mkdocs/get-deps | DOCS |
| mkdocs-material | 9.7.7 | MIT | Permissive | https://github.com/squidfunk/mkdocs-material | DOCS |
| mkdocs-material-extensions | 1.3.1 | MIT | Permissive | https://github.com/facelessuser/mkdocs-material-extensions | DOCS |
| more-itertools | 11.1.0 | MIT | Permissive | https://github.com/more-itertools/more-itertools | S12 |
| narwhals | 2.26.0 | MIT | Permissive | https://github.com/narwhals-dev/narwhals | S21 |
| openapi-pydantic | 0.6.0 | MIT License | Permissive | https://github.com/mike-oakley/openapi-pydantic | S12 |
| opentelemetry-api | 1.45.1 | Apache-2.0 | Permissive | https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-api | S10, S12, S13, S14, S15, S17, S18 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | Permissive | https://github.com/pypa/packaging | DOCS, S12, S15, S16, S17, S19, S20, S21, S24, S25, TOOLING |
| paginate | 0.5.7 | MIT License | Permissive | https://github.com/Signum/paginate | DOCS |
| pandas | 3.0.6 | BSD License | Permissive | https://pandas.pydata.org | S06, S20, S21 |
| pathable | 0.6.0 | Apache Software License | Permissive | https://github.com/p1c2u/pathable | S12 |
| platformdirs | 4.12.4 | MIT | Permissive | https://github.com/tox-dev/platformdirs | DOCS, S12 |
| pluggy | 1.6.0 | MIT License | Permissive | - | S15, S16, S17, S24, S25, TOOLING |
| prompt_toolkit | 3.0.53 | BSD License | Permissive | https://github.com/prompt-toolkit/python-prompt-toolkit | S19 |
| py-key-value-aio | 0.4.6 | Apache-2.0 | Permissive | - | S12 |
| pyarrow | 25.0.1 | Apache-2.0 | Permissive | https://arrow.apache.org/ | S21 |
| pycparser | 3.1 | BSD-3-Clause | Permissive | https://github.com/eliben/pycparser | S12 |
| pycubrid | 1.9.0 | MIT | Permissive | https://github.com/cubrid-lab/pycubrid | S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11, S12, S13, S14, S15, S16, S17, S18, S19, S20, S21, S22, S23, S24, S25 |
| pydantic | 2.13.5, 2.14.0 | MIT | Permissive | https://github.com/pydantic/pydantic | S10, S12, S13, S14, S15, S16, S17, S18 |
| pydantic_core | 2.46.5, 2.50.0 | MIT | Permissive | https://github.com/pydantic | S10, S12, S13, S14, S15, S16, S17, S18 |
| pydantic-settings | 2.15.0 | MIT | Permissive | https://github.com/pydantic/pydantic-settings | S12, S18 |
| pydeck | 0.9.3 | Apache License 2.0 | Permissive | https://github.com/visgl/deck.gl/tree/master/bindings/pydeck | S21 |
| Pygments | 2.21.0 | BSD-2-Clause | Permissive | https://pygments.org | DOCS, S12, S15, S16, S17, S24, S25, TOOLING |
| PyJWT | 2.15.1 | MIT | Permissive | https://github.com/jpadilla/pyjwt | S12 |
| pymdown-extensions | 12.1 | MIT | Permissive | https://github.com/facelessuser/pymdown-extensions | DOCS |
| pyparsing | 3.3.3 | MIT | Permissive | https://github.com/pyparsing/pyparsing/ | S20 |
| pyperclip | 1.11.0 | BSD License | Permissive | https://github.com/asweigart/pyperclip | S12 |
| pytest | 9.1.1 | MIT | Permissive | https://docs.pytest.org/en/latest/ | S15, S16, S17, S24, S25, TOOLING |
| pytest-asyncio | 1.4.0 | Apache-2.0 | Permissive | https://github.com/pytest-dev/pytest-asyncio | TOOLING |
| python-dateutil | 2.9.0.post0 | Apache Software License / BSD License | Permissive | https://github.com/dateutil/dateutil | DOCS, S06, S19, S20, S21 |
| python-dotenv | 1.2.4 | BSD-3-Clause | Permissive | https://github.com/theskumar/python-dotenv | S12, S15, S18 |
| python-multipart | 0.0.32 | Apache-2.0 | Permissive | https://github.com/Kludex/python-multipart | S12, S21 |
| PyYAML | 6.0.3 | MIT License | Permissive | https://github.com/yaml/pyyaml | DOCS, S12, S15 |
| pyyaml_env_tag | 1.1 | MIT | Permissive | https://github.com/waylan/pyyaml-env-tag | DOCS |
| redis | 6.4.0 | MIT | Permissive | https://github.com/redis/redis-py | S19 |
| referencing | 0.37.0 | MIT | Permissive | https://github.com/python-jsonschema/referencing | S12, S21 |
| requests | 2.34.2 | Apache Software License | Permissive | https://github.com/psf/requests | DOCS, S21 |
| rich | 15.0.0 | MIT License | Permissive | https://github.com/Textualize/rich | S12 |
| rich-rst | 2.2.0 | MIT | Permissive | https://github.com/wasi-master/rich-rst | S12 |
| rpds-py | 2026.9.1 | MIT | Permissive | https://github.com/crate-py/rpds | S12, S21 |
| ruff | 0.16.4 | MIT | Permissive | https://github.com/astral-sh/ruff | TOOLING |
| SecretStorage | 3.5.0 | BSD-3-Clause | Permissive | https://github.com/mitya57/secretstorage | S12 |
| six | 1.17.0 | MIT License | Permissive | https://github.com/benjaminp/six | DOCS, S06, S19, S20, S21 |
| SQLAlchemy | 2.1.1, 2.1.4 | MIT | Permissive | https://www.sqlalchemy.org | S01, S02, S05, S06, S08, S09, S11, S12, S13, S14, S15, S16, S17, S18, S19, S20, S21, S22, S23, S24, S25 |
| sqlalchemy-cubrid | 1.9.0 | MIT | Permissive | https://github.com/cubrid-lab/sqlalchemy-cubrid | S01, S02, S05, S06, S08, S09, S11, S12, S13, S14, S15, S16, S17, S18, S19, S20, S21, S22, S23, S24, S25 |
| sqlparse | 0.6.0 | BSD License | Permissive | https://github.com/andialbrecht/sqlparse | S12, S22 |
| sse-starlette | 3.5.0 | BSD-3-Clause | Permissive | https://github.com/sysid/sse-starlette | S12 |
| starlette | 1.7.0 | BSD-3-Clause | Permissive | https://github.com/Kludex/starlette | S10, S12, S13, S14, S15, S16, S17, S18, S21 |
| streamlit | 1.65.0 | Apache-2.0 | Permissive | https://streamlit.io | S21 |
| toml | 0.10.2 | MIT License | Permissive | https://github.com/uiri/toml | S21 |
| typing_extensions | 4.16.0 | PSF-2.0 | Permissive | https://github.com/python/typing_extensions | S01, S02, S05, S06, S08, S09, S10, S11, S12, S13, S14, S15, S16, S17, S18, S19, S20, S21, S22, S23, S24, S25, TOOLING |
| typing-inspection | 0.4.4 | MIT | Permissive | https://github.com/pydantic/typing-inspection | S10, S12, S13, S14, S15, S16, S17, S18 |
| tzdata | 2026.5 | Apache-2.0 | Permissive | https://github.com/python/tzdata | S19 |
| tzlocal | 5.4.4 | MIT | Permissive | https://github.com/regebro/tzlocal | S19 |
| uncalled-for | 0.4.0 | MIT License | Permissive | https://github.com/chrisguidry/uncalled-for | S12 |
| urllib3 | 2.8.0 | MIT | Permissive | - | DOCS, S21 |
| uvicorn | 0.54.0 | BSD-3-Clause | Permissive | https://uvicorn.dev/ | S10, S12, S13, S14, S15, S16, S17, S18, S21 |
| uvloop | 0.23.0 | Apache Software License / MIT License | Permissive | - | S15 |
| vine | 5.1.0 | BSD License | Permissive | https://github.com/celery/vine | S19 |
| watchdog | 6.0.0 | Apache Software License | Permissive | https://github.com/gorakhargosh/watchdog/ | DOCS, S21 |
| watchfiles | 1.3.0 | MIT License | Permissive | https://github.com/samuelcolvin/watchfiles | S12, S15 |
| wcwidth | 0.9.2 | MIT License | Permissive | https://github.com/jquast/wcwidth | S19 |
| websockets | 17.2 | BSD-3-Clause | Permissive | https://github.com/python-websockets/websockets | S12, S15, S21 |
| Werkzeug | 3.1.9 | BSD-3-Clause | Permissive | https://github.com/pallets/werkzeug/ | S23, S24, S25 |
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) | Weak copyleft (MPL) | https://github.com/certifi/python-certifi | DOCS, S12, S15, S16, S17, S21, S25 |
| pathspec | 1.1.1 | Mozilla Public License 2.0 (MPL 2.0) | Weak copyleft (MPL) | https://github.com/cpburnz/python-pathspec | DOCS |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Needs review | https://numpy.org | DEMO, S06, S20, S21 |
| pillow | 12.3.0 | MIT-CMU | Needs review | https://python-pillow.github.io | DEMO, S20, S21 |
| protobuf | 7.36.2 | 3-Clause BSD License | Needs review | https://developers.google.com/protocol-buffers/ | S21 |

<!-- END GENERATED INVENTORY -->
