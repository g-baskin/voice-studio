"""Script writer for Studio: turn a short brief into speaker-tagged lines.

* With a language model set up (OpenRouter key, OPENAI_API_KEY, NATURALVOICE_LLM_URL, or a local Ollama chat model) it writes the script.
* Without one, a built-in outline writer arranges the user's own points into a proper structure
  (hook, body, call to action) so the feature always works. It is a template, not an AI, and says so.
Output is always {title, lines:[{speaker, text}], engine, notes, words, estimated_seconds}.
"""

from __future__ import annotations

import json
import random
import re

from . import rewrite

WORDS_PER_SECOND = 2.5  # relaxed read at speed 1.0
KINDS = {
    "ad": "Ad / commercial",
    "social": "Short social video",
    "podcast_intro": "Podcast intro",
    "explainer": "Explainer",
    "story": "Story / narration",
    "dialogue": "Dialogue between two people",
}
TONES = ["friendly", "energetic", "professional", "calm", "dramatic", "funny"]
CLONE_TAGS = ["[chuckle]", "[laugh]", "[sigh]", "[gasp]"]

SAMPLES = {
    "ad": [
        (
            "Sunrise Coffee",
            "Small-batch roasted beans delivered fresh every week; free shipping on the first box; cancel any time",
            "Order your first box today.",
        )
    ],
    "social": [
        ("Glow Skin Serum", "One drop a day; visible glow in a week; made with vitamin C", "Tap the link to try it.")
    ],
    "podcast_intro": [
        (
            "The Weekend Builders",
            "Every week we build one project in under two hours; real tools, real mistakes; no experience needed",
            "",
        )
    ],
    "explainer": [
        (
            "how noise-cancelling headphones work",
            "microphones listen to the noise around you; the headphones play the opposite sound wave; the two cancel out",
            "",
        )
    ],
    "story": [
        (
            "The Lighthouse Keeper",
            "an old keeper guards a quiet coast; one stormy night a small boat appears; he lights the lamp and brings it home",
            "",
        )
    ],
    "dialogue": [
        (
            "a new budgeting app",
            "it tracks spending automatically; it shows where money leaks; setup takes two minutes",
            "Try it free this week.",
        )
    ],
}


def sample(kind: str = "ad") -> dict:
    kind = kind if kind in KINDS else "ad"
    topic, brief, cta = random.choice(SAMPLES[kind])
    return {"kind": kind, "topic": topic, "brief": brief, "cta": cta}


def _points(brief: str) -> list[str]:
    parts = [p.strip(" .-•\t") for p in re.split(r"[\n;]+|(?<=[.!?])\s+", brief or "") if p.strip(" .-•\t")]
    return parts[:6]


def _sentence(s: str) -> str:
    s = s.strip().rstrip(".!?")
    return (s[:1].upper() + s[1:] + ".") if s else ""


HOOKS = {
    "friendly": "Hey there! Quick question: ever wish things were just a little easier?",
    "energetic": "Stop scrolling! This is the one you've been waiting for.",
    "professional": "Every great result starts with the right choice.",
    "calm": "Take a breath. Let's make this simple.",
    "dramatic": "Everything changes... with one decision.",
    "funny": "Let's be honest: we've all been there, and it wasn't pretty.",
}


def _assign(texts: list[str], speakers: list[str]) -> list[dict]:
    return [{"speaker": speakers[i % len(speakers)], "text": t} for i, t in enumerate(texts) if t]


