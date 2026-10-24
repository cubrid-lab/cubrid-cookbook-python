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

1. `01_table_viewer.py` — `st.dataframe`으로 쿼리 결과를 표시하고, Refresh 버튼을 누를 때 다시 조회 (자동 갱신 없음)
2. `02_filters.py` — 사이드바에서 카테고리·가격 필터, 동적 `WHERE` 절
3. `03_kpis.py` — `COUNT`, `SUM`, `AVG`로 `st.metric` KPI 카드
4. `04_charts.py` — Streamlit 기본 차트 API로 그룹 막대·선 그래프
5. `05_form_crud.py` — `st.form`으로 삽입·수정·삭제

## 한 번에 데모 실행 (Docker)

```bash
docker compose up -d
# → localhost:33000 에 CUBRID 11.4, http://localhost:8501 에 대시보드
```

Compose 파일은 CUBRID 11.4와 Streamlit 서비스를 함께 띄웁니다. 첫 기동 시 고정된(pinned) requirements를 설치하므로 몇 분 걸릴 수 있고, 이후 실행은 pip 캐시를 재사용합니다. 레시피는 환경 변수 `DATABASE_URL`을 읽습니다(기본값 `cubrid+pycubrid://dba@localhost:33000/testdb`). Compose 서비스는 같은 스택 안의 CUBRID 컨테이너를 가리킵니다. `docker compose down`은 데이터베이스를 이름 있는 볼륨에 남기고,
`docker compose down -v`로 볼륨까지 지우면 전체를 초기 상태로 돌릴 수 있습니다.

Compose는 CUBRID 브로커(`127.0.0.1:33000`)와 대시보드(`127.0.0.1:8501`)를 이 호스트에만 게시합니다. 실습용 `dba` 계정에는 비밀번호가 없으므로 브로커는 다른 인터페이스에 게시하지 않습니다. 다른 머신에서 대시보드에 접근하게 하려면 의도적으로 `DASHBOARD_HOST_IP`를 지정하세요(예: `DASHBOARD_HOST_IP=0.0.0.0 docker compose up -d`).

### 이전 Compose 파일로 시작한 대시보드 업그레이드

CUBRID는 데이터베이스를 만든 컨테이너의 호스트 이름을 기록합니다. 현재 파일은
`CUBRID_DB_HOST: localhost`를 설정하고 컨테이너 이름은 Compose에 맡깁니다. #413 이후의
파일로 시작한 스택이라면 데이터베이스가 이미 이름 있는 볼륨에 있으니 `localhost`를
가리키게 하고 다시 시작하세요.

```bash
docker compose up -d cubrid
docker compose exec -T -u cubrid cubrid sh -c 'sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1localhost/" "$CUBRID_DATABASES/databases.txt"'
docker compose restart cubrid
docker compose up -d
```

#413 이전에는 데이터베이스가 이름 없는 볼륨에 있었습니다. 현재 파일은 비어 있는 새 이름
있는 볼륨을 마운트하므로, 그 이전 파일로 시작한 스택은 빈 데이터베이스로 뜹니다. 데이터는 예전 볼륨에 그대로 있으니 이 폴더에서 한 번만
옮기세요. **데이터를 삭제하는 `docker compose down -v`는 실행하지 마세요.** 템플릿을
업데이트하기 전에 예전 볼륨을 기록하고 스택을 멈춥니다:

```bash
OLD=$(docker inspect cubrid-dashboard --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker compose stop
```

그다음 템플릿을 업데이트(`git pull`)하고, 데이터베이스를 새 이름 있는 볼륨으로 복사한 뒤
`localhost`를 가리키게 하고 스택을 시작합니다:

```bash
docker compose create cubrid
NEW=$(docker inspect "$(docker compose ps -aq cubrid)" --format '{{range .Mounts}}{{if eq .Destination "/home/cubrid/CUBRID/databases"}}{{.Name}}{{end}}{{end}}')
docker run --rm -v "$OLD":/from:ro -v "$NEW":/to --entrypoint sh cubrid/cubrid:11.4 -c 'cp -a /from/. /to/ && sed -i -E "s/^(testdb[[:space:]]+[^[:space:]]+[[:space:]]+)[^[:space:]]+/\1localhost/" /to/databases.txt && chown cubrid:cubrid /to/databases.txt'
docker compose up -d
```

데이터가 돌아오면 `docker volume rm "$OLD"`로 예전 사본을 지웁니다.

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
