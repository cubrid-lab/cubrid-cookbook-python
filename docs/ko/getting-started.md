# 시작하기 (한국어)

> 🌐 [GETTING_STARTED.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/GETTING_STARTED.md)의 사이트 번역입니다. 영어 원문이 표준이며, 페이지 번역은 경고 수준의 동기화 규칙을 따릅니다.

세 가지 경로 — 5분 첫 쿼리부터 자연어 MCP 세션까지. 모든 것은 PyPI에서 설치됩니다 — git 체크아웃도, C 컴파일러도 필요 없습니다.

CUBRID가 처음이라면 초보자 튜토리얼 [처음 만드는 CUBRID 데이터베이스](first-cubrid.md)부터 시작하세요. 실습 환경과 연결 설정을 설명하고 한 단계씩 진행합니다. 이 페이지는 경로를 고르고, 전체 체크아웃을 검증하고, 예전 실습 환경을 복구하기 위한 것입니다.

## 0. CUBRID 시작 (모든 경로 공통)

```bash
docker compose up -d        # localhost:33000의 CUBRID 11.2, 데이터베이스 testdb
```

첫 시작 시 준비까지 최대 1분 걸립니다:

```bash
docker exec cubrid-cookbook bash -lc "csql -u dba testdb -c 'SELECT 1;'"
```

### 2026년 10월 실습 환경 수정 전에 만든 실습 환경

이제 `docker-compose.yml`은 데이터베이스를 이름 있는 볼륨에 보관하고, 컨테이너에
고정된 호스트 이름을 줍니다(#385). 이전 파일로 시작한 실습 환경은 새 파일이 컨테이너를
처음 다시 만들 때 열리지 않습니다. CUBRID가 이전 컨테이너의 호스트 이름을 기록해 두었기
때문입니다(`-353 Failed to connect to database server`). 데이터는 그대로 남아 있으니,
저장소 폴더에서 아래와 같이 복구하세요. **데이터를 지우는 `docker compose down -v`는
실행하지 마세요.** 필요한 데이터가 있다면 먼저 따로 복사해 두세요.

`CUBRID_VERSION` 없이(기본값인 CUBRID 11.2로) 시작했다면, 데이터베이스가 새 호스트
이름을 가리키게 하고 다시 시작합니다.

```bash
docker compose up -d
docker compose exec -T -u cubrid cubrid sh -c 'sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1cubrid-cookbook/" "$CUBRID_DATABASES/databases.txt"'
docker compose restart cubrid
python3 scripts/wait_for_cubrid.py
```

`CUBRID_VERSION=11.4`로 시작했다면, 데이터베이스가 이름 없는 볼륨에 있습니다. 저장소를
업데이트하기 전에 그 볼륨을 기록하고 실습 환경을 멈추세요.

```bash
OLD=$(docker inspect cubrid-cookbook --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker compose stop
```

그다음 저장소를 업데이트하고(`git pull`), 데이터베이스를 새 이름 있는 볼륨에 복사한 뒤
호스트 이름을 고치고 실습 환경을 시작합니다.

```bash
CUBRID_VERSION=11.4 docker compose create
NEW=$(docker inspect cubrid-cookbook --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker run --rm -v "$OLD":/from:ro -v "$NEW":/to --entrypoint sh cubrid/cubrid:11.4 -c 'cp -a /from/. /to/ && sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1cubrid-cookbook/" /to/databases.txt && chown cubrid:cubrid /to/databases.txt'
CUBRID_VERSION=11.4 docker compose up -d
python3 scripts/wait_for_cubrid.py
```

데이터가 돌아온 것을 확인한 뒤 `docker volume rm "$OLD"`로 이전 사본을 지우세요.

## 1. 5분 만에 첫 쿼리 (pycubrid)

```bash
pip install pycubrid
python fundamentals/pycubrid/01_connect.py
```

기대 출력은 CI가 CUBRID 11.2와 11.4에서 검증합니다 — `fundamentals/pycubrid/expected/01_connect.expected`와 비교해 보세요. 여기서부터 `fundamentals/`가 CRUD, 트랜잭션, 파라미터화 쿼리, 컬렉션, LOB, 윈도우 함수를 안내합니다 — `expected/` 폴더가 있는 모든 디렉터리는 `make verify`로 검증됩니다.

## 2. ORM과 애플리케이션 템플릿 (sqlalchemy-cubrid)

```bash
pip install 'sqlalchemy-cubrid[pycubrid]'   # SQLAlchemy 2.x와 pycubrid를 끌어옴
python fundamentals/sqlalchemy/01_connect_and_session.py
```

프로덕션형 시작점은 `templates/`에 있습니다 — FastAPI 서비스, Flask 앱, Django 앱, Streamlit 대시보드, Celery 비동기 워커, pandas 배치 ETL, AI 에이전트 예제(`templates/ai-agent`: 에이전트 상태, MCP 도구 체인, RAG 메타데이터). 대시보드는 원커맨드 데모입니다:

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

Python 3.11 이상의 가상 환경을 사용하세요:

```bash
python3 -m venv .venv && source .venv/bin/activate   # Python 3.11 이상
make up                       # CUBRID를 시작하고 준비될 때까지 대기
make deps                     # 드라이버, pytest, 골든 기반 모든 예제의 requirements
make verify                   # 골든 기반 모든 예제를 로컬 CUBRID에 대해 실행
```

`make deps`는 한 번의 pip 호출로 모두 설치하며 `PIP_CONSTRAINT`를 따릅니다. `make verify`는 예제 요구 패키지가 빠져 있으면 "run `make deps` first"를 출력하고 바로 멈추며, 스크립트마다 `VERIFY_TIMEOUT`초(기본 60)로 실행 시간을 제한하고, 결과를 통과·불일치(mismatch)·실행 오류·타임아웃·정규화/읽기 오류·건너뜀으로 구분해 보고합니다.

## 다음 단계

| 목표 | 시작 위치 |
|---|---|
| 복사-수정형 시작점 | `templates/` |
| JDBC→Python 마이그레이션 | `migration/java-to-python/` |
| 성능 패턴 | `performance/` |
| CUBRID의 알려진 특성 | `pitfalls/`, `KNOWN_ISSUES.md` |
| 지원 버전 | `SUPPORT_MATRIX.md` |
