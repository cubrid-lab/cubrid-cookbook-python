# 3단원: 행 저장하고 다시 읽기

> 🌐 [quickstart/first-cubrid/save-a-row.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/save-a-row.md)의 한국어 학습 경로입니다. 영어 원문이 표준이며, 코드와 출력은 원문과 같습니다.
>
> English: [Lesson 3: Save rows and read them back](https://cubrid-lab.github.io/cubrid-cookbook-python/first-cubrid-save-a-row/)

튜토리얼 전용 작은 테이블을 만들어 행 두 개를 저장하고 커밋한 뒤, 두 번째 연결에서 읽습니다.
[처음 만드는 CUBRID 데이터베이스](first-cubrid.md)의 3단원입니다.

## 시작하기 전에

- [2단원](first-cubrid-first-query.md)이 `Connected to database: testdb`를 출력해, 실습 환경이
  실행 중이고 연결 설정이 동작하는 것을 확인했어야 합니다.
- 가상 환경을 활성화한 채 `cubrid-cookbook-python` 폴더에 있어야 합니다. 새 터미널을
  열었다면 `cd cubrid-cookbook-python`과 `source .venv/bin/activate`를 다시 실행하세요.

## 프로그램

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

## 실행하기

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

## 다시 실행하면

첫 실행에서 만든 테이블이 남아 있으므로, 스크립트는 아무것도 바꾸지 않고 멈춥니다.

- `cookbook_first_cubrid_notes is left over from an earlier run.`은 튜토리얼 자신의
  테이블이 남아 있다는 뜻입니다. [5단원](first-cubrid-finish.md)의 정리 스크립트로 지운 뒤 이
  단원을 다시 실행하세요.
- `A table named cookbook_first_cubrid_notes already exists and was not created by this tutorial.`은
  그 테이블이 다른 사람의 것이라는 뜻입니다. 튜토리얼은 아무것도 바꾸지 않고, 그 테이블을
  지우지도 않습니다.

## 다음 단계

저장되기 전에 변경을 되돌려 봅니다. [4단원: rollback](first-cubrid-rollback.md).
