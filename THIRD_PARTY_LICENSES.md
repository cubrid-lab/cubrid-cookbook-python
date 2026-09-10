# Third-Party Software Licenses

This file lists the third-party open-source software used by the **cubrid-cookbook-python** examples and templates — the union of every `requirements.txt` under `templates/` and the dependency-carrying `fundamentals/` recipes, resolved and generated with `pip-licenses`.

All listed dependencies are distributed under permissive licenses (MIT, BSD-2/3-Clause, Apache-2.0, PSF, MPL-2.0). No dependency is copyleft/GPL, and none conflicts with this project's MIT license. This repository distributes example source code only; no packages are published from it.

> **CUBRID server license, for the record.** The CUBRID server engine is
> distributed under Apache License 2.0 and the official APIs/connectors under
> BSD (upstream `COPYING`, http://www.cubrid.org/cubrid) — the frequently cited
> GPL v2+ no longer applies. This project is an independent wire-protocol client
> that neither includes nor links any CUBRID server code; the `cubrid/cubrid`
> Docker image is used for CI and demo verification only.

## Dependencies (union of template/example requirements)

| Name                      | Version      | License                              | URL                                                                  |
|---------------------------|--------------|--------------------------------------|----------------------------------------------------------------------|
| protobuf                  | 7.36.1       | 3-Clause BSD License                 | https://developers.google.com/protocol-buffers/                      |
| pydeck                    | 0.9.3        | Apache License 2.0                   | https://github.com/visgl/deck.gl/tree/master/bindings/pydeck         |
| async-timeout             | 5.0.1        | Apache Software License              | https://github.com/aio-libs/async-timeout                            |
| requests                  | 2.34.2       | Apache Software License              | https://github.com/psf/requests                                      |
| watchdog                  | 6.0.0        | Apache Software License              | https://github.com/gorakhargosh/watchdog                             |
| python-dateutil           | 2.9.0.post0  | Apache Software License; BSD License | https://github.com/dateutil/dateutil                                 |
| pyarrow                   | 25.0.1       | Apache-2.0                           | https://arrow.apache.org/                                            |
| python-multipart          | 0.0.32       | Apache-2.0                           | https://github.com/Kludex/python-multipart                           |
| streamlit                 | 1.63.0       | Apache-2.0                           | https://streamlit.io                                                 |
| tzdata                    | 2026.3       | Apache-2.0                           | https://github.com/python/tzdata                                     |
| packaging                 | 26.3         | Apache-2.0 OR BSD-2-Clause           | https://github.com/pypa/packaging                                    |
| Flask-SQLAlchemy          | 3.1.1        | BSD License                          | https://flask-sqlalchemy.palletsprojects.com                         |
| Jinja2                    | 3.1.6        | BSD License                          | https://github.com/pallets/jinja/                                    |
| altair                    | 6.2.2        | BSD License                          | https://github.com/vega/altair                                       |
| amqp                      | 5.3.1        | BSD License                          | http://github.com/celery/py-amqp                                     |
| asgiref                   | 3.12.1       | BSD License                          | https://github.com/django/asgiref/                                   |
| billiard                  | 4.2.4        | BSD License                          | https://github.com/celery/billiard                                   |
| click-plugins             | 1.1.1.2      | BSD License                          | https://github.com/click-contrib/click-plugins                       |
| contourpy                 | 1.3.2        | BSD License                          | https://github.com/contourpy/contourpy                               |
| cycler                    | 0.12.1       | BSD License                          | https://matplotlib.org/cycler/                                       |
| httpx                     | 0.28.1       | BSD License                          | https://github.com/encode/httpx                                      |
| itsdangerous              | 2.2.0        | BSD License                          | https://github.com/pallets/itsdangerous/                             |
| kiwisolver                | 1.5.1        | BSD License                          | https://github.com/nucleic/kiwi                                      |
| numpy                     | 2.2.6        | BSD License                          | https://numpy.org                                                    |
| pandas                    | 2.3.3        | BSD License                          | https://pandas.pydata.org                                            |
| prompt_toolkit            | 3.0.53       | BSD License                          | https://github.com/prompt-toolkit/python-prompt-toolkit              |
| sqlparse                  | 0.6.0        | BSD License                          | https://github.com/andialbrecht/sqlparse                             |
| vine                      | 5.1.0        | BSD License                          | https://github.com/celery/vine                                       |
| Pygments                  | 2.21.0       | BSD-2-Clause                         | https://pygments.org                                                 |
| Django                    | 5.2.17       | BSD-3-Clause                         | https://www.djangoproject.com/                                       |
| Flask                     | 3.1.3        | BSD-3-Clause                         | https://github.com/pallets/flask/                                    |
| MarkupSafe                | 3.0.3        | BSD-3-Clause                         | https://github.com/pallets/markupsafe/                               |
| Werkzeug                  | 3.1.8        | BSD-3-Clause                         | https://github.com/pallets/werkzeug/                                 |
| celery                    | 5.6.3        | BSD-3-Clause                         | https://docs.celeryq.dev/                                            |
| click                     | 8.5.0        | BSD-3-Clause                         | https://github.com/pallets/click/                                    |
| httpcore                  | 1.0.9        | BSD-3-Clause                         | https://www.encode.io/httpcore/                                      |
| idna                      | 3.19         | BSD-3-Clause                         | https://github.com/kjd/idna                                          |
| kombu                     | 5.6.2        | BSD-3-Clause                         | https://kombu.readthedocs.io                                         |
| python-dotenv             | 1.2.3        | BSD-3-Clause                         | https://github.com/theskumar/python-dotenv                           |
| starlette                 | 1.6.0        | BSD-3-Clause                         | https://github.com/Kludex/starlette                                  |
| uvicorn                   | 0.52.4       | BSD-3-Clause                         | https://uvicorn.dev/                                                 |
| websockets                | 16.1.1       | BSD-3-Clause                         | https://github.com/python-websockets/websockets                      |
| Mako                      | 1.4.1        | MIT                                  | https://www.makotemplates.org/                                       |
| SQLAlchemy                | 2.0.52       | MIT                                  | https://www.sqlalchemy.org                                           |
| alembic                   | 1.19.2       | MIT                                  | https://alembic.sqlalchemy.org                                       |
| annotated-doc             | 0.0.5        | MIT                                  | https://github.com/fastapi/annotated-doc                             |
| annotated-types           | 0.8.0        | MIT                                  | https://github.com/annotated-types/annotated-types                   |
| anyio                     | 4.15.1       | MIT                                  | https://anyio.readthedocs.io/en/stable/versionhistory.html           |
| attrs                     | 26.1.0       | MIT                                  | https://www.attrs.org/en/stable/changelog.html                       |
| charset-normalizer        | 3.5.1        | MIT                                  | https://github.com/jawah/charset_normalizer/blob/master/CHANGELOG.md |
| click-repl                | 0.3.0        | MIT                                  | https://github.com/untitaker/click-repl                              |
| fastapi                   | 0.141.1      | MIT                                  | https://github.com/fastapi/fastapi                                   |
| fonttools                 | 4.64.0       | MIT                                  | http://github.com/fonttools/fonttools                                |
| httptools                 | 0.8.0        | MIT                                  | https://github.com/MagicStack/httptools                              |
| iniconfig                 | 2.3.0        | MIT                                  | https://github.com/pytest-dev/iniconfig                              |
| jsonschema                | 4.26.0       | MIT                                  | https://github.com/python-jsonschema/jsonschema                      |
| jsonschema-specifications | 2025.9.1     | MIT                                  | https://github.com/python-jsonschema/jsonschema-specifications       |
| narwhals                  | 2.26.0       | MIT                                  | https://github.com/narwhals-dev/narwhals                             |
| pydantic                  | 2.13.5       | MIT                                  | https://github.com/pydantic/pydantic                                 |
| pydantic-settings         | 2.15.0       | MIT                                  | https://github.com/pydantic/pydantic-settings                        |
| pydantic_core             | 2.46.5       | MIT                                  | https://github.com/pydantic                                          |
| pyparsing                 | 3.3.2        | MIT                                  | https://github.com/pyparsing/pyparsing/                              |
| pytest                    | 9.1.1        | MIT                                  | https://docs.pytest.org/en/latest/                                   |
| redis                     | 6.4.0        | MIT                                  | https://github.com/redis/redis-py                                    |
| referencing               | 0.37.0       | MIT                                  | https://github.com/python-jsonschema/referencing                     |
| rpds-py                   | 0.30.0       | MIT                                  | https://github.com/crate-py/rpds                                     |
| typing-inspection         | 0.4.4        | MIT                                  | https://github.com/pydantic/typing-inspection                        |
| tzlocal                   | 5.4.4        | MIT                                  | https://github.com/regebro/tzlocal/blob/master/CHANGES.txt           |
| urllib3                   | 2.7.0        | MIT                                  | https://github.com/urllib3/urllib3/blob/main/CHANGES.rst             |
| greenlet                  | 3.5.5        | MIT AND PSF-2.0                      | https://greenlet.readthedocs.io                                      |
| blinker                   | 1.9.0        | MIT License                          | https://github.com/pallets-eco/blinker/                              |
| click-didyoumean          | 0.3.1        | MIT License                          | https://github.com/click-contrib/click-didyoumean                    |
| exceptiongroup            | 1.3.1        | MIT License                          | https://github.com/agronholm/exceptiongroup/blob/main/CHANGES.rst    |
| h11                       | 0.16.0       | MIT License                          | https://github.com/python-hyper/h11                                  |
| pluggy                    | 1.6.0        | MIT License                          | UNKNOWN                                                              |
| pytz                      | 2026.3.post1 | MIT License                          | http://pythonhosted.org/pytz                                         |
| six                       | 1.17.0       | MIT License                          | https://github.com/benjaminp/six                                     |
| toml                      | 0.10.2       | MIT License                          | https://github.com/uiri/toml                                         |
| pillow                    | 12.3.0       | MIT-CMU                              | https://python-pillow.github.io                                      |
| certifi                   | 2026.7.22    | Mozilla Public License 2.0 (MPL 2.0) | https://github.com/certifi/python-certifi                            |
| typing_extensions         | 4.16.0       | PSF-2.0                              | https://github.com/python/typing_extensions                          |
| matplotlib                | 3.10.9       | Python Software Foundation License   | https://matplotlib.org                                               |
