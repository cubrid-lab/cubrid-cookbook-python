# SQLAlchemy + CUBRID 빠른 시작

> 🌐 [quickstart/5min-sqlalchemy/README.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/5min-sqlalchemy/README.md)의 한국어 학습 경로입니다. 영어 원문이 표준이며, 명령과 출력은 원문과 같습니다.

SQLAlchemy로 CUBRID에 행을 쓰고, 읽고, 고치고, 지우는 Python 스크립트 하나입니다.
먼저 SQLAlchemy Core(SQL 표현식)로, 다음에는 ORM(테이블에 연결한 Python 클래스)으로
합니다. Docker로 내 컴퓨터에 연습용 데이터베이스를 띄우고, 스크립트를 실행하고,
정리합니다. 필요한 내용은 모두 이 페이지에 있습니다.

Docker와 Python을 설치하고 데이터베이스 이미지를 내려받은 뒤라면 5분 정도 걸립니다.
처음 내려받을 때는 인터넷 속도에 따라 더 걸릴 수 있습니다. CUBRID 자체가 처음이라면
[처음 만드는 CUBRID 데이터베이스 (Python)](first-cubrid.md)를 먼저 해 보세요.
데이터베이스, 커넥터, 트랜잭션을 설명합니다.

## 필요한 것

