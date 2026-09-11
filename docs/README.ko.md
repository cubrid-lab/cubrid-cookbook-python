# CUBRID Python Cookbook (한국어)

> 🌐 Translated from [README.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/README.md) — 한국어는 심사 기간 동안 동기화가 **필수**입니다: README.md가 바뀌면 같은 PR에서 이 파일도 업데이트하세요 (`translation-sync` CI 검사, 보류 시 `translations-deferred` 라벨). English is canonical.


**CUBRID를 위한 프로덕션급 Python 예제 모음** — 첫 연결부터 프로덕션 API까지, 마이그레이션 가이드·성능 패턴·흔한 함정까지 함께 제공합니다.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/LICENSE)
[![CUBRID 11.2 | 11.4](https://img.shields.io/badge/CUBRID-11.2%20%7C%2011.4-green.svg)](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/SUPPORT_MATRIX.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
![pycubrid](https://img.shields.io/badge/pycubrid-%E2%89%A51.6.1-blue)
![sqlalchemy-cubrid](https://img.shields.io/badge/sqlalchemy--cubrid-%E2%89%A51.0-blue)
![status](https://img.shields.io/badge/status-active%20development-yellow)

---

## 시작하기

| 목표 | 바로 가기 | 소요 시간 |
|------|-----------|-----------|
| **5분 만에 시작** | [`quickstart/5min-fastapi/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/quickstart/5min-fastapi) | 5분 |
| **SQLAlchemy로 시작** | [`quickstart/5min-sqlalchemy/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/quickstart/5min-sqlalchemy) | 5분 |
| **Java에서 마이그레이션** | [`migration/java-to-python/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/migration/java-to-python) | 30분 |
| **프로덕션 API 구축** | [`templates/api-service-fastapi/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/templates/api-service-fastapi) | 15분 |

---

## 구성

### 퀵스타트

Docker로 CUBRID + FastAPI 앱을 5분 안에 띄웁니다.

```bash
cd quickstart/5min-fastapi
docker compose up -d
pip install -r requirements.txt
uvicorn app:app --reload
# http://localhost:8000/docs 접속
```

### 마이그레이션 가이드

Java JDBC → Python 마이그레이션을 실제 코드 나란히 비교로 제공합니다. 연결, CRUD(DB-API와 ORM), 트랜잭션, 배치 작업을 다룹니다.

> CUBRID의 JDBC 드라이버와 Python 드라이버는 동일한 CAS 프로토콜을 사용합니다 — 데이터 마이그레이션이 필요 없습니다.

### 프로덕션 템플릿

실제 애플리케이션의 복사-수정 출발점:

| 템플릿 | 용도 |
|--------|------|
| [`api-service-fastapi/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/templates/api-service-fastapi) | FastAPI + SQLAlchemy + Docker REST API (12개 레시피) |
| [`flask/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/templates/flask) | Flask + Flask-SQLAlchemy 패턴 (11개 레시피) |
| [`django/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/templates/django) | CUBRID 위의 최소 Django 앱 |
| [`async-worker/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/templates/async-worker) | Celery 백그라운드 작업 처리 |
| [`batch-etl/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/templates/batch-etl) | Pandas 데이터 파이프라인 |
| [`dashboard/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/templates/dashboard) | Streamlit 인터랙티브 대시보드 (`docker compose up` 원커맨드 데모) |

### 성능

벤치마크로 뒷받침된 최적화 패턴:

| 패턴 | 효과 |
|------|------|
| [Fetch 최적화](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/performance/fetch-optimization) | SELECT 1만 건: 96ms → 78ms (−19%) |
| [벌크 인서트](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/performance/bulk-insert) | COMMIT이 INSERT보다 7배 비싸다 — 쓰기는 배치로 |
| [커넥션 풀링](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/performance/connection-pooling) | 연결 재사용으로 건당 1.7ms 연결 비용 제거 |

### 함정 (Pitfalls)

실제 프로덕션 사고를 일으키는 7가지 반패턴 — 예약어, 오토커밋 차이, 커넥션 누수 등. [`pitfalls/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/pitfalls) 참고.

### 기초 (Fundamentals)

핵심 연산별 단계별 참조:

| 주제 | 위치 |
|------|------|
| [연결](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/connect) | 기본 연결, 메타데이터, 컨텍스트 매니저 |
| [CRUD](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/crud) | 파라미터를 사용한 INSERT/SELECT/UPDATE/DELETE |
| [트랜잭션](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/transactions) | 커밋, 롤백, 세이브포인트, 오토커밋 |
| [파라미터화 쿼리](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/parameterized-queries) | 안전한 파라미터 바인딩 (클라이언트 측 — 서버 측 prepare 아님) |
| [에러 처리](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/error-handling) | 예외 타입, 재시도 패턴 |
| [LOB 처리](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/lob-handling) | BLOB/CLOB 연산 |
| [ORM 기초](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/orm-basics) | SQLAlchemy 엔진, Core, ORM, 릴레이션십 |
| [pycubrid 드라이버](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/pycubrid) | 22개 DB-API 레시피: 커서, 윈도우 함수, 재귀 CTE, 페이지네이션, 타임존/ENUM |
| [SQLAlchemy 레시피](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/sqlalchemy) | SET/MULTISET/SEQUENCE 컬렉션 타입 포함 7개 |
| [Pandas](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/pandas) | 6개 레시피: read_sql, 청크 읽기, to_sql 적재 |
| [비동기 I/O](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/async) | pycubrid.aio와 SQLAlchemy 비동기 엔진 |
| [Alembic 마이그레이션](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/alembic) | CubridImpl로 프로그래밍 방식 마이그레이션 |
| [JSON 타입 CRUD](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/json) | 네이티브 JSON 컬럼, JSON_EXTRACT/UNQUOTE 패턴 |
| [격리 수준](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/fundamentals/isolation-levels) | MVCC 3단계, no-dirty-read 실증 |

---

## 프레임워크 맵

```
pycubrid (DB-API 2.0 드라이버)
├── 직접 사용 ─────── fundamentals/connect, crud, transactions, pycubrid
├── SQLAlchemy ────── fundamentals/orm-basics, sqlalchemy, quickstart/5min-sqlalchemy
├── FastAPI ───────── quickstart/5min-fastapi, templates/api-service-fastapi
├── Flask ─────────── templates/flask
├── Django ────────── templates/django
├── Celery ────────── templates/async-worker
├── Pandas ────────── fundamentals/pandas, templates/batch-etl
└── Streamlit ─────── templates/dashboard
```

## 연결 설정

모든 예제는 동일한 CUBRID 인스턴스에 연결합니다:

| 설정 | 값 |
|------|-----|
| 호스트 | `localhost` |
| 포트 | `33000` |
| 데이터베이스 | `testdb` |
| 사용자 | `dba` |
| 비밀번호 | *(비어 있음)* |

```python
# pycubrid (직접)
import pycubrid

conn = pycubrid.connect(host="localhost", port=33000, database="testdb", user="dba")

# SQLAlchemy
from sqlalchemy import create_engine

engine = create_engine("cubrid+pycubrid://dba@localhost:33000/testdb")
```

데이터베이스 기동:

```bash
docker compose up -d
```

## 관련 프로젝트

- [pycubrid](https://github.com/cubrid-lab/pycubrid) — CUBRID용 순수 Python DB-API 2.0 드라이버
- [sqlalchemy-cubrid](https://github.com/cubrid-lab/sqlalchemy-cubrid) — CUBRID용 SQLAlchemy 2.0 방언
- [cubrid-mcp-server](https://github.com/cubrid-lab/cubrid-mcp-server) — LLM 클라이언트용 MCP 서버
- [CUBRID](https://www.cubrid.org/) — CUBRID 데이터베이스

## 로드맵

계획된 추가 사항은 [`ROADMAP.md`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/ROADMAP.md)를 참고하세요. 생태계 전체 관점은 [CUBRID Labs Ecosystem Roadmap](https://github.com/cubrid-lab/.github/blob/main/ROADMAP.md)에서 볼 수 있습니다.

## 기여

PR 환영합니다! 각 예제는 자립적으로 실행 가능해야 합니다. [`CONTRIBUTING.md`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/CONTRIBUTING.md) 참고.

## 고지

> 이 프로젝트는 CUBRID 개발자 도구를 위한 독립 오픈소스 이니셔티브인 [CUBRID Lab](https://github.com/cubrid-lab)의 일부이며, CUBRID Corporation 또는 공식 CUBRID 프로젝트와 제휴·후원·보증 관계가 없습니다.

## 라이선스

[MIT](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/LICENSE)
