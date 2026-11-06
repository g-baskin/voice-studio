import { proxyUrl } from './api.ts';
import { drawCaptions, pageAt } from './captions.ts';
import type { Page } from './captions.ts';
import { dbToGain, pictureAlpha, placement, soundGain, sourceTime } from './timeline.ts';
import type { Captions, Layer, Sequence } from './types.ts';

type Voice = {
  el: HTMLMediaElement;
  gain: GainNode | null;
  node: MediaElementAudioSourceNode | null;
};

const PREROLL = 0.75; // seconds: elements are seeked and paused this early so cuts start on time
const KEEP = 3; // seconds around the playhead that elements stay loaded
const DRIFT = 0.25;
const MAX_SIDE = 960;
// Chrome refuses playbackRate above 16.
const MAX_RATE = 16;

/** One half of the trim view: a clip's frame at a source time. */
export type TrimSide = { layer: Layer; time: number } | null;

/** Captions to draw over the frame, once their font has loaded. */
export type CaptionLayer = { caps: Captions; pages: Page[]; family: string } | null;

/** Canvas preview of the timeline: proxies play in hidden elements and are composited per frame. */
export class Player {
  private pool = new Map<string, Voice>();
  private images = new Map<string, HTMLImageElement>();
  private audio: AudioContext | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private redraw: () => void;
  /** Set by the preview; drawn over the picture layers. */
  captions: CaptionLayer = null;

  constructor(redraw: () => void) {
    this.redraw = redraw;
  }

  attach(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
  }

  destroy() {
    for (const id of [...this.pool.keys()]) this.release(id);
    this.images.clear();
    void this.audio?.close();
    this.audio = null;
    this.canvas = null;
  }

  /** Starts Web Audio; must run inside a user gesture such as pressing Play. */
  unlock() {
    if (!this.audio) this.audio = new AudioContext();
    void this.audio.resume();
    for (const voice of this.pool.values()) this.connect(voice);
  }

  private connect(voice: Voice) {
    if (!this.audio || voice.node) return;
    voice.node = this.audio.createMediaElementSource(voice.el);
    voice.gain = this.audio.createGain();
    voice.gain.gain.value = 0;
    voice.node.connect(voice.gain).connect(this.audio.destination);
    voice.el.muted = false;
  }

  private voice(layer: Layer, key = layer.clip.id): Voice {
    let voice = this.pool.get(key);
    if (!voice) {
      const el = document.createElement(layer.media.kind === 'audio' ? 'audio' : 'video');
      el.preload = 'auto';
      el.muted = true;
      if (el instanceof HTMLVideoElement) el.playsInline = true;
      el.src = proxyUrl(layer.media.id);
      el.addEventListener('seeked', this.redraw);
      el.addEventListener('loadeddata', this.redraw);
      voice = { el, gain: null, node: null };
      this.pool.set(key, voice);
      this.connect(voice);
    }
    return voice;
  }

  private release(id: string) {
    const voice = this.pool.get(id);
    if (!voice) return;
    voice.el.pause();
    voice.el.removeEventListener('seeked', this.redraw);
    voice.el.removeEventListener('loadeddata', this.redraw);
    voice.el.removeAttribute('src');
    voice.el.load();
    voice.node?.disconnect();
    voice.gain?.disconnect();
    this.pool.delete(id);
  }

  private image(id: string): HTMLImageElement {
    let img = this.images.get(id);
    if (!img) {
      img = new Image();
      img.onload = this.redraw;
      img.src = proxyUrl(id);
      this.images.set(id, img);
    }
    return img;
  }

  stopAll() {
    for (const voice of this.pool.values()) voice.el.pause();
  }

