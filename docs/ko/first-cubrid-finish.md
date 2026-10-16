# 5단원: 안전하게 마치기

> 🌐 [quickstart/first-cubrid/finish.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/finish.md)의 한국어 학습 경로입니다. 영어 원문이 표준이며, 코드와 출력은 원문과 같습니다.
>
> English: [Lesson 5: Finish safely](https://cubrid-lab.github.io/cubrid-cookbook-python/first-cubrid-finish/)

튜토리얼 테이블을 지우고, 끊겼거나 반복한 실행에서 복구하고, 의도한 것보다 많이 지우지 않게
실습 환경을 멈춥니다. [처음 만드는 CUBRID 데이터베이스](first-cubrid.md)의 5단원입니다.

## 시작하기 전에

- [3단원](first-cubrid-save-a-row.md) 이후라면 언제든, 단원이 도중에 멈췄을 때도 이 단원을
  실행할 수 있습니다.
- 가상 환경을 활성화한 채 `cubrid-cookbook-python` 폴더에 있어야 합니다. 새 터미널을
  열었다면 `cd cubrid-cookbook-python`과 `source .venv/bin/activate`를 다시 실행하세요.

## 튜토리얼 테이블 정리

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
같은 이름의 테이블이 있지만 이 튜토리얼이 만들지 않았다면
`cookbook_first_cubrid_notes was not created by this tutorial; it was left unchanged.`를
출력하고 아무것도 지우지 않습니다.

## 다시 실행하기

정리한 뒤 [2단원](first-cubrid-first-query.md)부터 다시 시작하세요. 데이터베이스는 그동안 계속
실행 중입니다.

## 단원이 중간에 끊겼다면

Ctrl-C를 눌렀거나 터미널이 닫혔다면:

- 커밋 전에 끊긴 단원은 아무것도 저장하지 않았습니다. 그 단원을 다시 실행하세요.
- 3단원이 `cookbook_first_cubrid_notes is left over from an earlier run.`을 출력하면
  `04_cleanup.py`를 실행한 뒤 3단원을 다시 실행하세요.
- `A table named cookbook_first_cubrid_notes already exists and was not created by this tutorial.`이
  출력되면 그 테이블은 다른 사람의 것입니다. 튜토리얼은 아무것도 바꾸지 않고, 그 테이블을 지우지도 않습니다.
- 데이터베이스 자체가 멈췄다면 `CUBRID_VERSION=11.4 docker compose up -d`와
  `python scripts/wait_for_cubrid.py`를 다시 실행하세요.

## 실습 환경 멈추기

얼마나 지울지 고르세요. `cubrid-cookbook-python` 폴더에서 실행합니다.

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
- **SQL 문자열 대신 Python 객체로**: [SQLAlchemy 빠른 시작](quickstart-sqlalchemy.md).
- **작은 웹 API**: [FastAPI 빠른 시작](quickstart-fastapi.md).

연결, 브로커, 트랜잭션이 어떻게 동작하는지 더 깊이 알고 싶다면
[pycubrid 문서](https://github.com/cubrid-lab/pycubrid#readme)를 보세요.
