"""Magic rewrite: turn written text into text that is easy to *say*.

Built in (no download, no network): rule-based clean-up that fixes what makes speech engines stumble.
Optional smarter rewriting through llm.py (OpenRouter by default, via the OpenAI SDK; also OpenAI, any
OpenAI-compatible server, or a local Ollama chat model) when the user asks for a tone or free-form rewrite.

Rule-based steps (each reported back, so nothing changes silently):
* markdown, URLs, e-mail addresses and stray symbols -> spoken forms
* numbers, money, percentages, ordinals, years, times -> words
* common abbreviations (Dr., vs., etc.) and "&" -> words
* long sentences are split at natural joints so there is room to breathe
* optional contractions for a conversational tone
"""

from __future__ import annotations

import re

from . import llm

ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
SCALES = [(10**9, "billion"), (10**6, "million"), (10**3, "thousand")]
ORD_IRREG = {
    "one": "first",
    "two": "second",
    "three": "third",
    "five": "fifth",
    "eight": "eighth",
    "nine": "ninth",
    "twelve": "twelfth",
}
ABBR = {
    "Dr.": "Doctor",
    "Mr.": "Mister",
    "Mrs.": "Missus",
    "Ms.": "Miss",
    "Prof.": "Professor",
    "St.": "Saint",
    "vs.": "versus",
    "vs": "versus",
    "etc.": "et cetera",
    "e.g.": "for example",
    "i.e.": "that is",
    "approx.": "approximately",
    "Inc.": "Incorporated",
    "Ltd.": "Limited",
    "Co.": "Company",
    "min.": "minutes",
    "hr.": "hours",
    "&": "and",
    "w/": "with",
    "w/o": "without",
}
CONTRACTIONS = [
    (r"\bdo not\b", "don't"),
    (r"\bdoes not\b", "doesn't"),
    (r"\bdid not\b", "didn't"),
    (r"\bis not\b", "isn't"),
    (r"\bare not\b", "aren't"),
    (r"\bcannot\b", "can't"),
    (r"\bwill not\b", "won't"),
    (r"\bI am\b", "I'm"),
    (r"\bit is\b", "it's"),
    (r"\bIt is\b", "It's"),
    (r"\bthat is\b", "that's"),
    (r"\bwe are\b", "we're"),
    (r"\bthey are\b", "they're"),
    (r"\byou are\b", "you're"),
    (r"\bI will\b", "I'll"),
    (r"\byou will\b", "you'll"),
    (r"\bwe will\b", "we'll"),
    (r"\bI have\b", "I've"),
    (r"\bwe have\b", "we've"),
]


