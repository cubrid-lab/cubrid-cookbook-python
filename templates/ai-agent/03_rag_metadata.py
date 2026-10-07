"""RAG metadata hybrid — document store with structured CUBRID metadata.

Pattern: embeddings live in an external vector store (conceptual), while
document full text, metadata, tags, and chunk tracking live in CUBRID.
This demonstrates how CUBRID serves as the "source of truth" layer
in a retrieval-augmented generation pipeline.
"""

from __future__ import annotations

from contextlib import closing

import json
import os
import pycubrid

# Same CUBRID_* env vars as 02_mcp_toolchain.py, so a single live test
# instance (or a local dev CUBRID) configures every recipe in this folder.
DB_CONFIG = {
    "host": os.environ.get("CUBRID_HOST", "localhost"),
    "port": int(os.environ.get("CUBRID_PORT", "33000")),
    "user": os.environ.get("CUBRID_USER", "dba"),
    "password": os.environ.get("CUBRID_PASSWORD", ""),
    "database": os.environ.get("CUBRID_DATABASE", "testdb"),
}

DDL = [
    """
    CREATE TABLE IF NOT EXISTS rag_documents (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(200) NOT NULL,
        source VARCHAR(500),
        content STRING,
        metadata JSON,
        tags SET(VARCHAR(50)),
        chunk_count INT DEFAULT 0,
        created_at DATETIME DEFAULT SYS_DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rag_chunks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        document_id INT NOT NULL,
        chunk_index INT NOT NULL,
        content STRING,
        token_count INT,
        embedding_ref VARCHAR(500),
        FOREIGN KEY (document_id) REFERENCES rag_documents(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rag_retrieval_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        query_text STRING,
        retrieved_doc_ids SEQUENCE(INT),
        llm_response STRING,
        relevance_scores JSON,
        created_at DATETIME DEFAULT SYS_DATETIME
    )
    """,
]

SAMPLE_DOCS = [
    {
        "title": "CUBRID Python Driver Guide",
        "source": "https://github.com/cubrid-lab/pycubrid",
        "content": "pycubrid is a pure Python DB-API 2.0 driver for CUBRID. "
        "It supports sync and async connections, LOB handling, "
        "parameterized queries, and works on Python 3.11+.",
        "tags": ["driver", "python", "getting-started"],
        "metadata": {"author": "cubrid-lab", "type": "documentation", "version": "1.7"},
    },
    {
        "title": "SQLAlchemy CUBRID Dialect",
        "source": "https://github.com/cubrid-lab/sqlalchemy-cubrid",
        "content": "sqlalchemy-cubrid provides a SQLAlchemy dialect for CUBRID "
        "supporting ORM, Core, Alembic migrations, JSON types, "
        "and three driver backends.",
        "tags": ["orm", "sqlalchemy", "python"],
        "metadata": {"author": "cubrid-lab", "type": "documentation", "version": "1.7"},
    },
    {
        "title": "MCP Server for CUBRID",
        "source": "https://github.com/cubrid-lab/cubrid-mcp-server",
        "content": "cubrid-mcp-server is a Model Context Protocol server that "
        "lets LLM clients safely query CUBRID with read-only "
        "whitelisting and opt-in write mode.",
        "tags": ["mcp", "ai", "llm", "safety"],
        "metadata": {"author": "cubrid-lab", "type": "tool", "version": "0.4"},
    },
]


def setup(conn: pycubrid.connection.Connection) -> None:
    cur = conn.cursor()
    for ddl in DDL:
        cur.execute(ddl)
    conn.commit()
    cur.close()


def ingest_document(
    conn: pycubrid.connection.Connection,
    doc: dict,
    chunk_size: int = 100,
) -> int:
    """Store a document with metadata, then create chunks.

    In production, each chunk would be sent to an embedding API
    and the resulting vector stored externally. We simulate this
    with an `embedding_ref` pointing to the conceptual vector store.
    """
    cur = conn.cursor()

    # Store the document with its metadata
    tags = "{" + ", ".join("?" for _ in doc["tags"]) + "}"
    cur.execute(
        "INSERT INTO rag_documents (title, source, content, metadata, tags) "
        "VALUES (?, ?, ?, ?, " + tags + ")",
        [doc["title"], doc["source"], doc["content"], json.dumps(doc["metadata"]), *doc["tags"]],
    )
    doc_id = cur.lastrowid
    if doc_id is None:
        cur.close()
        conn.rollback()
        raise RuntimeError("Document INSERT did not return an auto-increment ID")
    conn.commit()

    # Simple chunking (word-based, for demonstration)
    words = doc["content"].split()
    chunks = [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)]

    # Store chunks with conceptual embedding references
    for i, chunk in enumerate(chunks):
        cur.execute(
            "INSERT INTO rag_chunks (document_id, chunk_index, content, token_count, embedding_ref) "
            "VALUES (?, ?, ?, ?, ?)",
            [doc_id, i, chunk, len(chunk.split()), f"vecstore://doc-{doc_id}/chunk-{i}"],
        )
    conn.commit()

    # Update chunk count
    cur.execute("UPDATE rag_documents SET chunk_count = ? WHERE id = ?", [len(chunks), doc_id])
    conn.commit()
    cur.close()
    return doc_id


