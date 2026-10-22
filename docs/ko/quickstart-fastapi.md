# FastAPI + CUBRID 빠른 시작

> 🌐 [quickstart/5min-fastapi/README.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/5min-fastapi/README.md)의 한국어 학습 경로입니다. 영어 원문이 표준이며, 명령과 출력은 원문과 같습니다.

항목을 CUBRID에 저장하는 작은 웹 API입니다. Docker로 내 컴퓨터에 연습용
데이터베이스를 띄우고, API를 실행하고, HTTP 요청으로 항목을 만들고 다시 읽은 뒤,
멈추고 정리합니다. 필요한 내용은 모두 이 페이지에 있습니다.

Docker를 설치하고 이미지를 내려받은 뒤라면 5분 정도 걸립니다. 처음 내려받고
빌드할 때는 인터넷 속도에 따라 더 걸릴 수 있습니다. CUBRID 자체가 처음이라면
[처음 만드는 CUBRID 데이터베이스 (Python)](first-cubrid.md)를 먼저 해 보세요.
데이터베이스, 커넥터, 트랜잭션을 설명합니다.

## 필요한 것

- `bash`나 `zsh`를 쓰는 Linux 또는 macOS. Windows에서는 WSL 2 터미널을 쓰세요.
- Compose v2가 포함된 [Docker](https://docs.docker.com/get-docker/):
  `docker compose version`이 버전을 출력해야 합니다.
- `git`과 `curl`.
- Python 3.11 이상은 아래의 방법 B(API를 내 컴퓨터에서 실행)와 오프라인 테스트에만
  필요합니다. 방법 A는 내 컴퓨터에 Python이 없어도 됩니다.

CUBRID 이미지는 x86_64(`linux/amd64`)용으로 배포됩니다. Apple Silicon Mac에서는
Docker가 에뮬레이션으로 실행하며, 이 페이지는 Linux x86_64에서 확인했습니다.

## 1. 코드 받기

프로젝트를 두는 폴더에서 실행하세요.

```bash
git clone https://github.com/cubrid-lab/cubrid-cookbook-python.git
cd cubrid-cookbook-python
cd quickstart/5min-fastapi
```

이 페이지의 이후 명령은 모두 이 `quickstart/5min-fastapi` 폴더에서 실행합니다.
새 터미널을 열었다면 먼저 이 폴더로 `cd` 하세요.

## 2. 데이터베이스와 API 시작

방법을 **하나만** 고르세요. 두 방법 모두 API를 `http://localhost:8000`에서
제공하므로, 둘을 동시에 실행하면 안 됩니다.

| | A. 모두 Docker에서 (권장) | B. API를 내 컴퓨터에서 |
|---|---|---|
| 데이터베이스 | 컨테이너 `cubrid` | 컨테이너 `cubrid` |
| API | 컨테이너 `api` | 터미널에서 Python venv로 실행하는 `uvicorn` |
| 이럴 때 | 동작하는 모습만 보고 싶을 때 | `app.py`를 고치고 다시 불러오고 싶을 때 |

### A. 모두 Docker에서 (권장)

```bash
docker compose up -d --build --wait
```

`Dockerfile`로 API 이미지를 빌드하고, 데이터베이스를 시작해 상태 검사(health
check)를 통과할 때까지 기다린 다음, API를 시작해 응답할 때까지 기다립니다.

**확인.** `docker compose up`이 오류 없이 끝나고, `docker compose ps`가 두 서비스를
모두 `healthy`로 보여 줍니다.

```text
NAME                    IMAGE                COMMAND                  SERVICE   CREATED          STATUS                    PORTS
5min-fastapi-api-1      5min-fastapi-api     "uvicorn app:app --h…"   api       24 seconds ago   Up 6 seconds (healthy)    127.0.0.1:8000->8000/tcp
5min-fastapi-cubrid-1   cubrid/cubrid:11.2   "/entrypoint.sh"         cubrid    25 seconds ago   Up 22 seconds (healthy)   127.0.0.1:33000->33000/tcp
```

시간 값은 컴퓨터마다 다릅니다. Docker 안에서 API는 Compose **서비스 이름**인
`cubrid`로 데이터베이스에 접속합니다. `docker-compose.yml`이 `api` 컨테이너에
`CUBRID_HOST=cubrid`를 설정하기 때문입니다. 내 컴퓨터에서는 두 서비스 모두
`localhost`에 있고, 포트는 `PORTS` 열에 나온 대로입니다.

### B. API는 내 컴퓨터에서, 데이터베이스는 Docker에서

방법 A를 이미 시작했다면 먼저 포트 8000을 쓰고 있는 API 컨테이너를 멈추세요:
`docker compose stop api`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
docker compose up -d --wait cubrid
uvicorn app:app --reload
```

- venv는 API의 패키지(`fastapi`, `uvicorn`, `pycubrid`)를 이 폴더 안에만
  설치합니다. 새 터미널에서는 `source .venv/bin/activate`를 다시 실행하세요.
- `docker compose up -d --wait cubrid`는 데이터베이스**만** 시작하고 상태 검사를
  통과할 때까지 기다립니다.
- `uvicorn app:app --reload`는 이 터미널에서 API를 실행하고, `app.py`를 저장하면
  다시 시작합니다. 이때 API는 내 컴퓨터에서 돌기 때문에 Docker가 데이터베이스용으로
  공개한 포트인 `localhost:33000`에 접속합니다. `CUBRID_HOST`를 설정하지 않으면
  기본값이 `localhost`입니다.

**확인.** Uvicorn이 계속 실행되면서, 감시하는 폴더를 알리는 줄 다음에 이렇게 출력합니다.

```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [2993868] using StatReload
INFO:     Started server process [2993873]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

프로세스 번호는 컴퓨터마다 다릅니다.

이 터미널은 그대로 두고, 3단계는 같은 폴더에서 두 번째 터미널로 진행하세요.

## 3. 항목을 만들고 다시 읽기

API는 항목을 자기 전용 테이블 `cookbook_quickstart_items`에 저장하며, 이 테이블이
없으면 시작할 때 만듭니다. 항목에는 텍스트 `val`이 있고, `id`는 데이터베이스가 정합니다.

먼저 API가 데이터베이스에 닿는지 물어봅니다. `GET /health`는 새 연결에서
`SELECT 1 FROM db_root`를 실행합니다.

```bash
curl -sS localhost:8000/health
```

**확인.**

```text
{"status":"ok","database":"ok"}
```

데이터베이스가 응답하지 않으면 같은 요청이 HTTP 상태 `503`과
`{"status":"error","database":"unavailable"}`를 돌려주며, 오류 세부 내용은 보내지 않습니다.

항목 하나를 만듭니다.

```bash
curl -sS -X POST localhost:8000/items -H 'Content-Type: application/json' -d '{"val": "hello from the quickstart"}'
```

**확인.** 처음 실행하면:

```text
{"val":"hello from the quickstart","id":1}
```

그 `id`로 다시 읽습니다.

```bash
curl -sS localhost:8000/items/1
```

```text
{"val":"hello from the quickstart","id":1}
```

`curl -sS localhost:8000/items`는 모든 항목을 보여 줍니다. `id`는 데이터베이스의
`AUTO_INCREMENT` 값이라서 새 테이블에서만 `1`입니다. 테이블은 지울 때까지(4단계)
행을 유지하므로, 나중에 다시 실행하면 `"id":2`처럼 다음 번호가 나옵니다. 그때는 그
`id`로 읽으세요. 브라우저에서 `http://localhost:8000/docs`를 열면 같은 API를
대화형 문서로 볼 수 있습니다.

## 4. 멈추기, 다시 실행하기, 정리하기

**API 멈추기.**

- 방법 A: `docker compose stop`으로 두 컨테이너를 멈춥니다.
- 방법 B: Uvicorn 터미널에서 Ctrl-C를 누른 뒤 `docker compose stop`으로
  데이터베이스를 멈춥니다. venv에서 나오려면 `deactivate`를 실행하세요.

**다시 실행하기.** 방법 A: `docker compose up -d --build --wait`. 방법 B:
`docker compose up -d --wait cubrid`를 실행한 뒤, venv를 활성화한 상태에서
`uvicorn app:app --reload`. 만든 항목은 그대로 남아 있습니다.

**빠른 시작의 테이블만 지우기.** 데이터베이스가 실행 중일 때:

```bash
docker compose exec -T cubrid csql -u dba testdb -c "DROP TABLE IF EXISTS cookbook_quickstart_items"
```

걸린 시간과 함께 `Execute OK.`와 `Committed.`가 출력됩니다. API는 다음에 시작할 때
테이블을 다시 만듭니다.

**컨테이너 지우기.** 얼마나 지울지 고르세요.

| 명령 | 컨테이너 | 데이터 |
|------|----------|--------|
| `docker compose stop` | 멈춤. `docker compose start`로 다시 시작 | 남음 |
| `docker compose down` | 삭제 | 이 빠른 시작의 Docker 볼륨에 남음. 다음 `up`에서 되살아남 |
| `docker compose down -v` | 삭제 | `testdb` 데이터베이스까지 포함해 **삭제** |

이 명령들은 폴더 이름을 딴 이 폴더의 Compose 프로젝트 `5min-fastapi`에만 작용합니다.
두 컨테이너, 네트워크, 그리고 `-v`를 붙이면 두 볼륨(`5min-fastapi_cubrid_data`,
`5min-fastapi_cubrid_databases`)입니다. 다른 컨테이너는 건드리지 않습니다. 방법 B의
venv는 `.venv` 폴더이며, `rm -rf .venv`로 지웁니다.

**포트 33000은 함께 씁니다.** 이 빠른 시작,
[SQLAlchemy 빠른 시작](quickstart-sqlalchemy.md), 저장소 루트의 실습 환경
(`cubrid-cookbook` 컨테이너)은 모두 데이터베이스를 `127.0.0.1:33000`에 공개합니다.
각각 데이터가 따로인 별개의 Compose 프로젝트라서 한 번에 하나만 실행할 수 있습니다.
다른 것으로 바꾸기 전에, 떠나는 쪽 폴더에서 `docker compose stop`을 실행하세요.

## 문제가 생기면

- **`docker: command not found`가 나오거나 `docker compose version`이 실패할 때:**
  Compose v2가 포함된 Docker를 설치하고([Get Docker](https://docs.docker.com/get-docker/)),
  Docker 데몬이 실행 중인지 확인하세요.
- **`Bind for 127.0.0.1:33000 failed: port is already allocated`** (또는 `8000`):
  다른 무언가가 그 포트를 쓰고 있습니다. `docker ps --filter publish=33000`
  (또는 `publish=8000`)으로 찾으세요. 이 저장소의 실습 환경이라면 그 폴더에서
  `docker compose stop`으로 멈추고, 아니라면 직접 시작한 프로그램을 멈추세요.
  내가 만들지 않은 컨테이너나 볼륨은 지우지 마세요. 시작에 실패해도 이 프로젝트의
  컨테이너가 남으므로, 다시 시도하기 전에 이 폴더에서 `docker compose down`을 실행하세요.
- **Uvicorn이 `[Errno 98] error while attempting to bind on address
  ('127.0.0.1', 8000): [errno 98] address already in use`를 출력하고 멈출 때** (방법 B):
  방법 A의 API 컨테이너나 다른 프로그램이 포트 8000을 쓰고 있습니다. 이 폴더에서
  `docker compose stop api`를 실행하거나 그 프로그램을 멈추세요.
- **데이터베이스가 healthy가 되지 않을 때** (`docker compose up --wait`가
  `unhealthy`를 보고하거나 오래 기다릴 때): 처음 시작할 때 `testdb`를 만드느라 1분쯤
  걸릴 수 있습니다. 원인은 `docker compose logs cubrid`로 확인하세요.
- **`ModuleNotFoundError`나 `uvicorn: command not found`** (방법 B): venv가
  활성화되지 않았습니다. `source .venv/bin/activate`를 실행한 뒤
  `python -m pip install -r requirements.txt`를 다시 실행하세요.
- **Uvicorn이 `pycubrid.exceptions.OperationalError: failed to connect to CUBRID broker`와
  `Application startup failed`를 출력하고 멈출 때**: `localhost:33000`에서 응답하는
  데이터베이스가 없습니다. `docker compose up -d --wait cubrid`로 시작하세요.
- **데이터베이스 오류나 로그인 오류**: 앱은 데이터베이스 `testdb`에 `dba`, 빈
  비밀번호로 접속하며, 이 Compose 파일이 만드는 설정과 같습니다. 포트 33000의 다른
  CUBRID 서버는 설정이 다릅니다. 위에서 설명한 대로 멈추세요.

더 많은 해결 방법: [CUBRID 특이점과 함정](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/pitfalls/README.md),
[알려진 문제](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/KNOWN_ISSUES.md).

> **내 컴퓨터 전용입니다.** 실습 환경의 `dba` 계정에는 비밀번호가 없어서, 두 포트
> 모두 `127.0.0.1`에서만 접속을 받습니다. 함께 쓰는 서버나 원격 서버에는 이 설정을
> 절대 쓰지 마세요.

## 앱의 동작 방식

`app.py`는 FastAPI의 lifespan 시작 훅에서 테이블을 만듭니다. 동기 요청 핸들러를
포함해, 블로킹되는 데이터베이스 작업은 스레드에서 실행합니다. 데이터베이스 작업마다
성공하면 커밋하고, 실패하면 롤백하며, 커서와 연결을 닫습니다. SQL의 `?`는 매개변수
자리표시자로, pycubrid가 각 값을 안전하게 이스케이프한 리터럴로 문장에 넣습니다.

## 데이터베이스 없이 테스트하기

방법 B의 venv를 활성화한 상태에서:

```bash
python -m pip install -r requirements.txt pytest httpx
python -m pytest tests -q
```

테스트는 DB-API 연결을 가짜로 바꾸고, 호스트 설정, 시작, CRUD와 `/health` 응답,
데이터베이스 오류 뒤의 자원 정리를 확인합니다. `tests/test_live.py`는 데이터베이스가
필요하므로 여기서는 건너뜁니다(다음 절).

## 데이터베이스로 테스트하기

`tests/test_live.py`는 같은 앱을 실행 중인 CUBRID에 연결해 돌리고, 각 응답을 별도
연결로 읽은 테이블 내용과 비교합니다. `/health`(`200`, 데이터베이스에 닿지 않으면
`503`), 항목 만들기, `id`와 목록으로 읽기, 없는 `id`의 `404`, 잘못된 본문의 `422`와
행이 쓰이지 않았는지, 거부된 INSERT가 행을 남기지 않는지를 확인합니다. 각 테스트는
자기만의 무작위 `live-qs-` 표식으로 시작하는 `val`의 행만 쓰고 끝나면 그 행을 지우므로,
내 항목은 건드리지 않고 다시 실행할 수 있습니다.

2단계의 데이터베이스가 실행 중이고 venv가 활성화된 상태에서:

```bash
CUBRID_TEST_URL=cubrid+pycubrid://dba@localhost:33000/testdb python -m pytest tests/test_live.py -v
```

앱은 항상 포트 `33000`의 데이터베이스 `testdb`에 접속하므로 URL에서는 호스트만 바꿀 수
있습니다. `CUBRID_TEST_URL`이 없으면 이 테스트는 건너뛰고, 설정했는데 데이터베이스가
응답하지 않으면 실패합니다. 저장소 루트의 `make verify-quickstart`(전체 `make verify`에도 포함)는
`localhost:33000`에 대해 `CUBRID_LIVE_GATE=1`로 실행해 건너뜀도 실패로 처리하고, JUnit
보고서와 요약을 `.live-evidence/quickstart/`에 씁니다.

## 다음 단계

- **프로덕션 형태의 API** (SQLAlchemy로 연결 재사용):
  [FastAPI 서비스 템플릿](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/templates/api-service-fastapi/README.md).
- **핵심 데이터베이스 패턴** (CRUD, 트랜잭션, 오류 처리):
  [기초 예제](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/fundamentals/README.md).
- **웹 프레임워크 없이 SQLAlchemy**: [SQLAlchemy 빠른 시작](quickstart-sqlalchemy.md).
