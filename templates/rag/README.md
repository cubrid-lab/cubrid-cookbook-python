# Local RAG example: CUBRID, Qdrant and Ollama

This is a **runnable, local-only demonstration**, not a deployment or compliance
reference for a government information system. It uses three **fictional**
public-service documents; no government records or personal data are included.

Unlike [the RAG metadata recipe](../ai-agent/03_rag_metadata.py), which simulates
vector references and LLM output, this example calls a real local embedding
model, writes vectors to Qdrant, retrieves matching chunks from **CUBRID**, and
asks a local LLM to answer with numbered citations.

## Architecture

1. `ingest.py` reads `data/sample_documents.json` and splits each document.
2. The local Ollama embedding model creates a vector for each chunk.
3. CUBRID stores the canonical document text, chunk text and source reference.
4. Qdrant stores only embeddings and stable CUBRID identifiers.
5. `POST /ask` embeds the question, searches Qdrant, resolves the identifiers
   through parameterized CUBRID queries, and prompts Ollama with the retrieved
   source text. The response includes explicit source references.

The Qdrant collection and CUBRID tables use distinct `cookbook_rag_demo_*`
names, so they do not overwrite the existing `ai-agent` template's data.

## Requirements

- Python 3.11+ and Docker Compose; enough memory/disk for local Ollama models.
- Docker images: CUBRID 11.4, Qdrant 1.15.5 and Ollama 0.12.3.
- No OpenAI API key, cloud AI service, LangChain or external embedding API.
- Internet access **once** to download container images, Python dependencies
  and the two Ollama model weights. Subsequent runs can be offline when cached.

## Run

From the repository root:

```bash
cd templates/rag
docker compose up -d --wait
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull qwen2.5:0.5b
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python ingest.py
uvicorn app:app --host 127.0.0.1 --port 8000
```

`--wait` returns once CUBRID answers its health check. The first start creates
the `testdb` database and can take a few minutes; later starts are faster.
On Windows, activate the virtual environment with the command for your shell.
In a second terminal, send a question:

```bash
curl -sS http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"How can an Example City resident request a document?"}'
```

The API returns an `answer` and `sources` (title, fictional `sample://`
reference, CUBRID chunk identifier and citation number). The LLM's wording may
vary. `GET /health` reports process health only; it does not check DB, Qdrant
or Ollama readiness.

`docker compose down` stops containers but retains data; `docker compose
down -v` **deletes all example database, vectors and model volumes**.

## Validation

Run offline, deterministic tests (no Docker, DB or models). pytest is a test
tool, not a runtime dependency, so install it into the same virtual environment
first. From `templates/rag`:

```bash
pip install pytest
python -m pytest tests/test_offline.py -q
```

For the full end-to-end example, execute the Run commands and inspect a real
answer and its CUBRID-backed citations. This example does **not** claim CI
verification against both CUBRID 11.2/11.4; the compose stack pins 11.4 and the
AI services are not started in the repository's normal CI.

Re-running `ingest.py` replaces only sample rows with the same stable source
IDs and replaces their Qdrant vectors. A CUBRID commit and a Qdrant update are
**not atomic**: if synchronization fails, stop queries and rerun ingestion.
If you remove a document from the sample JSON, its old rows are not
automatically deleted; manual cleanup or a real synchronization job is needed.

## Security and production gaps

The compose ports are bound to **127.0.0.1**. The stock lab uses an unprotected
`dba` account **only for local disposable sample data**. Do not expose these
ports, attach this example to a real database, or use real institutional data.
Before any production adaptation, implement separate least-privilege ingest
and read-only query accounts, document-level authorization **before** retrieval,
data classification and redaction, embedding/LLM data-handling review, rate
limits, timeouts, audit logs and security testing. User identity, tenancy and
document authorization are **not implemented** here. Prompt instructions are
not a security boundary, and the model can give incorrect or unsupported
answers. Citations are source identifiers, not verification that every sentence
of generated text is true.

The example intentionally omits live migration, change-data-capture, deletion
reconciliation, retry queues, and cross-system transactional guarantees.
For CUBRID production support, use the official support channels rather than
treating this demo as an operator or disaster-recovery solution.
