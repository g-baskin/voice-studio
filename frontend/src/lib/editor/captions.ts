import { silenceCuts } from './timeline.ts';
import type { SilenceCut } from './timeline.ts';
import type { Captions, Clip, Sequence, Word } from './types.ts';

// Layout numbers shared with src/naturalvoice/captions.py; change both together.
const PAGE_GAP = 0.6;
const PAGE_HOLD = 0.3;
const POP_STEP = 0.04;
const POP_SCALES = [1.22, 1.12, 1.06];
const LINE = 1.15;
const BAND = 3.2;
const WRAP = 0.9;
const MAX_LINES = 2;
const SHRINK = [1, 0.9, 0.8, 0.7, 0.6, 0.5];
const BOX_PAD = 0.16;
const CLEAN_BACK = 'rgba(0, 0, 0, 0.588)';
const BOLD_TEXT = '#111111';

export const DEFAULT_CAPTIONS: Captions = {
  enabled: true,
  track: null,
  style: 'pop',
  font: 'sans-bold',
  size: 0.06,
  y: 0.72,
  words_per_page: 3,
  max_chars: 24,
  uppercase: true,
  color: '#ffffff',
  highlight: '#ffd400',
  stroke: 0.12,
  animate: true,
};

/** A caption page: the words shown together, from t0 until t1, on the timeline's clock. */
export type Page = { t0: number; t1: number; words: Word[] };

