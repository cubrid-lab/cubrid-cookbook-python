# 처음 만드는 CUBRID 데이터베이스 (Python)

> 🌐 [quickstart/first-cubrid/README.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/README.md)의 한국어 학습 경로입니다. 영어 원문이 표준이며, 코드와 출력은 원문과 같습니다.

**CUBRID가 처음이라면 여기서 시작하세요.** Python 파일은 실행할 수 있지만
CUBRID는 써 본 적이 없는 분을 위한 튜토리얼입니다. 내 컴퓨터에 연습용
데이터베이스를 띄우고, Python에서 접속하고, 행 몇 개를 저장하고, `commit`과
`rollback`이 하는 일을 확인한 뒤 정리합니다. FastAPI, SQLAlchemy, 이 저장소의
기여자용 도구는 필요 없습니다.

준비물을 설치한 뒤라면 15분 정도 걸립니다. 처음에는 데이터베이스 이미지를
내려받느라 인터넷 속도에 따라 더 걸릴 수 있습니다.

## 1. 무엇을 설치하나요

두 가지는 서로 다릅니다.

- **CUBRID 데이터베이스 서버**: 데이터를 저장합니다. 여기서는 Docker 컨테이너
  안에서 돌아가는, 언제든 멈추거나 지울 수 있는 연습용 "실습 환경"입니다.
- **pycubrid (Python 커넥터)**: 실행 중인 서버와 대화하는 Python 패키지입니다.
  pycubrid를 설치해도 서버가 설치되거나 시작되지 않고, 데이터베이스도 만들어지지 않습니다.

접속하려면 Python이 서버에 대해 네 가지를 알아야 합니다.

| 설정 | 이 실습 환경의 값 | 뜻 |
|------|------------------|----|
| host | `localhost` | 서버가 도는 컴퓨터 (내 컴퓨터) |
| port | `33000` | 접속을 받아 주는 입구인 서버 **브로커**의 네트워크 포트 |
| database | `testdb` | 실습 환경이 처음 시작할 때 만드는 데이터베이스 |
| user / password | `dba` / 빈 값 | 실습 환경의 관리자 계정 |

> **내 컴퓨터 전용입니다.** 실습 환경의 `dba` 계정에는 비밀번호가 없어서,
> 실습 환경은 `127.0.0.1`에서만 접속을 받습니다. 내 컴퓨터 밖에서는 접속할 수
> 없습니다. 함께 쓰는 서버나 원격 서버에는 빈 비밀번호와 이 설정을 절대 쓰지 마세요.

## 2. 실습 환경 준비

**필요한 것**