def keyword_search(
    conn: pycubrid.connection.Connection,
    query: str,
) -> list[dict]:
    """Simulate retrieval — in production this would combine vector similarity
    with CUBRID-side filtering."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, metadata FROM rag_documents WHERE content LIKE ? ORDER BY id",
        [f"%{query}%"],
    )
    results = []
    rows = cur.fetchall()
    for row in rows:
        # The released driver returns raw collection payloads; TABLE() reads elements.
        cur.execute(
            "SELECT t.tag FROM rag_documents, TABLE(tags) AS t(tag) WHERE id = ?",
            [row[0]],
        )
        results.append(
            {
                "id": row[0],
                "title": row[1],
                "tags": [tag[0] for tag in cur.fetchall()],
                "metadata": json.loads(row[2]) if row[2] else {},
            }
        )
    cur.close()
    return results


def log_retrieval(
    conn: pycubrid.connection.Connection,
    query: str,
    doc_ids: list[int],
    llm_response: str,
    scores: list[float],
) -> None:
    """Log a RAG interaction for analytics and evaluation."""
    cur = conn.cursor()
    # Collection members are scalar bound values, not a quoted '{...}' string.
    ids_seq = "{" + ", ".join("?" for _ in doc_ids) + "}"
    cur.execute(
        "INSERT INTO rag_retrieval_log (query_text, retrieved_doc_ids, llm_response, relevance_scores) "
        "VALUES (?, " + ids_seq + ", ?, ?)",
        [query, *doc_ids, llm_response, json.dumps(scores)],
    )
    conn.commit()
    cur.close()


def main() -> None:
    with closing(pycubrid.connect(**DB_CONFIG)) as conn:
        setup(conn)

        # Ingest sample documents
        print("Ingesting documents...")
        for doc in SAMPLE_DOCS:
            doc_id = ingest_document(conn, doc)
            print(f"  [{doc_id}] {doc['title']} ({len(doc['tags'])} tags)")

        # Simulate a RAG query
        print("\nQuery: 'How do I connect Python to CUBRID?'")
        results = keyword_search(conn, "Python")
        print(f"  Retrieved {len(results)} documents:")
        for r in results:
            print(f"    [{r['id']}] {r['title']} tags={r['tags']}")

        # Simulate LLM synthesis (this is where you'd call OpenAI/Anthropic)
        llm_response = (
            "Based on the retrieved documents, pycubrid is the pure Python "
            "DB-API 2.0 driver for CUBRID. You can install it with "
            "'pip install pycubrid' and connect using pycubrid.connect()."
        )

        # Log the full interaction
        log_retrieval(
            conn,
            "How do I connect Python to CUBRID?",
            [r["id"] for r in results],
            llm_response,
            [0.92] * len(results),
        )
        print("  Logged to rag_retrieval_log")

        # Verify: retrieve logged interactions with JSON scores
        cur = conn.cursor()
        cur.execute(
            "SELECT id, query_text, relevance_scores "
            "FROM rag_retrieval_log ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            print(f"  Logged query: {row[1][:40]}...")
            cur.execute(
                "SELECT d.doc_id FROM rag_retrieval_log, TABLE(retrieved_doc_ids) AS d(doc_id) "
                "WHERE id = ?",
                [row[0]],
            )
            logged_doc_ids = [result[0] for result in cur.fetchall()]
            print(f"  Doc IDs: {logged_doc_ids}")
            assert logged_doc_ids == [result["id"] for result in results]
            scores = json.loads(row[2]) if row[2] else []
            print(f"  Relevance scores: {scores}")
            assert len(scores) == len(results)
        cur.close()
        print("\n✓ RAG metadata hybrid working")


if __name__ == "__main__":
    main()