def int_to_words(n: int) -> str:
    if n < 0:
        return "minus " + int_to_words(-n)
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return ONES[n // 100] + " hundred" + (" " + int_to_words(n % 100) if n % 100 else "")
    for size, name in SCALES:
        if n >= size:
            rest = n % size
            return int_to_words(n // size) + " " + name + (" " + int_to_words(rest) if rest else "")
    raise ValueError("unreachable")


def ordinal_words(n: int) -> str:
    words = int_to_words(n)
    parts = re.split(r"([ -])", words)
    last = parts[-1]
    if last in ORD_IRREG:
        last = ORD_IRREG[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return "".join(parts[:-1]) + last


def year_words(y: int) -> str:
    if 2000 <= y <= 2009:
        return int_to_words(y)
    hi, lo = divmod(y, 100)
    return int_to_words(hi) + " " + ("oh " + ONES[lo] if 0 < lo < 10 else int_to_words(lo) if lo else "hundred")


def _digits(s: str) -> str:
    return " ".join(ONES[int(c)] for c in s)


def _num(m: re.Match) -> str:
    s = m.group(0).replace(",", "")
    if "." in s:
        whole, frac = s.split(".", 1)
        return int_to_words(int(whole or 0)) + " point " + _digits(frac)
    return int_to_words(int(s)) if len(s) <= 12 else _digits(s)


def spell_numbers(text: str) -> str:
    def money(m):
        cur = {"$": ("dollar", "cent"), "£": ("pound", "penny"), "€": ("euro", "cent")}[m.group(1)]
        whole = int(m.group(2).replace(",", ""))
        out = int_to_words(whole) + " " + cur[0] + ("" if whole == 1 else "s")
        if m.group(3):
            c = int(m.group(3)[1:].ljust(2, "0")[:2])
            if c:
                out += (
                    " and "
                    + int_to_words(c)
                    + " "
                    + (cur[1] if c == 1 else ("pence" if cur[1] == "penny" else cur[1] + "s"))
                )
        return out + {
            "k": " thousand",
            "K": " thousand",
            "m": " million",
            "M": " million",
            "b": " billion",
            "B": " billion",
        }.get(m.group(4) or "", "")

    text = re.sub(r"([$£€])(\d[\d,]*)(\.\d+)?([kKmMbB]\b)?", money, text)
    text = re.sub(r"(\d+(?:\.\d+)?)\s?%", lambda m: spell_numbers(m.group(1)) + " percent", text)
    text = re.sub(
        r"\b(\d{1,2}):(\d{2})\s?(am|pm|AM|PM|a\.m\.|p\.m\.)",
        lambda m: (
            int_to_words(int(m.group(1)))
            + (
                " o'clock"
                if m.group(2) == "00"
                else " oh " + ONES[int(m.group(2))]
                if m.group(2)[0] == "0"
                else " " + int_to_words(int(m.group(2)))
            )
            + " "
            + " ".join(m.group(3).lower().replace(".", ""))
        ),
        text,
    )
    text = re.sub(r"\b(\d+)(st|nd|rd|th)\b", lambda m: ordinal_words(int(m.group(1))), text)
    text = re.sub(
        r"\b(1[0-9]{3}|20[0-9]{2})\b(?!\s?(?:people|items|dollars|users|%))",
        lambda m: year_words(int(m.group(1))),
        text,
    )
    return re.sub(r"\d[\d,]*(?:\.\d+)?", _num, text)


def clean_symbols(text: str) -> tuple[str, list[str]]:
    notes = []
    t = text
    t2 = re.sub(r"https?://\S+|www\.\S+", "the link", t)
    if t2 != t:
        notes.append('Replaced links with "the link".')
    t = t2
    t2 = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", lambda m: m.group(0).replace("@", " at ").replace(".", " dot "), t)
    if t2 != t:
        notes.append("Spelled out e-mail addresses.")
    t = t2
    t2 = re.sub(r"[*_`#>]+", "", t)
    t2 = re.sub(r"^\s*[-•]\s+", "", t2, flags=re.M)
    if t2 != t:
        notes.append("Removed markdown symbols.")
    t = t2
    t = (
        t.replace("\u2014", ", ")
        .replace("\u2013", " to ")
        .replace("\u2026", "...")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    return t, notes


def expand_abbreviations(text: str) -> str:
    text = re.sub(r"\bNo\.\s*(?=\d)", "number ", text)  # "No. 5" is a number; "No." alone is just "no"
    for k, v in sorted(ABBR.items(), key=lambda kv: -len(kv[0])):
        pat = r"(?<!\w)" + re.escape(k) + (r"(?!\w)" if k[-1] != "." else "")
        text = re.sub(pat, v, text)
    return text


def split_long(text: str, max_words: int = 24) -> tuple[str, int]:
    out, n = [], 0
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = sent.split()
        if len(words) <= max_words:
            out.append(sent)
            continue
        pieces = re.split(r"(?<=,)\s+|\s+(?=(?:and|but|so|because|which|while|although)\b)", sent)
        cur = ""
        for p in pieces:
            if cur and len((cur + " " + p).split()) > max_words:
                out.append(cur.rstrip(",;") + ".")
                cur, n = p[0].upper() + p[1:], n + 1
            else:
                cur = (cur + " " + p).strip()
        out.append(cur)
    return " ".join(out), n


def rule_rewrite(text: str, conversational: bool = False) -> dict:
    """Deterministic clean-up. Returns {text, notes}."""
    original = text
    notes: list[str] = []
    # Square-bracket tags ([pause 1s], [laugh], ...) are instructions, not prose: park them, restore at the end.
    parked: list[str] = []

    def park(m):
        parked.append(m.group(0))
        return chr(0xE100 + len(parked) - 1)  # one private-use character per tag: no digits to be spelled out

    text = re.sub(r"\[[^\[\]\n]{1,40}\]", park, text)
    t, n = clean_symbols(text)
    notes += n
    t2 = expand_abbreviations(t)
    if t2 != t:
        notes.append("Expanded abbreviations.")
    t = t2
    t2 = spell_numbers(t)
    if t2 != t:
        notes.append("Wrote numbers, money, percentages, dates and times as words.")
    t = t2
    if conversational:
        for pat, rep in CONTRACTIONS:
            t = re.sub(pat, rep, t)
        notes.append("Used contractions for a conversational tone.")
    t, split = split_long(t)
    if split:
        notes.append(f"Split {split} long sentence{'s' if split != 1 else ''} at natural breaks.")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t).strip()
    t = re.sub("[\ue100-\uf8ff]", lambda m: parked[ord(m.group(0)) - 0xE100], t)
    if t == original.strip() and not notes:
        notes.append("Nothing needed fixing.")
    return {"text": t, "notes": notes, "engine": "built-in rules"}


# ---------------------------------------------------------------- optional smarter rewrite

TONES = {
    "natural": "Make it sound like natural, relaxed speech.",
    "energetic": "Make it upbeat and punchy.",
    "warm": "Make it warm and reassuring.",
    "professional": "Make it clear, confident and professional.",
    "shorter": "Make it about 30% shorter without losing the key points.",
}


def llm_available() -> dict:
    """Kept for the rest of the app; the real logic lives in llm.py (OpenAI SDK, OpenRouter by default)."""
    st = llm.status()
    return {"available": st["available"], "via": st["via"]}


def chat(system: str, user: str, temperature: float = 0.4, timeout: float = 90) -> str:
    return llm.chat(system, user, temperature, timeout)


def llm_rewrite(text: str, tone: str = "natural", instruction: str = "") -> dict:
    """Ask a language model to rewrite for speech. Raises RuntimeError with a plain message if none is set up."""
    if tone not in TONES:
        raise ValueError("Unknown tone.")
    system = (
        "You rewrite text so it reads well when spoken aloud by a voice actor. Keep the meaning and every fact. "
        "Write numbers and symbols as words. Do not add stage directions, markdown or quotes. Keep tags "
        "in square brackets such as [pause 1s] or [laugh] exactly as written. Reply with only the rewritten text. "
        + TONES[tone]
        + (" Extra direction: " + instruction.strip()[:300] if instruction.strip() else "")
    )
    out = chat(system, text)
    return {
        "text": out,
        "notes": [f"Rewritten for a {tone} tone by a language model. Read it before using it."],
        "engine": "language model",
    }
