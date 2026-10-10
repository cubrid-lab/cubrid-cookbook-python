# CUBRID용 Streamlit 레시피 (한국어)

> 🌐 [README.md](README.md)의 번역입니다. 영어 원문이 표준이며, 이 번역은 경고 수준의 동기화 규칙을 따릅니다.

이 디렉터리에는 서로 독립적으로 실행할 수 있는 Streamlit 레시피 다섯 개가 있습니다. 각 레시피는 하나의 `.py` 파일이며 `streamlit run <파일>.py`로 바로 실행할 수 있습니다.

모든 레시피는 다음을 공통으로 사용합니다.

- 연결 문자열: `cubrid+pycubrid://dba@localhost:33000/testdb`
- SQLAlchemy 엔진 캐싱: `@st.cache_resource`
- 테이블 이름 접두사: `cookbook_`
- 불리언은 정수 `0/1` (`is_active`)
- 금액은 센트 단위 정수 (`unit_price_cents`)
- **Reset Demo Data**(데모 데이터 초기화) 버튼 — 데모 테이블을 삭제한 뒤 다시 만듭니다

## 레시피

1. `01_table_viewer.py` — `st.dataframe`과 자동 갱신으로 쿼리 결과를 실시간 표시
2. `02_filters.py` — 사이드바에서 카테고리·가격 필터, 동적 `WHERE` 절
3. `03_kpis.py` — `COUNT`, `SUM`, `AVG`로 `st.metric` KPI 카드
4. `04_charts.py` — Streamlit 기본 차트 API로 그룹 막대·선 그래프
5. `05_form_crud.py` — `st.form`으로 삽입·수정·삭제

## 한 번에 데모 실행 (Docker)

```bash
docker compose up -d
# → localhost:33000 에 CUBRID 11.4, http://localhost:8501 에 대시보드
```

Compose 파일은 CUBRID 11.4와 Streamlit 서비스를 함께 띄웁니다. 첫 기동 시 고정된(pinned) requirements를 설치하므로 몇 분 걸릴 수 있고, 이후 실행은 pip 캐시를 재사용합니다. 레시피는 환경 변수 `DATABASE_URL`을 읽습니다(기본값 `cubrid+pycubrid://dba@localhost:33000/testdb`). Compose 서비스는 같은 스택 안의 CUBRID 컨테이너를 가리킵니다. `docker compose down -v`로 볼륨까지 지우면 전체를 초기 상태로 돌릴 수 있습니다.

## 로컬 설정 (앱은 Docker 없이)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행

```bash
streamlit run 01_table_viewer.py
streamlit run 02_filters.py
streamlit run 03_kpis.py
streamlit run 04_charts.py
streamlit run 05_form_crud.py
```

## 참고

- 첫 실행 시 각 레시피가 데모 테이블이 없으면 만들고, 비어 있으면 샘플 행을 넣습니다.
- 특정 레시피를 깨끗한 상태로 다시 시작하려면 해당 화면의 **Reset Demo Data**(데모 데이터 초기화) 버튼을 사용하세요.