  /**
   * Sync every element to time t and draw the frame. `rate` is the shuttle speed: above 0 the elements
   * play at that multiple; below 0 they are paused and seeked to each frame, silently, as media can't
   * play backwards.
   */
  update(seq: Sequence, layers: Layer[], t: number, playing: boolean, rate = 1) {
    const backwards = playing && rate < 0;
    if (backwards) playing = false;
    const live = new Set<string>();
    const speaking = layers.some((l) => l.sound && !l.duck && t >= l.t0 && t < l.t1);
    const duck = speaking ? dbToGain(-seq.duck_db) : 1;
    const now = this.audio?.currentTime ?? 0;
    for (const layer of layers) {
      if (layer.media.kind === 'image') continue;
      if (t < layer.t0 - KEEP || t > layer.t1 + 1) continue;
      live.add(layer.clip.id);
      const voice = this.voice(layer);
      const { el } = voice;
      const active = t >= layer.t0 && t < layer.t1;
      const target = sourceTime(layer, active ? t : layer.t0);
      const gain = active && layer.sound && !backwards ? soundGain(layer, t) * (layer.duck ? duck : 1) : 0;
      voice.gain?.gain.setTargetAtTime(gain, now, layer.duck ? 0.08 : 0.015);
      if (playing && active) {
        const speed = Math.min(MAX_RATE, layer.clip.speed * rate);
        if (el.playbackRate !== speed) el.playbackRate = speed;
        if (el.paused) {
          el.currentTime = target;
          el.play().catch(() => {});
        } else if (Math.abs(el.currentTime - target) > DRIFT * speed) {
          el.currentTime = target;
        }
      } else {
        if (!el.paused) el.pause();
        const near = playing ? t >= layer.t0 - PREROLL : active;
        if (near && !el.seeking && Math.abs(el.currentTime - target) > 0.5 / seq.fps) el.currentTime = target;
      }
    }
    for (const id of [...this.pool.keys()]) if (!live.has(id)) this.release(id);
    this.draw(seq, layers, t);
  }

  /**
   * Two-up trim view: the outgoing frame on the left and the incoming frame on the right, each a
   * half-size copy of the sequence frame. Uses its own elements so one clip can show both its ends.
   */
  trim(seq: Sequence, left: TrimSide, right: TrimSide) {
    const g = this.context(seq);
    if (!g) return;
    const { width: w, height: h } = g.canvas;
    [left, right].forEach((side, i) => {
      if (!side) return;
      const key = `${side.layer.clip.id}:trim-${i}`;
      const frame = { x: (i * w) / 2, y: h / 4, w: w / 2, h: h / 2 };
      let source: CanvasImageSource | null = null;
      if (side.layer.media.kind === 'image') {
        const img = this.image(side.layer.media.id);
        if (img.complete && img.naturalWidth) source = img;
      } else if (side.layer.picture) {
        const { el } = this.voice(side.layer, key);
        if (!el.paused) el.pause();
        if (!el.seeking && Math.abs(el.currentTime - side.time) > 0.5 / seq.fps) el.currentTime = side.time;
        if (el instanceof HTMLVideoElement && el.readyState >= 2) source = el;
      }
      if (!source) return;
      const box = placement(seq, side.layer.clip, side.layer.media);
      g.save();
      g.beginPath();
      g.rect(frame.x, frame.y, frame.w, frame.h);
      g.clip();
      g.drawImage(source, frame.x + box.x * frame.w, frame.y + box.y * frame.h, box.w * frame.w, box.h * frame.h);
      g.restore();
    });
    g.fillStyle = '#5a615d';
    g.fillRect(w / 2 - 1, h / 4, 2, h / 2);
  }

  /** Size the canvas to the sequence and clear it to black. */
  private context(seq: Sequence): CanvasRenderingContext2D | null {
    const canvas = this.canvas;
    if (!canvas) return null;
    const k = Math.min(1, MAX_SIDE / Math.max(seq.width, seq.height));
    const w = Math.round(seq.width * k);
    const h = Math.round(seq.height * k);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    const g = canvas.getContext('2d');
    if (!g) return null;
    g.globalAlpha = 1;
    g.fillStyle = '#000';
    g.fillRect(0, 0, w, h);
    return g;
  }

  private draw(seq: Sequence, layers: Layer[], t: number) {
    const g = this.context(seq);
    if (!g) return;
    const { width: w, height: h } = g.canvas;
    for (const layer of layers) {
      if (!layer.picture || t < layer.t0 || t >= layer.t1) continue;
      let source: CanvasImageSource | null = null;
      if (layer.media.kind === 'image') {
        const img = this.image(layer.media.id);
        if (img.complete && img.naturalWidth) source = img;
      } else {
        const el = this.pool.get(layer.clip.id)?.el;
        if (el instanceof HTMLVideoElement && el.readyState >= 2) source = el;
      }
      if (!source) continue;
      const box = placement(seq, layer.clip, layer.media);
      g.globalAlpha = pictureAlpha(layer, t);
      g.drawImage(source, box.x * w, box.y * h, box.w * w, box.h * h);
    }
    g.globalAlpha = 1;
    const page = this.captions && pageAt(this.captions.pages, t);
    if (this.captions && page) drawCaptions(g, this.captions.caps, page, t, this.captions.family);
  }
}
