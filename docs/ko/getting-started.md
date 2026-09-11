# 시작하기 (한국어)

> 🌐 [GETTING_STARTED.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/GETTING_STARTED.md)의 사이트 번역입니다. 영어 원문이 표준이며, 페이지 번역은 경고 수준의 동기화 규칙을 따릅니다.

세 가지 경로 — 5분 첫 쿼리부터 자연어 MCP 세션까지. 모든 것은 PyPI에서 설치됩니다 — git 체크아웃도, C 컴파일러도 필요 없습니다.

## 0. CUBRID 시작 (모든 경로 공통)

```bash
docker compose up -d        # localhost:33000의 CUBRID 11.2, 데이터베이스 testdb
```

첫 시작 시 준비까지 최대 1분 걸립니다:

```bash
docker exec cubrid-cookbook bash -lc "csql -u dba testdb -c 'SELECT 1;'"
```

## 1. 5분 만에 첫 쿼리 (pycubrid)

```bash
pip install pycubrid
python fundamentals/pycubrid/01_connect.py
```

기대 출력은 CI가 CUBRID 11.2와 11.4에서 검증합니다 — `fundamentals/pycubrid/expected/01_connect.expected`와 비교해 보세요. 여기서부터 `fundamentals/`가 CRUD, 트랜잭션, 파라미터화 쿼리, 컬렉션, LOB, 윈도우 함수를 안내합니다 — `expected/` 폴더가 있는 모든 디렉터리는 `make verify`로 검증됩니다.

## 2. ORM과 애플리케이션 템플릿 (sqlalchemy-cubrid)

```bash
pip install sqlalchemy-cubrid   # SQLAlchemy 2.x를 끌어옴
python fundamentals/sqlalchemy/01_connect_and_session.py
```

프로덕션형 시작점은 `templates/`에 있습니다 — FastAPI 서비스, Flask 앱, Django 앱, Streamlit 대시보드, Celery 비동기 워커, pandas 배치 ETL. 대시보드는 원커맨드 데모입니다:

```bash
cd templates/dashboard
docker compose up -d           # CUBRID 11.4 + Streamlit at http://localhost:8501
```

## 3. 데이터베이스 위의 자연어 (cubrid-mcp-server)

```bash
uvx cubrid-mcp-server          # stdio MCP 서버; CUBRID_* 환경 변수 필요
```

Claude Desktop / Claude Code / Cursor 설정 블록은 [cubrid-mcp-server README](https://github.com/cubrid-lab/cubrid-mcp-server#mcp-client-integration)에 있습니다. 연결되면 이렇게 물어보세요:

1. "이 데이터베이스에 어떤 테이블이 있어?" → `all_table_names`
2. "`cookbook_sales` 구조 보여줘" → `describe_table`
3. "매출 상위 5개 상품은?" → `execute_query` (읽기 전용)
4. "orders 테이블 지워줘" → 읽기 전용 화이트리스트가 **거부** (이 거부가 바로 기능입니다)

## 전체 체크아웃 검증

```bash
pip install pycubrid sqlalchemy sqlalchemy-cubrid
make verify                   # 골든 기반 모든 예제를 로컬 CUBRID에 대해 실행
```

## 다음 단계

| 목표 | 시작 위치 |
|---|---|
| 복사-수정형 시작점 | `templates/` |
| JDBC→Python 마이그레이션 | `migration/java-to-python/` |
| 성능 패턴 | `performance/` |
| CUBRID의 알려진 특성 | `pitfalls/`, `KNOWN_ISSUES.md` |
| 지원 버전 | `SUPPORT_MATRIX.md` |
