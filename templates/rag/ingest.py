"""Load a fictional public-service corpus into CUBRID and Qdrant."""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

from pipeline import Ollama, Qdrant, connect_cubrid, ensure_tables, ingest_document

SAMPLE_FILE = Path(__file__).resolve().parent / "data" / "sample_documents.json"


def main() -> None:
    documents = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    ollama = Ollama()
    qdrant = Qdrant()
    with closing(connect_cubrid()) as conn:
        ensure_tables(conn)
        for document in documents:
            count = ingest_document(conn, qdrant, ollama, document)
            print(f"Indexed {count} chunks: {document['source_ref']}")
    print("Sample indexing complete. Rerunning safely replaces the same sample documents.")


if __name__ == "__main__":
    main()
