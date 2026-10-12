# CUBRID용 Flask + Flask-SQLAlchemy 레시피 (한국어)

> 🌐 [README.md](README.md)의 번역입니다. 영어 원문이 표준이며, 이 번역은 경고 수준의 동기화 규칙을 따릅니다.

이 디렉터리에는 Flask-SQLAlchemy로 CUBRID 기반 JSON API 패턴을 단계적으로 보여 주는, 서로 독립적인 Flask 레시피가 있습니다.

## 요구 사항

- Python 3.11 이상
- 레시피별 Python 가상 환경
- 레시피 애플리케이션을 실행할 때는 실행 중인 CUBRID 인스턴스가 필요합니다. 기본 CRUD 앱의 기본 연결 문자열은 `cubrid+pycubrid://dba@localhost:33000/testdb`이며, 저장소 루트에서 `make up`을 실행하면 지원되는 로컬 CUBRID 서비스가 시작됩니다.
- 테스트에는 CUBRID가 필수가 아닙니다. `CUBRID_TEST_URL`을 설정하지 않으면 테스트 픽스처가 임시 SQLite 데이터베이스를 사용합니다.

## 레시피 구성

번호가 붙은 각 디렉터리는 자체 README, 애플리케이션 파일, 테스트를 갖춘 독립 레시피입니다.

- `01-basic-crud/`
- `02-categories/`
- `03-inventory-ledger/`
- `04-purchase-orders/`
- `05-batch-operations/`
- `06-case-triage/`
- `07-vendor-feed/`
- `08-transactional-outbox/`
- `09-rbac/`
- `10-workflow-engine/`
- `11-inventory-reservation/`

`01-basic-crud`부터 시작하고, 엔드포인트와 레시피별 추가 설정은 각 레시피의 README를 따르세요.

## 레시피 실행

예를 들어 저장소의 로컬 CUBRID 서비스를 시작한 뒤 기본 CRUD 레시피를 실행합니다.

```bash
# 저장소 루트에서:
make up

cd templates/flask/01-basic-crud
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

기본 CRUD 레시피는 `/api/products` 아래에 JSON 기반 Product CRUD 엔드포인트를 제공합니다. 지원되는 다른 CUBRID 인스턴스를 쓰려면 앱을 시작하기 전에 `DATABASE_URL`을 설정하세요. 예:

```bash
DATABASE_URL="cubrid+pycubrid://dba@localhost:33000/testdb" python run.py
```

## 테스트

레시피의 테스트 스위트는 해당 레시피 디렉터리에서 실행합니다. `01-basic-crud`의 경우:

```bash
cd templates/flask/01-basic-crud
pip install pytest
python -m pytest tests/ -v
```

테스트는 기본적으로 임시 SQLite 데이터베이스를 사용합니다. 실행 중인 CUBRID 인스턴스로 테스트하려면 레시피별 README와 마찬가지로 `CUBRID_TEST_URL`을 설정하세요.

```bash
CUBRID_TEST_URL="cubrid+pycubrid://dba@localhost:33000/testdb" python -m pytest tests/ -v
```

## 더 알아보기

번호가 붙은 각 레시피는 자체 엔드포인트, 예제, 추가 요구 사항을 문서로 제공합니다. 데이터베이스 오류 처리에 초점을 맞춘 레시피는 저장소의 `fundamentals/error-handling/` 예제를 참고하세요.
