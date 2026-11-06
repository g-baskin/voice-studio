import { fmt } from './text.ts';

export type Take = { blob: Blob; seconds: number; name: string };
export type StartResult = 'ok' | 'unsupported' | 'blocked';

const LIMIT = 60;

/** Microphone recording capped at 60 s; always releases the stream when it stops or is disposed. */
export class Recorder {
  #recorder: MediaRecorder | null = null;
  #stream: MediaStream | null = null;
  #tick: ReturnType<typeof setInterval> | undefined;

  get recording(): boolean {
    return this.#recorder?.state === 'recording';
  }

  async start(base: string, onTick: (clock: string) => void, onStop: (take: Take) => void): Promise<StartResult> {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') return 'unsupported';
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      return 'blocked';
    }
    this.#stream = stream;
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream);
    this.#recorder = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    const started = Date.now();
    recorder.onstop = () => {
      this.#release();
      const type = recorder.mimeType || 'audio/webm';
      const ext = type.includes('ogg') ? 'ogg' : type.includes('mp4') ? 'm4a' : 'webm';
      onStop({ blob: new Blob(chunks, { type }), seconds: (Date.now() - started) / 1000, name: `${base}.${ext}` });
    };
    recorder.start();
    onTick('0:00');
    this.#tick = setInterval(() => {
      const s = (Date.now() - started) / 1000;
      onTick(fmt(s));
      if (s >= LIMIT) this.stop();
    }, 250);
    return 'ok';
  }

  stop(): void {
    if (this.recording) this.#recorder?.stop();
  }

  #release(): void {
    clearInterval(this.#tick);
    this.#stream?.getTracks().forEach((t) => t.stop());
    this.#stream = null;
  }

  dispose(): void {
    if (this.#recorder) this.#recorder.onstop = null;
    this.stop();
    this.#release();
  }
}

/** Object URLs keyed by slot; replacing or disposing revokes the old one. */
export class UrlSlots {
  #urls = new Map<string, string>();

  set(slot: string, blob: Blob): string {
    this.revoke(slot);
    const url = URL.createObjectURL(blob);
    this.#urls.set(slot, url);
    return url;
  }

  revoke(slot: string): void {
    const old = this.#urls.get(slot);
    if (old) URL.revokeObjectURL(old);
    this.#urls.delete(slot);
  }

  dispose(): void {
    for (const url of this.#urls.values()) URL.revokeObjectURL(url);
    this.#urls.clear();
  }
}
