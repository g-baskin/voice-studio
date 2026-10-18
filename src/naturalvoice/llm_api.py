"""/api/llm: connect an OpenRouter key from the app. The key is never sent back to the browser."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import llm

router = APIRouter(prefix="/api/llm")


class KeyBody(BaseModel):
    api_key: str = Field(min_length=1, max_length=400)
    model: str = Field(default="", max_length=100)


@router.get("/status")
def status():
    return llm.status()


@router.put("/key")
def put_key(body: KeyBody):
    try:
        return llm.connect(body.api_key, body.model)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:  # bad key, no credit, no internet: shown to the user in plain words
        raise HTTPException(502, str(e))


@router.delete("/key")
def delete_key():
    llm.clear_key()
    return llm.status()
