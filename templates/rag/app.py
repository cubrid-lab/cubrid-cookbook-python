"""Local-only example API for asking questions over a fictional CUBRID corpus."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from pipeline import answer_question

app = FastAPI(title="CUBRID RAG demo", version="0.1.0")


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@app.post("/ask")
def ask(payload: Question) -> dict:
    try:
        return answer_question(payload.question)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/health")
def health() -> dict:
    # Process health only; this is not a dependency readiness check.
    return {"status": "ok"}
