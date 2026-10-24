# CUBRIDdb에서 pycubrid로 이전하기

> 🌐 [migration/cubriddb-to-pycubrid/README.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/migration/cubriddb-to-pycubrid/README.md)의 한국어 번역입니다. 영어 원문이 표준이며, 명령과 출력은 원문과 같습니다.

이 가이드는 공식 C 확장 드라이버 `CUBRIDdb`
([CUBRID/cubrid-python](https://github.com/CUBRID/cubrid-python))를 쓰는 Python 애플리케이션을
순수 Python 드라이버 [`pycubrid`](https://github.com/cubrid-lab/pycubrid)로 옮기는 방법을
다룹니다. Python 안에서 드라이버만 바꾸는 이전입니다. **Java/JDBC** 애플리케이션을 Python으로
옮긴다면 [Java → Python 마이그레이션 가이드](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/migration/java-to-python)를 보세요.

두 드라이버 모두 Python DB-API 2.0(PEP 249)을 구현하고 같은 CUBRID 브로커와 통신하므로
데이터베이스, 스키마, 데이터와 대부분의 SQL 문은 그대로 둡니다. 그렇다고 서로 **바꿔 끼울 수
있는 것은 아닙니다**. 설치 방법, 연결 인자, 기본 트랜잭션 모드, 스레드 공유, 파라미터가 서버로
가는 방식, 오류 속성, 노출하는 네이티브 CCI 기능이 다릅니다. import 한 줄을 바꾸는 일이 아니라
테스트가 필요한 애플리케이션 변경으로 다루세요. pycubrid는 CCI나 `_cubrid`와 완전히 같다고
주장하지 않습니다.

## 이 페이지의 주장을 확인한 방법

| 표시 | 뜻 |
|------|----|
| **여기서 실행** | 이 디렉터리의 레시피 네 개가 실제 CUBRID에서 실행했고, 그 출력이 [`expected/`](https://github.com/cubrid-lab/cubrid-cookbook-python/tree/main/migration/cubriddb-to-pycubrid/expected)의 골든입니다. |
| **pycubrid 소스** | 설치된 pycubrid 패키지(1.13.1, 하한 확인용 1.6.1)나 그 변경 기록에서 읽었습니다. |
| **공식 소스, 실행 안 함** | [cubrid-python `v11.3.0.51`](https://github.com/CUBRID/cubrid-python/tree/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5)(커밋 `c63ab9c`, `VERSION` 11.3.0)에서 읽었습니다. 쿡북은 공식 드라이버를 빌드하거나 실행하지 않으므로 그 실행 동작은 여기서 **검증되지 않았습니다**. |

이 저장소에는 공식 드라이버와 비교 실행한 결과가 없습니다. 이 페이지의 CUBRIDdb 설명은 모두
소스를 읽고 쓴 것이며, 아래 CUBRIDdb 코드 조각은 실행하지 않습니다.

## 파일 구성

| 파일 | 보여 주는 것 |
|------|--------------|
| [01_connection_mapping.py](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/migration/cubriddb-to-pycubrid/01_connection_mapping.py) | DSN → 키워드 인자, 기본 autocommit OFF, autocommit 켜기, 커서와 연결 닫기, 모듈의 `threadsafety` |
| [02_parameterized_crud.py](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/migration/cubriddb-to-pycubrid/02_parameterized_crud.py) | `str`, `Decimal`, `date`, `bytes`, `None` 값을 쓰는 `?` 파라미터, `executemany()`, 일반 텍스트로 저장되는 악의적 문자열, `rowcount` |
| [03_fetch_and_errors.py](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/migration/cubriddb-to-pycubrid/03_fetch_and_errors.py) | `description`, 튜플 행과 그로부터 만든 dict, `fetchone/fetchmany/fetchall`, CLOB 열, `errno`/`code`/`sqlstate`/`args`, `InterfaceError` |
| [04_transaction_visibility.py](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/migration/cubriddb-to-pycubrid/04_transaction_visibility.py) | `commit()`/`rollback()` 전후에 두 번째 세션이 보는 것, 트랜잭션 안에서 실패한 문장, autocommit ON에서 같은 단계 |

각 레시피는 표시용 주석(COMMENT)을 붙인 자기 테이블(`cookbook_cdb_connect`, `cookbook_cdb_orders`,
`cookbook_cdb_events`, `cookbook_cdb_ledger`)을 만듭니다. 같은 이름의 테이블이 표시 없이 이미
있으면 아무것도 바꾸지 않고 멈추고, 중단된 실행이 남긴 표시된 테이블은 지우며, 자기 테이블은
`finally` 블록에서 삭제합니다.

## 레시피 실행

먼저 쿡북 실습 환경을 띄우고(저장소 루트에서 `make up`,
[시작하기](getting-started.md) 참고) 다음을 실행합니다.

```bash
cd migration/cubriddb-to-pycubrid
pip install -r requirements.txt
python 01_connection_mapping.py
python 02_parameterized_crud.py
python 03_fetch_and_errors.py
python 04_transaction_visibility.py
```

저장소 루트에서 네 개를 골든과 비교합니다.

```bash
make verify-goldens VERIFY_PATHS=migration/cubriddb-to-pycubrid
```

`make verify`(CI에서 CUBRID 11.2와 11.4)도 같은 골든을 실행합니다. `make test`는 오프라인으로
모든 레시피에 골든이 있는지, 테이블이 `cookbook_` 접두사를 쓰는지, 이 페이지의 링크와 명령이
맞는지 확인합니다.

레시피에는 쿡북의 전역 하한인 `pycubrid>=1.6.1`이 필요하며, 출력은 pycubrid 1.6.1과 1.13.1에서
같았습니다. 더 새 pycubrid가 필요한 기능은 아래에 버전과 함께 적었고, 레시피에서는 쓰지 않습니다.

## 1. 설치

| | CUBRIDdb (공식) | pycubrid |
|---|---|---|
| 정체 | 번들된 CCI 라이브러리 위의 C 확장(`_cubrid`)과 `CUBRIDdb` 래퍼 패키지 | 순수 Python, 컴파일러나 CCI 라이브러리 불필요 |
| 설치 | 고정한 소스 리비전에서 빌드: `git clone --recursive`, 태그 체크아웃, 그다음 [README](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/README.md)의 빌드 명령(setuptools 빌드, 또는 체크아웃에서 휠을 만들어 설치) | `pip install pycubrid` |
| 타입 힌트 | 소스 트리에 `py.typed`나 `.pyi` 스텁 없음 | `py.typed` 포함(pycubrid 소스) |
| asyncio | 소스 트리에 비동기 API 없음 | `pycubrid.aio`(pycubrid 1.1.0부터) |

공식 드라이버는 테스트한 소스 리비전, 예를 들어 이 페이지가 인용하는 태그 `v11.3.0.51`에
고정하세요. 그 대신 `pip install CUBRID-Python`을 쓰지 **마세요**. 이 PyPI 프로젝트의 최신
릴리스는 2014-05-15에 올라온 소스 아카이브 9.3.0으로(PyPI 메타데이터, 2026-10-24 확인),
11.3 소스보다 몇 년 오래되었습니다. 공식 README는 `ftp.cubrid.org`의 빌드된 휠도 언급하지만,
이 가이드는 그것을 확인하지 않았습니다.

## 2. 연결 매핑

CUBRIDdb, 이전(공식 소스, 실행 안 함):

```python
import CUBRIDdb

conn = CUBRIDdb.connect("CUBRID:localhost:33000:testdb:::", "dba", "")
print(conn.autocommit)  # True: the extension enables autocommit on connect
cur = conn.cursor()  # conn.cursor(dictCursor=True) for dict rows
cur.execute("UPDATE cookbook_cdb_ledger SET balance = ? WHERE id = ?", (10, 1))
# committed already
cur.close()
conn.close()
```

pycubrid, 이후(여기서 실행, `01_connection_mapping.py`):

```python
import pycubrid

conn = pycubrid.connect(host="localhost", port=33000, database="testdb", user="dba", password="")
print(conn.autocommit)  # False
with conn.cursor() as cur:  # the cursor is closed when the block ends
    cur.execute("UPDATE cookbook_cdb_ledger SET balance = ? WHERE id = ?", (10, 1))
conn.commit()  # without this the update is rolled back on close
conn.close()
```

| 항목 | CUBRIDdb (공식 소스, 실행 안 함) | pycubrid |
|------|----------------------------------|----------|
| 인자 | `connect(dsn, user, password)`, CCI URL `CUBRID:host:port:db:::`; `Connection(..., charset="utf8")` | `connect(host=, port=, database=, user=, password=, ...)` 키워드 인자; URL과 CCI URL 속성 없음(알 수 없는 키워드는 경고만 함, pycubrid 소스) |
| 기본 사용자 | `"public"`([`connections.py:17`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/CUBRIDdb/connections.py#L17)) | `"dba"`(pycubrid 소스). 항상 `user=`를 명시하세요 |
| 연결 직후 autocommit | ON: 연결 초기화의 `cci_set_autocommit(..., CCI_AUTOCOMMIT_TRUE)`([`python_cubrid.c:464`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/cubrid_ext/python_cubrid.c#L464)) | OFF(**여기서 실행**); 켜려면 `connect(autocommit=True)` 또는 `conn.autocommit = True` |
| commit / rollback | `conn.commit()`, `conn.rollback()` | 이름은 같고, autocommit OFF에서는 반드시 호출. autocommit OFF에서는 DDL도 트랜잭션에 묶이므로 `CREATE TABLE` 뒤에 commit하세요 |
| 문자셋 | `charset` 인자, 기본 `"utf8"` | pycubrid 1.9.0부터 `charset=` 인자, 기본 `"utf-8"`(pycubrid 변경 기록); 이전 릴리스는 항상 UTF-8 |
| `threadsafety` | `2`: 스레드가 연결을 공유 가능([`__init__.py:11`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/CUBRIDdb/__init__.py#L11)) | `1`: 스레드는 모듈만 공유하고 연결은 공유하지 **않음**(**여기서 실행**). 스레드마다 연결을 따로 쓰거나 풀을 쓰세요 |
| `paramstyle` | `'qmark'` | `'qmark'`(**여기서 실행**) |
| 닫힌 객체 | 여기서 확인 안 함 | 닫힌 커서나 연결을 쓰면 `InterfaceError`(**여기서 실행**) |

`01_connection_mapping.py`의 한 세션 확인은 autocommit OFF로 행을 하나 넣고 두 번 셉니다. 같은
세션은 자기의 대기 중인 행을 보고, 두 번째 연결은 보지 못하며, `rollback()` 뒤에는 어느 쪽도
보지 못합니다. autocommit ON이면 두 번째 연결이 바로 그 행을 보는데, CUBRIDdb 코드는 이 동작을
전제로 작성되어 있습니다.

## 3. 안전한 파라미터 CRUD

`?` 표시는 그대로 두고 값은 튜플로 넘깁니다. SQL 문은 바뀌지 않습니다.

| Python 값 | CUBRIDdb 래퍼(공식 소스, 실행 안 함) | 일반 pycubrid 커서 |
|---|---|---|
| 모든 값 | `prepare()` 후 값마다 `bind_param()`, CCI 타입 바인딩으로 전송([`cursors.py:143`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/CUBRIDdb/cursors.py#L143)) | 드라이버가 이스케이프된 SQL 리터럴로 바꾼 뒤 prepare-and-execute 요청 하나로 전송(pycubrid 소스) |
| `None` | `_bind_params`가 건너뜀(바인딩 호출 없음, [`cursors.py:183`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/CUBRIDdb/cursors.py#L183)); 그때 CCI가 무엇을 보내는지는 실행해 보지 않음 | SQL `NULL`(**여기서 실행**); `None`을 쓴 `WHERE col = ?`는 아무것도 맞지 않으니 `IS NULL`을 쓰세요 |
| `Decimal`, `date`, `bytes`, `str` | 타입별 바인딩(`bytes`는 `VARBIT`) | `Decimal`, `datetime.date`, `bytes`, `str`로 저장되고 그대로 읽힘(**여기서 실행**) |
| `executemany()` | 한 번 prepare한 뒤 행마다 바인딩하고 실행([`cursors.py:255`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/CUBRIDdb/cursors.py#L255)) | INSERT/UPDATE/DELETE/MERGE는 모든 행을 리터럴 문장으로 만들어 배치 요청 하나로 전송; `rowcount`는 합계(**여기서 실행**) |

드라이버 쪽 리터럴 변환 덕분에 `02_parameterized_crud.py`의 악의적 값
(`O'Reilly'); DROP TABLE ...; --`)은 텍스트로 저장되고 테이블은 남습니다. 이 보호는 `?`로 넘긴
값에만 적용됩니다. 신뢰할 수 없는 값을 f-string, `%`, `.format()`으로 SQL 문자열에 넣지 마세요.
테이블 이름 같은 식별자는 파라미터가 될 수 없으므로 정해진 목록과 비교해 확인하세요.

**선택형 prepared 배치.** pycubrid 1.12.0은 INSERT, UPDATE, DELETE, MERGE에 쓰는
`cursor.executemany(sql, rows, prepared=True)`를 추가했습니다. 렌더링한 리터럴 대신 타입이 있는
호스트 변수로 `PREPARE` 한 번과 `EXECUTE_ARRAY` 요청 한 번을 보냅니다(pycubrid 변경 기록). 큰
쓰기 배치에서 자기 워크로드를 측정한 뒤 고려하세요. 다른 문장 종류는 `NotSupportedError`를
냅니다. 실패한 행만 따로 취소되고 나머지 행은 실행되므로, autocommit을 끄고 `commit()`이나
`rollback()`을 직접 결정하세요. 레시피는 1.6.1 하한을 지키므로 이 기능을 쓰지 않습니다.

```python
# pycubrid >= 1.12.0 only; not executed by the recipes
cur.executemany(
    "INSERT INTO cookbook_cdb_orders (customer, amount) VALUES (?, ?)",
    rows,
    prepared=True,
)
conn.commit()
```

## 4. 조회와 오류 처리

**행.** CUBRIDdb는 `conn.cursor(dictCursor=True)`로 행 모양을 고릅니다(공식 소스). 일반
pycubrid 커서는 항상 튜플을 돌려주므로, dict가 필요하면 `cursor.description`으로 만드세요
(**여기서 실행**).

```python
cur.execute("SELECT id, title FROM cookbook_cdb_events ORDER BY id")
names = [column[0] for column in cur.description]
rows = [dict(zip(names, row)) for row in cur.fetchall()]
```

`description` 항목은 7개짜리 튜플이고, 타입 코드는 `pycubrid.NUMBER`, `pycubrid.STRING`,
`pycubrid.DATETIME` 등 DB-API 타입 객체와 같다고 비교됩니다(**여기서 실행**). `null_ok` 필드는
pycubrid 버전마다 믿지 마세요. 이 가이드의 확인에서 1.6.1과 1.13.1의 값이 달랐습니다.

**LOB 열.** 일반 pycubrid 커서는 BLOB이나 CLOB 값을 내용이 아니라 LOB 핸들(`dict`)로
돌려줍니다(**여기서 실행**).
[`fundamentals/pycubrid/06_lob.py`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/fundamentals/pycubrid/06_lob.py)처럼
`pycubrid.Lob`으로 읽거나, 짧은 CLOB은 SQL에서 `VARCHAR`로 `CAST`하세요. CUBRIDdb의 `_cubrid`
LOB 객체 API(`connection.lob()`, `cursor.fetch_lob()`, `lob.read/write/seek/imports/export`)는
일반 pycubrid에 대응하는 것이 없습니다.

**오류.** PEP 249 클래스 이름은 같지만 예외가 담는 내용은 다릅니다.

| | CUBRIDdb (공식 소스, 실행 안 함) | pycubrid |
|---|---|---|
| `exc.args` | `(error_code, "ERROR: DBMS, <code>, <message>")`([`python_cubrid.c:294-301`](https://github.com/CUBRID/cubrid-python/blob/c63ab9c51353e5c80e02dd2c1a19d4640acb29f5/cubrid_ext/python_cubrid.c#L294-L301)) | `(message,)`(**여기서 실행**) |
| 오류 번호 | `exc.args[0]` | `exc.errno`, 데이터베이스 오류에서는 `exc.code`도 같음: 중복 키 `-670`, 없는 테이블이나 구문 오류 `-493`(**여기서 실행**) |
| SQLSTATE | 없음 | `exc.sqlstate`, 예를 들어 중복 키는 `'23000'`(**여기서 실행**). 일부 SQLSTATE는 pycubrid 릴리스 사이에 바뀌었으므로(없는 테이블은 1.6.1에서 `42S02`, 1.13.1에서 `42000`) `errno`나 예외 클래스로 분기하세요 |
| 예외 클래스 | `handle_error`의 고정된 코드 목록으로 선택 | `IntegrityError`, `ProgrammingError`, `OperationalError` 등(앞의 둘은 **여기서 실행**) |

`code, message = exc.args`로 푸는 코드는 `exc.errno`와 `str(exc)`로 바꿔야 합니다.
`InterfaceError`(닫힌 커서나 연결)는 `pycubrid.Error`이지만 `DatabaseError`는 아니고 `errno`도
없습니다(**여기서 실행**).

**트랜잭션 실패.** 실패한 문장이 트랜잭션을 끝내지는 않습니다. 그 트랜잭션에서 앞서 쓴 행은
`commit()`이나 `rollback()`을 부를 때까지 대기 상태로 남습니다(`04_transaction_visibility.py`,
**여기서 실행**). autocommit ON에서는 앞선 문장이 이미 commit되어 `rollback()`으로 되돌릴 수
없습니다. CUBRIDdb 코드는 기본적으로 이 상황에 있습니다.

**연결 끊김과 알 수 없는 결과.** `commit()`(또는 autocommit 문장)이 진행 중일 때 연결이 끊기면,
클라이언트는 서버가 그것을 적용했는지 알 수 없습니다. `OperationalError` 뒤에 멱등이 아닌 쓰기를
무작정 재시도하지 마세요. 다시 연결하고, 데이터를(예를 들어 고유한 업무 키로) 확인한 뒤
결정하세요. 레시피는 연결 끊김을 흉내 내지 않습니다.

**일반 pycubrid 커서가 일부러 지원하지 않는 것.** `_cubrid` 모듈이 노출하는 CCI 수준 API, 즉
명시적 `prepare()`/`bind_param()`, 네이티브 LOB 객체, `connection.set()` 컬렉션 바인딩,
`escape_string()`, 결과 위치 이동, HA URL 속성은 일반 DB-API 범위에 없습니다. pycubrid에는 그
일부를 다루는 선택형 `pycubrid.compat.cubriddb` / `pycubrid.compat.native` 네임스페이스가
있습니다(생성자는 1.8.0부터, CUBRIDdb 방식의 튜플/dict 커서는 1.9.0부터). 무엇이 제공되고 무엇이
안 되는지는 pycubrid의
[호환성 문서](https://github.com/cubrid-lab/pycubrid/blob/99b98a13eb18d8a85312fcafc620acb1f608ece8/docs/UPSTREAM_COMPATIBILITY.md)에
있습니다. 그대로 바꿔 끼우는 대체품이 아니며, 여기 레시피는 이것을 쓰지 않습니다.

## 5. 결정 기준

**CUBRIDdb를 유지하세요.** 위에 적은 네이티브 전용 기능 가운데 pycubrid 선택형 네임스페이스가
다루지 않는 기능에 애플리케이션이 의존할 때, 또는 직접 측정한 워크로드가 CUBRIDdb에서 더 빠르고
그 차이가 중요할 때입니다.

**pycubrid를 고려하세요.** 컴파일러나 CCI 빌드 없는 순수 Python 설치, 타입 힌트(`py.typed`),
네이티브 asyncio(`pycubrid.aio`), [`sqlalchemy-cubrid`](https://github.com/cubrid-lab/sqlalchemy-cubrid)를
통한 SQLAlchemy가 필요할 때입니다.

**성능.** 결과는 드라이버 버전, 서버, 워크로드, 장비에 따라 달라지므로 이 가이드는 성능 수치를
인용하지 않습니다. 두 드라이버를 비교한 날짜가 있는 측정은 cubrid-benchmark(커밋 `edf8836`에
고정)에 있으며, 각각 환경과 주의 사항이 함께 있습니다.

- [pycubrid-release-baseline](https://github.com/cubrid-lab/cubrid-benchmark/tree/edf8836d9e3cbe5e2e70eec84924681bd5603e0e/experiments/pycubrid-release-baseline),
  실행 `2026-10-11_main-vs-1.10.0-vs-cubriddb`: CUBRID 11.4.6에서 pycubrid `main`과 1.10.0을
  CUBRIDdb v11.3.0.51과 비교.
- [pycubrid-executemany-overhead](https://github.com/cubrid-lab/cubrid-benchmark/tree/edf8836d9e3cbe5e2e70eec84924681bd5603e0e/experiments/pycubrid-executemany-overhead),
  실행 `2026-10-11_executemany-vs-cubriddb`: 두 드라이버의 `executemany()` 경로. 그 README는
  공유된 고부하 장비에서 실행했고 합친 중앙값만 믿을 수 있다고 밝힙니다.
- [pycubrid-prepared-batch](https://github.com/cubrid-lab/cubrid-benchmark/tree/edf8836d9e3cbe5e2e70eec84924681bd5603e0e/experiments/pycubrid-prepared-batch):
  CUBRID 10.2-11.4에서 pycubrid의 prepared 배치 경로.

성능을 이유로 결정하기 전에 자기 서버에서 자기 워크로드를 측정하세요. 쿡북의
[성능 패턴](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/performance/README.md)은 pycubrid만 측정합니다.

## 이전 체크리스트

- [ ] pycubrid를 설치하고(`pip install pycubrid`), 애플리케이션이 pycubrid에서 테스트를 통과한
      뒤에만 배포에서 CUBRIDdb 빌드를 제거합니다.
- [ ] 각 `CUBRIDdb.connect("CUBRID:host:port:db:::", user, password)`를
      `pycubrid.connect(host=, port=, database=, user=, password=)`로 바꾸고 `user=`를 명시합니다.
- [ ] 연결마다 트랜잭션 모드를 정합니다. CUBRIDdb의 autocommit ON에 기대던 곳에
      `commit()`/`rollback()`을 넣거나, 의도적으로 `autocommit=True`를 넘깁니다.
- [ ] 한 연결을 여러 스레드가 공유하지 않게 합니다. 스레드마다 연결을 쓰거나 풀을 씁니다.
- [ ] 모든 값을 `?` 파라미터로 넘기고, 문자열로 조립한 SQL을 없앱니다.
- [ ] `cursor(dictCursor=True)`를 `cursor.description`으로 만든 dict로 바꿉니다.
- [ ] `exc.args[0]` 오류 코드 확인을 `exc.errno`나 예외 클래스로 바꿉니다.
- [ ] LOB 코드를 `pycubrid.Lob`으로 다시 쓰고, 네이티브 `_cubrid` 호출을 위의 미지원 목록과
      대조합니다.
- [ ] 자기 테스트와 이 레시피를 사용하는 CUBRID 버전에서 실행합니다.