def template_script(
    topic: str, brief: str, kind: str, tone: str, seconds: int, speakers: list[str], cta: str = ""
) -> dict:
    topic = (topic or "this").strip()
    pts = _points(brief) or ["it makes your day easier"]
    budget = int(seconds * WORDS_PER_SECOND)
    hook = HOOKS.get(tone, HOOKS["friendly"])
    cta = cta.strip() or {
        "ad": f"Try {topic} today.",
        "social": "Follow for more.",
        "dialogue": f"Give {topic} a try.",
    }.get(kind, "")
    if kind == "dialogue":
        a, b = speakers[0], speakers[1 if len(speakers) > 1 else 0]
        texts = [(a, f"Have you heard about {topic}?"), (b, "No. What is it?")]
        for i, p in enumerate(pts):
            texts.append((a if i % 2 == 0 else b, _sentence(p if i == 0 else p)))
            if i < len(pts) - 1:
                texts.append(
                    (b if i % 2 == 0 else a, ["Really?", "That sounds useful.", "Okay, I'm interested."][i % 3])
                )
        texts.append((b, "Sounds great. How do I start?"))
        texts.append((a, _sentence(cta) or "Just give it a try."))
        lines = [{"speaker": s, "text": t} for s, t in texts]
    else:
        if kind == "podcast_intro":
            body = [f"Welcome to {topic}.", _sentence(pts[0]), *[_sentence(p) for p in pts[1:3]], "Let's get into it."]
        elif kind == "explainer":
            order = ["First", "Next", "Then", "Finally"]
            body = (
                [f"Let's talk about {topic}."]
                + [
                    f"{order[min(i, 3)]}, {p.strip().rstrip('.')[:1].lower() + p.strip().rstrip('.')[1:]}."
                    for i, p in enumerate(pts)
                ]
                + ["And that's the big idea."]
            )
        elif kind == "story":
            body = [f"This is the story of {topic}.", *[_sentence(p) for p in pts], "And that is how it ended."]
        elif kind == "social":
            body = [hook, f"{topic}: {_sentence(pts[0])}", *([_sentence(pts[1])] if len(pts) > 1 else [])]
        else:  # ad
            body = [hook, f"Meet {topic}.", *[_sentence(p) for p in pts]]
        if cta:
            body.append(_sentence(cta))
        lines = _assign(body, speakers)

    # Trim from the middle until it fits the length (never drop the first or the last line).
    def words(lines):
        return sum(len(line["text"].split()) for line in lines)

    while words(lines) > budget * 1.15 and len(lines) > 3:
        lines.pop(len(lines) // 2)
    notes = [
        "Built-in outline: your own points arranged into a script structure. It's a template, not an AI. "
        "Connect an AI (an OpenRouter key) for fully written scripts."
    ]
    if words(lines) < budget * 0.6:
        notes.append("Shorter than the length you asked for. Add more details to the brief to fill the time.")
    return {"title": topic[:80], "lines": lines, "engine": "built-in outline", "notes": notes}


def _parse(raw: str, speakers: list[str]) -> tuple[str, list[dict]]:
    title = ""
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            lines = [
                {"speaker": str(line.get("speaker", speakers[0]))[:30], "text": str(line.get("text", "")).strip()}
                for line in data.get("lines", [])
                if isinstance(line, dict) and str(line.get("text", "")).strip()
            ]
            if lines:
                return str(data.get("title", ""))[:80], lines
        except (ValueError, AttributeError):
            pass
    lines = []
    for ln in raw.splitlines():
        mm = re.match(r"\s*\[?([A-Za-z][\w ]{0,28})\]?\s*:\s*(.+)", ln)
        if mm:
            lines.append({"speaker": mm.group(1).strip(), "text": mm.group(2).strip()})
    if not lines:
        lines = [{"speaker": speakers[0], "text": t.strip()} for t in re.split(r"\n\s*\n", raw) if t.strip()]
    return title, lines


def llm_script(
    topic: str,
    brief: str,
    kind: str,
    tone: str,
    seconds: int,
    speakers: list[str],
    cta: str,
    audience: str,
    emotion_tags: bool,
) -> dict:
    budget = int(seconds * WORDS_PER_SECOND)
    system = (
        f"You write {KINDS[kind].lower()} scripts for voice actors. Tone: {tone}. Target about {budget} spoken words "
        f"(plus or minus 15%). Use only these speaker names, exactly: {', '.join(speakers)}. "
        "Write for the ear: short sentences, natural speech, numbers and symbols written as words. No stage directions, "
        "no markdown, no emojis. You may use [pause 1s] for a beat. "
        + (
            f"You may sparingly use these sound tags where a person would make the sound: {' '.join(CLONE_TAGS)}. "
            if emotion_tags
            else "Do not use any other square-bracket tags. "
        )
        + 'Reply with ONLY JSON: {"title": "...", "lines": [{"speaker": "...", "text": "..."}]}.'
    )
    user = (
        f"Topic: {topic or 'unspecified'}\nDetails: {brief or 'none'}\nAudience: {audience or 'general'}\n"
        f"Call to action: {cta or 'none'}"
    )
    raw = rewrite.chat(system, user, temperature=0.8)
    title, lines = _parse(raw, speakers)
    allowed = set(speakers)
    for line in lines:  # keep speaker names to the cast the user chose
        if line["speaker"] not in allowed:
            line["speaker"] = speakers[0]
    return {
        "title": title or topic[:80],
        "lines": lines,
        "engine": "language model",
        "notes": ["Written by a language model. Read it through before you record."],
    }


def generate(
    topic: str = "",
    brief: str = "",
    kind: str = "ad",
    tone: str = "friendly",
    seconds: int = 30,
    speakers: list[str] | None = None,
    cta: str = "",
    audience: str = "",
    mode: str = "auto",
    emotion_tags: bool = False,
) -> dict:
    if kind not in KINDS:
        raise ValueError("Unknown script type.")
    if tone not in TONES:
        raise ValueError("Unknown tone.")
    if not 10 <= seconds <= 300:
        raise ValueError("Length must be between 10 and 300 seconds.")
    if mode not in {"auto", "llm", "template"}:
        raise ValueError("Unknown mode.")
    speakers = [re.sub(r"[^\w .'-]", "", s).strip()[:30] for s in (speakers or ["Narrator"])]
    speakers = [s for s in speakers if s][:4] or ["Narrator"]
    if kind == "dialogue" and len(speakers) < 2:
        speakers = ["Alex", "Sam"]
    out = None
    fallback_note = None
    if mode in {"auto", "llm"} and (mode == "llm" or rewrite.llm_available()["available"]):
        try:
            out = llm_script(topic, brief, kind, tone, seconds, speakers, cta, audience, emotion_tags)
        except RuntimeError as e:
            if mode == "llm":
                raise
            fallback_note = f"The language model didn't answer ({e}) so the built-in outline was used."
    if out is None:
        out = template_script(topic, brief, kind, tone, seconds, speakers, cta)
        if fallback_note:
            out["notes"].insert(0, fallback_note)
    # Spell numbers/symbols for speech on every line (tags are protected by the rewrite engine).
    for line in out["lines"]:
        line["text"] = rewrite.rule_rewrite(line["text"])["text"]
    words = sum(len(line["text"].split()) for line in out["lines"])
    out.update(
        words=words, estimated_seconds=round(words / WORDS_PER_SECOND, 1), speakers=speakers, kind=kind, tone=tone
    )
    return out
