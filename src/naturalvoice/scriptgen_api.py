"""/api/scriptgen: generate a speaker-tagged script from a brief (language model if set up, else built-in outline)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import llm, rewrite, scriptgen

router = APIRouter(prefix="/api/scriptgen")


class Brief(BaseModel):
    topic: str = Field(default="", max_length=120)
    brief: str = Field(default="", max_length=2000)
    kind: str = "ad"
    tone: str = "friendly"
    seconds: int = 30
    speakers: list[str] = Field(default_factory=lambda: ["Narrator"], max_length=4)
    cta: str = Field(default="", max_length=200)
    audience: str = Field(default="", max_length=200)
    mode: str = "auto"            # auto | llm | template
    emotion_tags: bool = False


@router.get("/status")
def status():
    return {"llm": llm.status(), "kinds": scriptgen.KINDS, "tones": scriptgen.TONES,
            "min_seconds": 10, "max_seconds": 300}


@router.get("/sample")
def sample(kind: str = "ad"):
    return scriptgen.sample(kind[:20])


@router.post("")
def run(body: Brief):
    if not (body.topic.strip() or body.brief.strip()):
        raise HTTPException(400, "Give a topic or a few details to write from.")
    try:
        return scriptgen.generate(**body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