- `bash`나 `zsh`를 쓰는 Linux 또는 macOS. Windows에서는 WSL 2 터미널을 쓰세요.
- Compose v2가 포함된 [Docker](https://docs.docker.com/get-docker/):
  `docker compose version`이 버전을 출력해야 합니다.
- 내 컴퓨터의 Python 3.11 이상: `python3 --version`. 스크립트는 내 컴퓨터에서
  실행되고, Docker에서는 데이터베이스만 실행됩니다.
- `git`.

CUBRID 이미지는 x86_64(`linux/amd64`)용으로 배포됩니다. Apple Silicon Mac에서는
Docker가 에뮬레이션으로 실행하며, 이 페이지는 Linux x86_64에서 확인했습니다.

## 1. 코드와 Python 환경 준비

프로젝트를 두는 폴더에서 실행하세요.

```bash
git clone https://github.com/cubrid-lab/cubrid-cookbook-python.git
cd cubrid-cookbook-python
cd quickstart/5min-sqlalchemy
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

이 페이지의 이후 명령은 모두 venv를 활성화한 상태로 이 `quickstart/5min-sqlalchemy`
폴더에서 실행합니다. venv는 패키지(`sqlalchemy`, `sqlalchemy-cubrid`, 드라이버
`pycubrid`)를 이 폴더 안에만 설치합니다. 새 터미널을 열었다면 이 폴더로 `cd` 하고
`source .venv/bin/activate`를 다시 실행하세요.

## 2. 데이터베이스 시작

```bash
docker compose up -d --wait
```

`docker-compose.yml`로 컨테이너 하나를 시작합니다. 이 컨테이너가 데이터베이스
`testdb`를 만들고, 명령은 상태 검사(컨테이너 안에서 실행하는 `SELECT 1`)를 통과할
때까지 기다립니다.

**확인.** `docker compose up`이 오류 없이 끝나고, `docker compose ps`가 데이터베이스를
`healthy`로 보여 줍니다.

```text
NAME                       IMAGE                COMMAND            SERVICE   CREATED          STATUS                    PORTS
5min-sqlalchemy-cubrid-1   cubrid/cubrid:11.2   "/entrypoint.sh"   cubrid    17 seconds ago   Up 16 seconds (healthy)   127.0.0.1:33000->33000/tcp
```

시간 값은 컴퓨터마다 다릅니다. 스크립트는 내 컴퓨터에서 돌기 때문에, Docker가
데이터베이스용으로 공개한 포트(`PORTS` 열)인 `localhost:33000`에 접속합니다.

## 3. 스크립트 실행

```bash
python app.py
```

**확인.** 예상 출력:

```text
=== SQLAlchemy Core CRUD ===
Core query result: [(1, 'core-sample', 'v1')]

=== SQLAlchemy ORM CRUD ===
ORM query result: 1 orm-sample

Done. Core and ORM CRUD completed successfully.
```

[`app.py`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/5min-sqlalchemy/app.py)가 한 일:

- URL `cubrid+pycubrid://dba@localhost:33000/testdb`로 접속합니다. `pycubrid`
  드라이버를 쓰는 SQLAlchemy `cubrid` 방언(dialect)으로, 사용자 `dba`와 빈
  비밀번호로 `localhost:33000`의 데이터베이스 `testdb`에 접속한다는 뜻입니다.
- 자기 전용 테이블 두 개 `cookbook_core_items`와 `cookbook_orm_items`를 만듭니다.
  Core 부분은 `core-sample` 행을 넣고 `(item_id, item_name, val)` 튜플로 다시 읽은
  뒤, 고치고 지웁니다. ORM 부분은 `CookbookOrmItem` 객체로 같은 일을 하고 그
  `item_id`와 `item_name`을 출력합니다.
- 끝날 때는 오류가 났더라도 두 테이블을 다시 지웁니다.

스크립트가 매번 두 테이블을 새로 만들기 때문에 id는 실행할 때마다 `1`이고,
`python app.py`를 바로 다시 실행해도 출력이 같습니다. 이 두 이름의 테이블이 이미
있으면 지우므로, 이 데이터베이스처럼 그 이름을 다른 용도로 쓰지 않는
데이터베이스에서만 실행하세요.

## 4. 멈추기, 다시 실행하기, 정리하기

스크립트는 테이블을 남기지 않습니다. 데이터베이스를 멈출 때는 얼마나 지울지 고르세요.

| 명령 | 컨테이너 | 데이터 |
|------|----------|--------|
| `docker compose stop` | 멈춤. `docker compose start`로 다시 시작 | 남음 |
| `docker compose down` | 삭제 | 이 빠른 시작의 Docker 볼륨에 남음. 다음 `docker compose up -d --wait`에서 되살아남 |
| `docker compose down -v` | 삭제 | `testdb` 데이터베이스까지 포함해 **삭제** |

나중에 다시 실행하려면 `docker compose up -d --wait`로 데이터베이스를 시작한 뒤
`python app.py`를 실행하세요.

이 명령들은 폴더 이름을 딴 이 폴더의 Compose 프로젝트 `5min-sqlalchemy`에만
작용합니다. 컨테이너, 네트워크, 그리고 `-v`를 붙이면 두 볼륨
(`5min-sqlalchemy_cubrid_data`, `5min-sqlalchemy_cubrid_databases`)입니다. 다른
컨테이너는 건드리지 않습니다. venv에서 나오려면 `deactivate`를, 지우려면
`rm -rf .venv`를 실행하세요.

**포트 33000은 함께 씁니다.** 이 빠른 시작, [FastAPI 빠른 시작](quickstart-fastapi.md),
저장소 루트의 실습 환경(루트 `docker-compose.yml`의 `cubrid` 서비스)은 모두 데이터베이스를
`127.0.0.1:33000`에 공개합니다. 각각 데이터가 따로인 별개의 Compose 프로젝트라서
한 번에 하나만 실행할 수 있습니다. 다른 것으로 바꾸기 전에, 떠나는 쪽 폴더에서
`docker compose stop`을 실행하세요.

## 문제가 생기면

- **`docker: command not found`가 나오거나 `docker compose version`이 실패할 때:**
  Compose v2가 포함된 Docker를 설치하고([Get Docker](https://docs.docker.com/get-docker/)),
  Docker 데몬이 실행 중인지 확인하세요.
- **`Bind for 127.0.0.1:33000 failed: port is already allocated`**: 다른 무언가가
  포트 33000을 쓰고 있습니다. `docker ps --filter publish=33000`으로 찾으세요. 이
  저장소의 실습 환경이라면 그 폴더에서 `docker compose stop`으로 멈추고, 아니라면
  직접 시작한 프로그램을 멈추세요. 내가 만들지 않은 컨테이너나 볼륨은 지우지 마세요.
  시작에 실패해도 이 프로젝트의 컨테이너가 남으므로, 다시 시도하기 전에 이 폴더에서
  `docker compose down`을 실행하세요.
- **데이터베이스가 healthy가 되지 않을 때** (`docker compose up --wait`가
  `unhealthy`를 보고하거나 오래 기다릴 때): 처음 시작할 때 `testdb`를 만드느라 1분쯤
  걸릴 수 있습니다. 원인은 `docker compose logs cubrid`로 확인하세요.
- **`ModuleNotFoundError: No module named 'sqlalchemy'`**나
  `Can't load plugin: sqlalchemy.dialects:cubrid.pycubrid`: venv가 활성화되지
  않았습니다. `source .venv/bin/activate`를 실행한 뒤
  `python -m pip install -r requirements.txt`를 다시 실행하세요.
- **`Database operation failed: (pycubrid.exceptions.OperationalError) failed
  to connect to CUBRID broker`** 다음에 `Cleanup failed:` 줄이 두 번 나올 때:
  `localhost:33000`에서 응답하는 데이터베이스가 없습니다. `docker compose up -d --wait`로
  시작하세요.
- **데이터베이스 오류나 로그인 오류**: 스크립트는 `testdb`에 `dba`, 빈 비밀번호로
  접속하며, 이 Compose 파일이 만드는 설정과 같습니다. 포트 33000의 다른 CUBRID
  서버는 설정이 다릅니다. 위에서 설명한 대로 멈추세요.
- **이전 Compose 파일에서 업데이트한 뒤 `-353 Failed to connect to database server`가
  나오면:** 이전 파일은 데이터베이스를 호스트 `cubrid-sqlalchemy`로 등록했고, 볼륨의 데이터베이스가
  아직 그 이름을 기록하고 있습니다. 데이터는 그대로이니 `localhost`를 가리키게 하고
  다시 시작하세요. 데이터를 지우는 `docker compose down -v`는 실행하지 마세요.

  ```bash
  docker compose up -d cubrid
  docker compose exec -T -u cubrid cubrid sh -c 'sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1localhost/" "$CUBRID_DATABASES/databases.txt"'
  docker compose restart cubrid
  docker compose up -d --wait
  ```

더 많은 해결 방법: [CUBRID 특이점과 함정](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/pitfalls/README.md),
[알려진 문제](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/KNOWN_ISSUES.md).

> **내 컴퓨터 전용입니다.** 실습 환경의 `dba` 계정에는 비밀번호가 없어서,
> 데이터베이스는 `127.0.0.1`에서만 접속을 받습니다. 함께 쓰는 서버나 원격 서버에는
> 이 설정을 절대 쓰지 마세요.

## 다음 단계

- **CUBRID에서 SQLAlchemy 더 익히기** (관계, 대량 삽입, upsert, 리플렉션, 컬렉션 타입):
  [SQLAlchemy 예제](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/fundamentals/sqlalchemy/README.md).
- **프로덕션 형태의 배치 작업** (pandas와 SQLAlchemy):
  [배치 ETL 템플릿](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/templates/batch-etl/README.md).
- **웹 API**: [FastAPI 빠른 시작](quickstart-fastapi.md).
