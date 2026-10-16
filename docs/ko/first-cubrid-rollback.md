# 4단원: rollback으로 변경 되돌리기

> 🌐 [quickstart/first-cubrid/rollback.md](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/rollback.md)의 한국어 학습 경로입니다. 영어 원문이 표준이며, 코드와 출력은 원문과 같습니다.
>
> English: [Lesson 4: Undo a change with rollback](https://cubrid-lab.github.io/cubrid-cookbook-python/first-cubrid-rollback/)

행을 하나 더 넣고 열린 트랜잭션 안에서 확인한 뒤 `rollback()`으로 버립니다.
[처음 만드는 CUBRID 데이터베이스](first-cubrid.md)의 4단원입니다.

## 시작하기 전에

- [3단원](first-cubrid-save-a-row.md)이 두 행을 출력해, 튜토리얼 테이블
  `cookbook_first_cubrid_notes`에 커밋된 행 두 개가 있어야 합니다.
- 가상 환경을 활성화한 채 `cubrid-cookbook-python` 폴더에 있어야 합니다. 새 터미널을
  열었다면 `cd cubrid-cookbook-python`과 `source .venv/bin/activate`를 다시 실행하세요.

## 프로그램

[`03_rollback.py`](https://github.com/cubrid-lab/cubrid-cookbook-python/blob/main/quickstart/first-cubrid/03_rollback.py)는
행을 하나 더 넣고 열린 트랜잭션 안에서 보여 준 뒤 **`rollback()`**을 호출합니다.
`rollback()`은 마지막 커밋 이후의 모든 변경을 버립니다. 저장해 둔 두 행은 남습니다.

## 실행하기

```bash
python quickstart/first-cubrid/03_rollback.py
```

**확인.** 예상 출력:

```text
Rows before the change: 2
Rows inside the open transaction: 3
Rows after rollback: 2
```

## 일어난 일

- 열린 트랜잭션 안에서는 내 연결에 세 번째 행이 이미 보입니다.
- `rollback()`은 트랜잭션을 끝내고 그 행을 버립니다. 3단원의 두 행은 커밋되었으므로 남습니다.
- 각 스크립트는 끝나기 전에 연결을 닫습니다. 데이터를 읽기만 한 트랜잭션도 열려
  있는 동안에는 잠금을 잡고 있어서, 다른 연결의 `DROP TABLE`이 그 잠금을 기다리게 됩니다.

이 단원은 다시 실행해도 됩니다. 실행할 때마다 같은 행을 하나 더 넣고 버립니다.

`The tutorial table cookbook_first_cubrid_notes is missing: run 02_save_and_verify.py first.`가
출력되면 먼저 [3단원](first-cubrid-save-a-row.md)을 실행하세요.

## 다음 단계

정리하고 실습 환경을 안전하게 멈춥니다. [5단원](first-cubrid-finish.md).
