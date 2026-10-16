# 처음 만드는 CUBRID 데이터베이스 (Python)

> 🌐 [quickstart/first-cubrid/README.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/README.md)의 한국어 학습 경로입니다. 영어 원문이 표준이며, 코드와 출력은 원문과 같습니다.

**CUBRID가 처음이라면 여기서 시작하세요.** Python 파일은 실행할 수 있지만
CUBRID는 써 본 적이 없는 분을 위한 튜토리얼입니다. 내 컴퓨터에 연습용
데이터베이스를 띄우고, Python에서 접속하고, 행 몇 개를 저장하고, `commit`과
`rollback`이 하는 일을 확인한 뒤 정리합니다. FastAPI, SQLAlchemy, 이 저장소의
기여자용 도구는 필요 없습니다.

준비물을 설치한 뒤라면 15분 정도 걸립니다. 처음에는 데이터베이스 이미지를
내려받느라 인터넷 속도에 따라 더 걸릴 수 있습니다.

튜토리얼은 다섯 개의 짧은 단원으로, 다음 순서로 진행합니다.

1. 이 페이지의 "1. 무엇을 설치하나요"와 "2. 실습 환경 준비"
2. [첫 쿼리 실행하기](first-cubrid-first-query.md)
3. [행 저장하고 다시 읽기](first-cubrid-save-a-row.md)
4. [rollback으로 변경 되돌리기](first-cubrid-rollback.md)
5. [안전하게 마치기](first-cubrid-finish.md): 정리, 복구, 실습 환경 멈추기

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

다음으로 [첫 쿼리를 실행하세요](first-cubrid-first-query.md).

## 3. 첫 성공: 접속해서 값 읽기

이 단계는 별도 단원에서 다룹니다. [2단원: 첫 쿼리 실행하기](first-cubrid-first-query.md)에서
`01_first_query.py`를 실행해 출력을 확인하고, 그 프로그램이 쓰는 연결과 커서를 설명합니다.

## 4. 데이터 저장, 커밋, 다른 연결에서 확인

이 단계는 이제 두 개의 단원입니다. [3단원: 행 저장하고 다시 읽기](first-cubrid-save-a-row.md)에서
`02_save_and_verify.py`를, [4단원: rollback으로 변경 되돌리기](first-cubrid-rollback.md)에서
`03_rollback.py`를 실행합니다.

## 5. 마무리, 복구, 다시 실행

튜토리얼 테이블 정리, 끊긴 실행의 복구, 실습 환경 멈추기는
[5단원: 안전하게 마치기](first-cubrid-finish.md)에 있습니다.

## 다음 단계

- **pycubrid로 SQL 더 익히기**: [pycubrid 기초 예제](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/fundamentals/pycubrid/README.md)는
  같은 실습 환경에서 CRUD, prepared statement, 오류 처리, LOB 등으로 이어집니다.
- **SQL 문자열 대신 Python 객체로**: [SQLAlchemy 빠른 시작](quickstart-sqlalchemy.md).
- **작은 웹 API**: [FastAPI 빠른 시작](quickstart-fastapi.md).

연결, 브로커, 트랜잭션이 어떻게 동작하는지 더 깊이 알고 싶다면
[pycubrid 문서](https://github.com/cubrid-lab/pycubrid#readme)를 보세요.