/** Same rounding as the export, so pages match it exactly. */
const r3 = (v: number) => Math.floor(v * 1000 + 0.5) / 1000;
const chars = (s: string) => [...s].length;
const endsSentence = (text: string) => /[.?!…]$/.test(text.replace(/["')\]”’]+$/, ''));

/** The track captions follow: the chosen one, else the first unmuted audio track that has clips. */
export function captionTrack(seq: Sequence): string | null {
  if (seq.captions?.track) return seq.captions.track;
  // Audio tracks first; then video tracks, whose clips carry their own sound until it is detached.
  const used = (kind: string) =>
    seq.tracks.find((t) => t.kind === kind && !t.muted && seq.clips.some((c) => c.track === t.id && !c.muted));
  return (used('audio') ?? used('video'))?.id ?? null;
}

/** Transcript words of every unmuted clip on the caption track, on the timeline's clock. */
export function timelineWords(seq: Sequence, transcripts: Record<string, Word[] | undefined>): Word[] {
  const trackId = captionTrack(seq);
  const out: Word[] = [];
  const clips = seq.clips.filter((c) => c.track === trackId && !c.muted).sort((a, b) => a.start - b.start);
  for (const c of clips)
    for (const [t0, t1, text] of transcripts[c.media] ?? []) {
      const mid = (t0 + t1) / 2;
      if (mid < c.source_in || mid >= c.source_out) continue;
      const a = c.start + (Math.max(t0, c.source_in) - c.source_in) / c.speed;
      const b = c.start + (Math.min(t1, c.source_out) - c.source_in) / c.speed;
      out.push([r3(a), r3(Math.max(a, b)), text]);
    }
  return out.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
}

/** Group words into pages: a new page at the word limit, a long gap, a sentence end or the character limit. */
export function pages(words: Word[], perPage: number, maxChars: number): Page[] {
  const groups: Word[][] = [];
  for (const word of words) {
    const page = groups.at(-1);
    if (page) {
      const prev = page.at(-1)!;
      const fits = chars([...page, word].map((w) => w[2]).join(' ')) <= maxChars;
      if (page.length < perPage && word[0] - prev[1] <= PAGE_GAP && !endsSentence(prev[2]) && fits) {
        page.push(word);
        continue;
      }
    }
    groups.push([word]);
  }
  return groups.map((group, i) => {
    let end = group.at(-1)![1] + PAGE_HOLD;
    const next = groups[i + 1];
    if (next) end = Math.min(end, next[0][0]);
    return { t0: group[0][0], t1: r3(Math.max(group[0][0], end)), words: group };
  });
}

export function pageAt(found: Page[], t: number): Page | null {
  return found.find((p) => p.t0 <= t && t < p.t1) ?? null;
}

export const pageText = (page: Page | null) => (page ? page.words.map((w) => w[2]).join(' ') : '');

export function activeWord(page: Page, t: number): number {
  let active = 0;
  page.words.forEach((w, i) => {
    if (w[0] <= t) active = i;
  });
  return active;
}

function popStep(caps: Captions, page: Page, active: number, t: number): number {
  const last = POP_SCALES.length - 1;
  if (caps.style !== 'pop' || !caps.animate) return last;
  const since = t - page.words[active][0];
  return Math.min(last, Math.max(0, Math.floor(since / POP_STEP + 1e-9)));
}

/** [top, height] of the caption strip in a frame of this size. */
export function band(caps: Captions, height: number): [number, number] {
  const px = Math.max(8, Math.floor(caps.size * height + 0.5));
  const tall = Math.min(height, 2 * Math.ceil((BAND * px) / 2));
  const top = Math.floor(caps.y * height - tall / 2 + 0.5);
  return [Math.max(0, Math.min(height - tall, top)), tall];
}

function wrap(widths: number[], space: number, limit: number): number[][] {
  const lines: number[][] = [];
  let used = 0;
  widths.forEach((w, i) => {
    const line = lines.at(-1);
    if (line && used + space + w <= limit) {
      line.push(i);
      used += space + w;
    } else {
      lines.push([i]);
      used = w;
    }
  });
  return lines;
}

/** Draw the caption page shown at time t over the frame (same layout as the export). */
export function drawCaptions(g: CanvasRenderingContext2D, caps: Captions, page: Page, t: number, family: string) {
  const { width, height } = g.canvas;
  const [top, tall] = band(caps, height);
  const texts = page.words.map((w) => (caps.uppercase ? w[2].toUpperCase() : w[2]));
  const active = caps.style === 'clean' ? -1 : activeWord(page, t);
  const step = popStep(caps, page, Math.max(active, 0), t);
  const base = Math.max(8, Math.floor(caps.size * height + 0.5));
  const font = (px: number) => `${px}px "${family}", sans-serif`;
  let px = base;
  let widths: number[] = [];
  let space = 0;
  let lines: number[][] = [];
  let stroke = 0;
  const peak = caps.style === 'pop' ? POP_SCALES[0] : 1;
  for (const factor of SHRINK) {
    px = Math.max(8, Math.floor(base * factor + 0.5));
    g.font = font(px);
    stroke = Math.floor(caps.stroke * px + 0.5);
    // Outlines sit outside the glyphs, so the gap keeps a full space between them.
    space = g.measureText(' ').width + 2 * stroke;
    widths = texts.map((s) => g.measureText(s).width);
    // Wrap as if every word were popped, so lines stay put while the highlight moves.
    lines = wrap(
      widths.map((w) => w * peak),
      space,
      WRAP * width,
    );
    if (lines.length <= MAX_LINES) break;
  }
  const slots = widths.map((w, i) => (i === active ? w * peak : w));
  const lineH = px * LINE;
  const first = top + (tall - lines.length * lineH) / 2;
  const pad = BOX_PAD * px;
  const lineWidth = (line: number[]) => line.reduce((sum, i) => sum + slots[i], 0) + space * (line.length - 1);
  g.save();
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.lineJoin = 'round';
  if (caps.style === 'clean') {
    const wide = Math.max(...lines.map(lineWidth));
    g.fillStyle = CLEAN_BACK;
    g.beginPath();
    g.roundRect((width - wide) / 2 - pad, first - pad / 2, wide + 2 * pad, lines.length * lineH + pad, pad);
    g.fill();
  }
  lines.forEach((line, row) => {
    let x = (width - lineWidth(line)) / 2;
    const cy = first + lineH * (row + 0.5);
    for (const i of line) {
      const cx = x + slots[i] / 2;
      let colour = caps.color;
      let scale = 1;
      let boxed = false;
      if (caps.style === 'pop' && i === active) [colour, scale] = [caps.highlight, POP_SCALES[step]];
      else if (caps.style === 'karaoke' && i <= active) colour = caps.highlight;
      else if (caps.style === 'bold' && i === active) [colour, boxed] = [BOLD_TEXT, true];
      g.font = font(scale === 1 ? px : Math.max(8, Math.floor(px * scale + 0.5)));
      if (boxed) {
        g.fillStyle = caps.highlight;
        g.beginPath();
        g.roundRect(cx - widths[i] / 2 - pad, cy - lineH / 2, widths[i] + 2 * pad, lineH, pad);
        g.fill();
      } else if (stroke > 0) {
        g.strokeStyle = '#000';
        g.lineWidth = stroke * 2;
        g.strokeText(texts[i], cx, cy);
      }
      g.fillStyle = colour;
      g.fillText(texts[i], cx, cy);
      x += slots[i] + space;
    }
  });
  g.restore();
}

/** Source spans of the chosen words, joining neighbours into one span. */
export function wordSpans(words: Word[], indices: number[]): [number, number][] {
  const spans: [number, number][] = [];
  let lastIndex = -2;
  for (const i of [...new Set(indices)].sort((a, b) => a - b)) {
    const w = words[i];
    if (!w) continue;
    const last = spans.at(-1);
    if (last && i === lastIndex + 1) last[1] = Math.max(last[1], w[1]);
    else spans.push([w[0], w[1]]);
    lastIndex = i;
  }
  return spans;
}

/** Timeline cuts that remove the chosen words from these clips (and their linked picture or sound). */
export const wordCuts = (clips: Clip[], words: Word[], indices: number[]): SilenceCut[] =>
  silenceCuts(clips, wordSpans(words, indices), 0, 1e-3);

/** Timeline cuts that remove source spans (pauses or possible fillers) from these clips. */
export const gapCuts = (clips: Clip[], spans: [number, number][]): SilenceCut[] => silenceCuts(clips, spans, 0, 1e-3);

/** Source spans that shorten each pause between words longer than `longer` down to `keep` seconds. */
export function pauseSpans(words: Word[], longer: number, keep: number): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 1; i < words.length; i++) {
    const a = words[i - 1][1];
    const b = words[i][0];
    if (b - a <= Math.max(longer, keep)) continue;
    out.push([r3(a + keep / 2), r3(b - keep / 2)]);
  }
  return out;
}