- `bash`나 `zsh`를 쓰는 Linux 또는 macOS. Windows에서는 WSL 2 터미널을 쓰세요.
- Compose v2가 포함된 [Docker](https://docs.docker.com/get-docker/):
  `docker compose version`이 버전을 출력해야 합니다.
- Python 3.11 이상: `python3 --version`.
- `git`.

CUBRID 11.4 이미지는 x86_64(`linux/amd64`)용으로 배포됩니다. Apple Silicon Mac에서는
Docker가 에뮬레이션으로 실행하며, 이 튜토리얼은 Linux x86_64에서만 확인했습니다.

**코드와 Python 환경 준비.** 프로젝트를 두는 폴더에서 실행하세요. 이후의 모든
명령은 `git clone`이 만드는 `cubrid-cookbook-python` 폴더에서 실행합니다.

```bash
git clone https://github.com/cubrid-lab/cubrid-cookbook-python.git
cd cubrid-cookbook-python
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r quickstart/first-cubrid/requirements.txt
```

`source .venv/bin/activate`를 실행하면 `python`이 이 프로젝트 전용 Python을
가리키므로, 패키지가 여기에만 설치됩니다. 나중에 새 터미널을 열면
`cd cubrid-cookbook-python`과 `source .venv/bin/activate`를 다시 실행하세요.

**데이터베이스를 시작하고 준비될 때까지 기다리기.**

```bash
CUBRID_VERSION=11.4 docker compose up -d
python scripts/wait_for_cubrid.py
```

`docker compose up -d`는 `docker-compose.yml`대로 `cubrid-cookbook`이라는
컨테이너를 시작하고 바로 돌아옵니다. 데이터베이스가 뜨기까지는 몇 초가 더 걸리며,
두 번째 명령이 그동안 기다립니다.

**확인.** 마지막 줄이 다음과 같아야 합니다.

```text
CUBRID is ready: the in-container csql query passed.
```

그다음 `docker compose ps`에 `cubrid-cookbook`과 `127.0.0.1:33000->33000/tcp`가
보여야 합니다. 데이터베이스가 응답한 뒤에도 30초 정도는 상태가
`health: starting`으로 보일 수 있는데, 정상입니다.

기다리다 시간이 초과되면 `docker compose logs cubrid`로 원인을 보세요.
`docker compose up`이 33000 포트가 이미 쓰이고 있다고 하면, 다른 프로그램(대개 다른
CUBRID 컨테이너)이 그 포트를 쓰고 있는 것이니 그 프로그램을 먼저 멈추세요.
내가 만들지 않은 컨테이너나 볼륨은 지우지 마세요.

## 3. 첫 성공: 접속해서 값 읽기

첫 프로그램 전체입니다.
[`quickstart/first-cubrid/01_first_query.py`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/01_first_query.py):

```python
"""01_first_query.py — connect to CUBRID from Python and read a first result.

Step 3 of the beginner tutorial (quickstart/first-cubrid/README.md).
"""

from __future__ import annotations

import pycubrid

# The disposable lab started by docker-compose.yml: a local-only database with
# an empty password for the dba account. Never use these settings for a shared
# or remote server.
SETTINGS = {
    "host": "localhost",  # the machine running the lab container
    "port": 33000,  # the broker port: the connection entry point
    "database": "testdb",  # the database the lab image creates
    "user": "dba",
    "password": "",
}


def main() -> None:
    conn = pycubrid.connect(**SETTINGS)  # open a connection to the database
    try:
        cursor = conn.cursor()  # a cursor sends SQL and holds its results
        cursor.execute("SELECT 1 + 1, 'Hello, CUBRID'")
        total, greeting = cursor.fetchone()  # one row, as a tuple
        print(f"1 + 1 = {total}")
        print(f"Greeting: {greeting}")

        cursor.execute("SELECT database()")
        print(f"Connected to database: {cursor.fetchone()[0]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- `pycubrid.connect(...)`는 **연결**, 즉 서버와의 세션 하나를 엽니다.
- `conn.cursor()`는 **커서**를 줍니다. 커서는 `execute(...)`로 SQL을 보냅니다.
- `fetchone()`은 다음 결과 행을 튜플로 돌려주고, `fetchall()`은 모든 행을 돌려줍니다.
- `conn.close()`는 세션을 끝냅니다. `try`/`finally` 덕분에 중간에 실패해도 닫힙니다.

실행:

```bash
python quickstart/first-cubrid/01_first_query.py
```

**확인.** 예상 출력:

```text
1 + 1 = 2
Greeting: Hello, CUBRID
Connected to database: testdb
```

## 4. 데이터 저장, 커밋, 다른 연결에서 확인

[`02_save_and_verify.py`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/02_save_and_verify.py)는
자기 전용 테이블 `cookbook_first_cubrid_notes`를 만들고 행 두 개를 저장합니다. 테이블에
주석(comment)으로 표시를 남겨서, 이후 단계가 이 테이블만 다루게 합니다. 같은 이름의
테이블이 이미 있으면 아무것도 바꾸지 않고 멈춥니다.

핵심 부분:

```python
cursor.execute(
    "CREATE TABLE cookbook_first_cubrid_notes ("
    " id INT AUTO_INCREMENT PRIMARY KEY,"
    " note VARCHAR(100) NOT NULL"
    ") COMMENT = 'created by the cubrid-cookbook first-cubrid tutorial'"
)
for note in ("My first row", "My second row"):
    cursor.execute("INSERT INTO cookbook_first_cubrid_notes (note) VALUES (?)", (note,))
conn.commit()
```

- `?`는 **파라미터 자리 표시자**입니다. 값은 Python 인자로 따로 넘기고, pycubrid가
  각 값을 올바르게 이스케이프한 값으로 문장에 넣으므로 값이 문장의 뜻을 바꿀 수 없습니다.
  값을 SQL 문자열에 직접 붙여 넣지 말고 항상 이렇게 넘기세요. (pycubrid가 값을 바인딩하는 방식:
  [파라미터화된 쿼리](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/fundamentals/parameterized-queries/README.md))
- 변경은 **`commit()`**을 호출해야 확정됩니다. pycubrid는 자동 커밋이 꺼진 채로
  시작하므로, 마지막 커밋 이후의 모든 변경이 하나의 **트랜잭션**이 됩니다.
  `commit()`은 새 테이블과 두 행을 영구히 저장하고 다른 연결에서도 보이게 합니다.

커밋한 뒤 스크립트는 다른 프로그램처럼 **두 번째 독립 연결**을 열어 테이블을 읽습니다.

```bash
python quickstart/first-cubrid/02_save_and_verify.py
```

**확인.** 예상 출력:

```text
Created cookbook_first_cubrid_notes and saved 2 rows.
A second connection reads:
  1: My first row
  2: My second row
```

id `1`과 `2`는 새 테이블의 `AUTO_INCREMENT`가 매긴 값입니다.

**rollback으로 변경 되돌리기.**
[`03_rollback.py`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/03_rollback.py)는
행을 하나 더 넣고 열린 트랜잭션 안에서 보여 준 뒤 **`rollback()`**을 호출합니다.
`rollback()`은 마지막 커밋 이후의 모든 변경을 버립니다. 저장해 둔 두 행은 남습니다.

```bash
python quickstart/first-cubrid/03_rollback.py
```

**확인.** 예상 출력:

```text
Rows before the change: 2
Rows inside the open transaction: 3
Rows after rollback: 2
```

각 스크립트는 끝나기 전에 연결을 닫습니다. 데이터를 읽기만 한 트랜잭션도 열려
있는 동안에는 잠금을 잡고 있어서, 다른 연결의 `DROP TABLE`이 그 잠금을 기다리게 됩니다.

## 5. 마무리, 복구, 다시 실행

**튜토리얼 테이블 정리.**
[`04_cleanup.py`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/04_cleanup.py)는
이 튜토리얼이 만든 경우에만 `cookbook_first_cubrid_notes`를 지웁니다. 그래서 언제든, 몇 번을
실행해도 안전합니다.

```bash
python quickstart/first-cubrid/04_cleanup.py
```

**확인.** 예상 출력:

```text
Dropped cookbook_first_cubrid_notes.
```

한 번 더 실행하면 `Nothing to clean up: cookbook_first_cubrid_notes does not exist.`가 출력됩니다.

**다시 실행하기.** 정리한 뒤 3단계부터 다시 시작하세요. 데이터베이스는 그동안 계속 실행 중입니다.

**단계가 중간에 끊겼다면** (Ctrl-C를 눌렀거나 터미널이 닫혔다면):

- 커밋 전에 끊긴 단계는 아무것도 저장하지 않았습니다. 그 단계를 다시 실행하세요.
- 4단계가 `cookbook_first_cubrid_notes is left over from an earlier run.`을 출력하면
  `04_cleanup.py`를 실행한 뒤 4단계를 다시 실행하세요.
- `A table named cookbook_first_cubrid_notes already exists and was not created by this tutorial.`이
  출력되면 그 테이블은 다른 사람의 것입니다. 튜토리얼은 아무것도 바꾸지 않고, 그 테이블을 지우지도 않습니다.
- 데이터베이스 자체가 멈췄다면 `CUBRID_VERSION=11.4 docker compose up -d`와
  `python scripts/wait_for_cubrid.py`를 다시 실행하세요.

**실습 환경 멈추기.** 얼마나 지울지 고르세요. `cubrid-cookbook-python` 폴더에서 실행합니다.

| 명령 | 컨테이너 | 데이터 |
|------|----------|--------|
| `docker compose stop` | 멈춤. `docker compose start`로 다시 시작 | 남음 |
| `docker compose down` | 삭제 | 실습 환경의 Docker 볼륨에 남음. 다음 `CUBRID_VERSION=11.4 docker compose up -d`에서 되살아남 |
| `docker compose down -v` | 삭제 | `testdb`까지 포함해 **삭제** |

`docker compose down -v`는 `docker-compose.yml`에 이름이 적힌 이 실습 환경의 볼륨만
지웁니다. 다른 컨테이너나 볼륨은 건드리지 않습니다. Python 환경에서 나오려면 `deactivate`를 실행하세요.

## 다음 단계

- **pycubrid로 SQL 더 익히기**: [pycubrid 기초 예제](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/fundamentals/pycubrid/README.md)는
  같은 실습 환경에서 CRUD, prepared statement, 오류 처리, LOB 등으로 이어집니다.
- **SQL 문자열 대신 Python 객체로**: [SQLAlchemy 빠른 시작](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/5min-sqlalchemy/README.md).
- **작은 웹 API**: [FastAPI 빠른 시작](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/5min-fastapi/README.md).

연결, 브로커, 트랜잭션이 어떻게 동작하는지 더 깊이 알고 싶다면
[pycubrid 문서](https://github.com/cubrid-lab/pycubrid#readme)를 보세요.
