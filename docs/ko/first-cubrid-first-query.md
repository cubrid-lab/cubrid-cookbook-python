# 2단원: 첫 쿼리 실행하기

> 🌐 [quickstart/first-cubrid/first-query.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/first-query.md)의 한국어 학습 경로입니다. 영어 원문이 표준이며, 코드와 출력은 원문과 같습니다.
>
> English: [Lesson 2: Run your first query](https://cubrid-lab.github.io/cubrid-cookbook-python/first-cubrid-first-query/)

Python에서 연습용 데이터베이스에 접속해 SQL 문 하나를 보내고, 돌아온 행을 읽습니다.
[처음 만드는 CUBRID 데이터베이스](first-cubrid.md)의 2단원입니다.

## 시작하기 전에

1단원(첫 페이지의 "2. 실습 환경 준비")에서 마련한 것이 필요합니다.

- 실습 환경이 실행 중이어야 합니다. `python scripts/wait_for_cubrid.py`가
  `CUBRID is ready: the in-container csql query passed.`를 출력했어야 합니다.
- 가상 환경을 활성화한 채 `cubrid-cookbook-python` 폴더에 있어야 합니다. 새 터미널을
  열었다면 `cd cubrid-cookbook-python`과 `source .venv/bin/activate`를 다시 실행하세요.

모든 프로그램은 터미널에서 실행하는 파일이므로, 앞서 열어 둔 Python 세션에서 이어지는 것은
없습니다.

## 프로그램

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

## 실행하기

```bash
python quickstart/first-cubrid/01_first_query.py
```

**확인.** 예상 출력:

```text
1 + 1 = 2
Greeting: Hello, CUBRID
Connected to database: testdb
```

대신 `failed to connect to CUBRID broker`가 나오면 실습 환경이 실행 중이 아니거나 아직
준비되지 않은 것입니다. [첫 페이지](first-cubrid.md)의 "2. 실습 환경 준비"로 돌아가 준비
확인을 다시 실행하세요.

## 프로그램이 한 일

- `pycubrid.connect(...)`는 **연결**, 즉 서버와의 세션 하나를 엽니다. 네 가지 설정은
  첫 페이지의 "1. 무엇을 설치하나요"에 나온 값입니다.
- `conn.cursor()`는 **커서**를 줍니다. 커서는 `execute(...)`로 SQL을 보냅니다.
- `fetchone()`은 다음 결과 행을 튜플로 돌려주고, `fetchall()`은 모든 행을 돌려줍니다.
- `conn.close()`는 세션을 끝냅니다. `try`/`finally` 덕분에 중간에 실패해도 닫힙니다.

이 파일의 설정은 `dba` 계정에 비밀번호가 없는 내 컴퓨터 전용 실습 환경의 값입니다. 함께 쓰는
서버나 원격 서버에는 절대 쓰지 마세요.

## 다음 단계

데이터를 저장하고 커밋한 뒤 다른 연결에서 확인합니다.
[첫 페이지](first-cubrid.md)의 "4. 데이터 저장, 커밋, 다른 연결에서 확인"으로 이어 가세요.
