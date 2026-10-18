"""POST /api/rewrite: built-in speech-friendly rewrite, optional language-model rewrite."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import llm, rewrite

router = APIRouter(prefix="/api/rewrite")


class Body(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    mode: str = "rules"  # rules | llm
    tone: str = "natural"
    conversational: bool = False
    instruction: str = Field(default="", max_length=300)


@router.get("/status")
def status():
    return {"rules": True, "llm": llm.status(), "tones": list(rewrite.TONES)}


@router.post("")
def run(body: Body):
    if body.mode not in {"rules", "llm"}:
        raise HTTPException(400, "Mode must be rules or llm.")
    try:
        if body.mode == "rules":
            return rewrite.rule_rewrite(body.text, body.conversational)
        return rewrite.llm_rewrite(body.text, body.tone, body.instruction)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
