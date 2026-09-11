# AI Agent Template

CUBRID를 AI 에이전트의 상태 저장소로 사용하는 템플릿 — MCP 서버와 결합해
"자연어 → 안전한 쿼리 → 응답" 전체 파이프라인을 구축합니다.

## 예제

| 파일 | 주제 | 사용 기술 |
|------|------|-----------|
| `01_agent_state.py` | 에이전트 세션·메시지·도구 호출을 CUBRID에 저장 | pycubrid, JSON columns, SET |
| `02_mcp_toolchain.py` | MCP 서버를 프로그래밍 방식으로 호출 (Claude 없이) | cubrid-mcp-server, subprocess |
| `03_rag_metadata.py` | RAG 문서 저장소 — 전문·메타데이터·청크 추적 | pycubrid, JSON, SET, SEQUENCE |
| `04_agent_loop.py` | 쿼리 → 생각 → 행동 → 관찰 에이전트 사이클 | pycubrid, agent state |
| `05_chatbot_backend.py` | 채팅봇 백엔드 — 대화 이력·사용자 선호 저장 | SQLAlchemy ORM, JSON columns |

## 빠른 시작

```bash
# 1. CUBRID 시작 (루트 docker-compose.yml)
cd ../../  # cookbook root
docker compose up -d

# 2. 의존성 설치
cd templates/ai-agent
pip install -r requirements.txt

# 3. 예제 실행
python 01_agent_state.py       # 에이전트 상태 관리
python 02_mcp_toolchain.py     # MCP 도구 체인
python 03_rag_metadata.py      # RAG 메타데이터
python 04_agent_loop.py        # 에이전트 루프
python 05_chatbot_backend.py   # 채팅봇 백엔드
```

## 아키텍처

```
User Query
    ↓
┌─────────────────────────────────┐
│  AI Agent (Python)              │
│  ┌───────────┐  ┌────────────┐ │
│  │ Think     │→ │ Act (MCP)  │ │
│  │ (LLM)     │  │ (read-only)│ │
│  └───────────┘  └────────────┘ │
│       ↓               ↓        │
│  ┌───────────┐  ┌────────────┐ │
│  │ Observe   │→ │ Respond    │ │
│  │           │  │            │ │
│  └───────────┘  └────────────┘ │
│       ↓               ↓        │
│  ┌──────────────────────────┐  │
│  │ CUBRID (state store)     │  │
│  │ · agent_sessions         │  │
│  │ · agent_messages (JSON)  │  │
│  │ · agent_tool_calls (JSON)│  │
│  │ · rag_documents (SET)    │  │
│  │ · rag_chunks             │  │
│  └──────────────────────────┘  │
└─────────────────────────────────┘
```

## CUBRID가 AI 에이전트에 주는 이점

| 기능 | 설명 |
|------|------|
| **JSON 컬럼** | LLM 응답·도구 출력을 구조화된 형태로 저장·조회 |
| **SET / SEQUENCE** | 문서 태깅, 대화 순서, 검색 로그 등 컬렉션 타입 |
| **MCP 읽기 전용 화이트리스트** | 에이전트의 쿼리를 SELECT 전용으로 안전하게 제한 |
| **옵트인 쓰기 모드** | 필요 시 단일 DML만 원자적으로 허용 |
| **트랜잭션** | 에이전트 상태 변경의 일관성 보장 |

## 실제 LLM 연결

이 템플릿의 `simulate_llm_response()` 함수를 실제 API 호출로 교체하세요:

```python
# OpenAI
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": user_message}]
)

# Anthropic Claude
import anthropic
client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": user_message}]
)
```

또는 cubrid-mcp-server를 Claude Desktop에 연결하여
자연어로 직접 CUBRID를 조회하세요 — [GETTING_STARTED.md](../../GETTING_STARTED.md) 참고.
