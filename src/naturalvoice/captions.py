"""Word-by-word captions: transcript words placed on the timeline, paged, drawn for export and written as SRT."""

from __future__ import annotations

import math
import os
import shutil
import threading
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import editor as ed

# Layout numbers shared with frontend/src/lib/editor/captions.ts; change both together.
PAGE_GAP = 0.6
PAGE_HOLD = 0.3
POP_STEP = 0.04
POP_SCALES = (1.22, 1.12, 1.06)
LINE = 1.15
BAND = 3.2
WRAP = 0.9
MAX_LINES = 2
SHRINK = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
BOX_PAD = 0.16
CLEAN_BACK = (0, 0, 0, 150)
BOLD_TEXT = "#111111"
MAX_STATES = 5000
MAX_SECONDS = 30 * 60
_CLOSERS = "\"')]”’"
_TERMINAL = (".", "?", "!", "…")

FONTS: dict[str, tuple[str, ...]] = {
    "sans-bold": (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    "impact": (
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    "rounded": (
        "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    "system": (
        "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
}

Word = list  # [t0, t1, text] on the timeline


def r3(value: float) -> float:
    # Same rounding as Math.round in the browser, so pages match exactly.
    return math.floor(value * 1000 + 0.5) / 1000


def font_file(key: str) -> Path | None:
    """The first installed file from the fixed allowlist for this font key; never a caller-supplied path."""
    for candidate in FONTS.get(key, ()):
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def transcripts_for(seq: ed.Sequence) -> dict[str, list]:
    """Saved transcript words for each media on the caption track."""
    from .transcript import read_transcript

    track = caption_track(seq)
    found: dict[str, list] = {}
    for clip in seq.clips:
        if clip.track == track and clip.media not in found:
            data = read_transcript(clip.media)
            found[clip.media] = data["words"] if data else []
    return found


def caption_track(seq: ed.Sequence) -> str | None:
    caps = seq.captions
    if caps and caps.track:
        return caps.track
    # Audio tracks first; then video tracks, whose clips carry their own sound until it is detached.
    for kind in ("audio", "video"):
        for track in seq.tracks:
            if track.kind == kind and not track.muted and any(c.track == track.id and not c.muted for c in seq.clips):
                return track.id
    return None


def timeline_words(seq: ed.Sequence, transcripts: dict[str, list]) -> list[Word]:
    """Transcript words of every unmuted clip on the caption track, on the timeline's clock."""
    track = caption_track(seq)
    out: list[Word] = []
    for clip in sorted((c for c in seq.clips if c.track == track and not c.muted), key=lambda c: c.start):
        for t0, t1, text in transcripts.get(clip.media, ()):
            if not clip.source_in <= (t0 + t1) / 2 < clip.source_out:
                continue
            a = clip.start + (max(t0, clip.source_in) - clip.source_in) / clip.speed
            b = clip.start + (min(t1, clip.source_out) - clip.source_in) / clip.speed
            out.append([r3(a), r3(max(a, b)), text])
    return sorted(out, key=lambda w: (w[0], w[1]))


def _ends_sentence(text: str) -> bool:
    return text.rstrip(_CLOSERS).endswith(_TERMINAL)


def pages(words: list[Word], words_per_page: int, max_chars: int) -> list[dict]:
    """Group words into caption pages; a page shows from its first word until shortly after its last."""
    groups: list[list[Word]] = []
    for word in words:
        if groups:
            page = groups[-1]
            prev = page[-1]
            fits = len(" ".join(str(w[2]) for w in page + [word])) <= max_chars
            if len(page) < words_per_page and word[0] - prev[1] <= PAGE_GAP and not _ends_sentence(prev[2]) and fits:
                page.append(word)
                continue
        groups.append([word])
    result = []
    for i, group in enumerate(groups):
        end = group[-1][1] + PAGE_HOLD
        if i + 1 < len(groups):
            end = min(end, groups[i + 1][0][0])
        result.append({"t0": group[0][0], "t1": r3(max(group[0][0], end)), "words": group})
    return result


def page_at(found: list[dict], t: float) -> int:
    for i, page in enumerate(found):
        if page["t0"] <= t < page["t1"]:
            return i
    return -1


def active_word(page: dict, t: float) -> int:
    active = 0
    for i, word in enumerate(page["words"]):
        if word[0] <= t:
            active = i
    return active


def pop_step(caps: ed.Captions, page: dict, active: int, t: float) -> int:
    if caps.style != "pop" or not caps.animate:
        return len(POP_SCALES) - 1
    since = t - page["words"][active][0]
    return min(len(POP_SCALES) - 1, max(0, math.floor(since / POP_STEP + 1e-9)))


def band(caps: ed.Captions, width: int, height: int) -> tuple[int, int]:
    """(top, height) of the transparent caption strip, the full frame width wide."""
    px = max(8, math.floor(caps.size * height + 0.5))
    tall = min(height, 2 * math.ceil(BAND * px / 2))
    top = math.floor(caps.y * height - tall / 2 + 0.5)
    return max(0, min(height - tall, top)), tall


def display(text: str, caps: ed.Captions) -> str:
    return text.upper() if caps.uppercase else text


def wrap(widths: list[float], space: float, limit: float) -> list[list[int]]:
    lines: list[list[int]] = []
    used = 0.0
    for i, w in enumerate(widths):
        if lines and used + space + w <= limit:
            lines[-1].append(i)
            used += space + w
        else:
            lines.append([i])
            used = w
    return lines


def _hex(colour: str, alpha: int = 255) -> tuple[int, int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16), alpha


def draw_state(
    caps: ed.Captions, width: int, height: int, page: dict, active: int, step: int, font_for: Callable
) -> Image.Image:
    """One caption state as a transparent strip (same layout as drawCaptions in the browser)."""
    top, tall = band(caps, width, height)
    image = Image.new("RGBA", (width, tall), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    texts = [display(str(w[2]), caps) for w in page["words"]]
    base_px = max(8, math.floor(caps.size * height + 0.5))
    for factor in SHRINK:
        px = max(8, math.floor(base_px * factor + 0.5))
        font = font_for(px)
        space = font.getlength(" ")
        widths = [font.getlength(t) for t in texts]
        lines = wrap(widths, space, WRAP * width)
        if len(lines) <= MAX_LINES:
            break
    line_h = px * LINE
    first = (tall - len(lines) * line_h) / 2
    stroke = math.floor(caps.stroke * px + 0.5)
    pad = BOX_PAD * px
    if caps.style == "clean":
        wide = max(sum(widths[i] for i in line) + space * (len(line) - 1) for line in lines)
        box = (
            (width - wide) / 2 - pad,
            first - pad / 2,
            (width + wide) / 2 + pad,
            first + len(lines) * line_h + pad / 2,
        )
        draw.rounded_rectangle(box, radius=pad, fill=CLEAN_BACK)
    for row, line in enumerate(lines):
        total = sum(widths[i] for i in line) + space * (len(line) - 1)
        x = (width - total) / 2
        centre_y = first + line_h * (row + 0.5)
        for i in line:
            centre_x = x + widths[i] / 2
            colour, scale, boxed = caps.color, 1.0, False
            if caps.style == "pop" and i == active:
                colour, scale = caps.highlight, POP_SCALES[step]
            elif caps.style == "karaoke" and i <= active:
                colour = caps.highlight
            elif caps.style == "bold" and i == active:
                colour, boxed = BOLD_TEXT, True
            word_font = font if scale == 1.0 else font_for(max(8, math.floor(px * scale + 0.5)))
            if boxed:
                half = widths[i] / 2 + pad
                box = (centre_x - half, centre_y - line_h / 2, centre_x + half, centre_y + line_h / 2)
                draw.rounded_rectangle(box, radius=pad, fill=_hex(caps.highlight))
            draw.text(
                (centre_x, centre_y),
                texts[i],
                font=word_font,
                fill=_hex(colour),
                anchor="mm",
                stroke_width=0 if boxed else stroke,
                stroke_fill=(0, 0, 0, 255),
            )
            x += widths[i] + space
    return image


def fonts_for(key: str) -> Callable:
    cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
    path = font_file(key)

    def get(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if px not in cache:
            cache[px] = ImageFont.truetype(str(path), px) if path else ImageFont.load_default(px)
        return cache[px]

    return get


def render_frames(
    seq: ed.Sequence, found: list[dict], start: float, stop: float, folder: Path, cancel: threading.Event | None = None
) -> int:
    """One PNG per output frame in folder/frames, hardlinked to the drawn PNG of its caption state."""
    caps = seq.captions
    if caps is None:
        raise ed.EditorError("Captions are off.")
    if stop - start > MAX_SECONDS + 1e-6:
        raise ed.EditorError("Captioned exports are limited to 30 minutes. Set In and Out points to export a part.")
    fps = Fraction(ed.FPS_RATES[seq.fps])
    count = max(1, math.ceil((Fraction(stop - start) * fps) - Fraction(1, 10**6)))
    frames, states = folder / "frames", folder / "states"
    frames.mkdir(parents=True, exist_ok=True)
    states.mkdir(parents=True, exist_ok=True)
    top, tall = band(caps, seq.width, seq.height)
    font_for = fonts_for(caps.font)
    drawn: dict[tuple[int, int, int], Path] = {}
    blank = states / "blank.png"
    Image.new("RGBA", (seq.width, tall), (0, 0, 0, 0)).save(blank)
    index = 0
    for n in range(count):
        if cancel is not None and n % 250 == 0 and cancel.is_set():
            raise ed.Cancelled("Export cancelled.")
        t = start + float(n / fps)
        while index < len(found) and found[index]["t1"] <= t:
            index += 1
        source = blank
        if index < len(found) and found[index]["t0"] <= t:
            page = found[index]
            active = -1 if caps.style == "clean" else active_word(page, t)
            step = pop_step(caps, page, max(active, 0), t)
            key = (index, active, step)
            if key not in drawn:
                if len(drawn) >= MAX_STATES:
                    raise ed.EditorError("Too many caption changes to export at once. Export a shorter part.")
                drawn[key] = states / f"{len(drawn):05d}.png"
                draw_state(caps, seq.width, seq.height, page, active, step, font_for).save(drawn[key], optimize=False)
            source = drawn[key]
        target = frames / f"{n:07d}.png"
        try:
            os.link(source, target)
        except OSError:
            shutil.copyfile(source, target)
    return count


def check_export(seq: ed.Sequence, in_out: bool) -> None:
    """Refuse a captioned export over the length limit before it starts."""
    if seq.captions is None or not seq.captions.enabled:
        return
    start, stop = ed.export_range(seq, in_out)
    if stop - start > MAX_SECONDS + 1e-6 and timeline_words(seq, transcripts_for(seq)):
        raise ed.EditorError("Captioned exports are limited to 30 minutes. Set In and Out points to export a part.")


def _stamp(t: float) -> str:
    ms = max(0, math.floor(t * 1000 + 0.5))
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt(found: list[dict]) -> str:
    """SubRip text for caption pages (original casing; times on the timeline's clock)."""
    blocks = []
    for n, page in enumerate(found, 1):
        text = " ".join(str(w[2]) for w in page["words"])
        blocks.append(f"{n}\n{_stamp(page['t0'])} --> {_stamp(page['t1'])}\n{text}\n")
    return "\n".join(blocks)
