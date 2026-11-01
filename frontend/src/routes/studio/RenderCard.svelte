<script lang="ts">
  import { onDestroy, tick } from 'svelte';
  import { errorText, fileUrl, getJson, sendJson } from '#lib/studio/api.ts';
  import { clampNum, fmtDb } from '#lib/studio/logic.ts';
  import type { Studio } from '#lib/studio/studio.svelte.ts';
  import type { RecentRender, RenderJob, RenderResult } from '#lib/studio/types.ts';
  import Status from './Status.svelte';

  let { studio, ready }: { studio: Studio; ready: boolean } = $props();

  const LABELS: Record<string, string> = {
    video: 'Dubbed video',
    mix: 'Full mix',
    stem: 'Stem',
    line: 'Line clip',
    captions: 'Captions',
    timeline: 'Timeline (JSON)',
  };

  let job = $state<string | null>(null);
  let running = $state(false);
  let progress = $state(0);
  let shown = $state<{ id: string; result: RenderResult } | null>(null);
  let caption = $state('');
  let recent = $state<RecentRender[]>([]);
  let player: HTMLAudioElement | undefined = $state();
  let timer: ReturnType<typeof setTimeout> | undefined;

  onDestroy(() => clearTimeout(timer));

  $effect(() => {
    if (ready) void refreshRecent();
  });

  const mix = $derived(shown?.result.files.find((f) => f.kind === 'mix'));
  const videoFile = $derived(shown?.result.files.find((f) => f.kind === 'video'));
  const captions = $derived(shown?.result.captions ?? []);
  const loud = $derived(shown?.result.loudness);
  const fit = $derived(shown?.result.fit ?? null);
  const fitText = $derived.by(() => {
    const res = shown?.result;
    if (!res) return '';
    const bits: string[] = [];
    if (fit)
      bits.push(
        `Fit to time: ${fit.achieved} s of ${fit.target} s target (${fit.met ? 'met' : 'NOT met'}); speech ${fit.speed_factor}× speed, ${fit.stretch}× stretch, pauses ${fit.pause_change >= 0 ? '+' : ''}${fit.pause_change} s.`,
        ...fit.warnings,
      );
    for (const lf of res.line_fits ?? [])
      bits.push(`Line ${lf.line}: ${lf.achieved} s of ${lf.target} s.` + (lf.warning ? ' ' + lf.warning : ''));
    return bits.join(' ');
  });

  function fitSeconds(): number | null {
    const v = studio.opts.fit;
    if (!v) return null;
    return v === 'custom' ? Math.min(3600, Math.max(1, Number(studio.opts.fitCustom) || 30)) : Number(v);
  }

  /** Starts a render; the page's Cmd/Ctrl+Shift+Enter calls this too. */
  export async function render() {
    if (running) return;
    if (!studio.hasText()) {
      studio.say('render', 'Add at least one line with text first.', true);
      return;
    }
    const o = studio.opts;
    const body = {
      project: studio.payload(),
      target: o.target,
      sample_rate: Number(o.rate),
      format: o.format,
      stems: o.stems,
      line_clips: o.clips,
      captions: o.captions,
      polish: o.polish,
      stop_on_error: o.stoperr,
      music_id: o.musicId,
      music_level_db: Number(o.mlevel),
      music_loop: o.loop,
      duck: o.duck,
      duck_db: Number(o.duckdb),
      attack_ms: clampNum(o.attack, 5, 1000),
      release_ms: clampNum(o.release, 20, 3000),
      fade_in: clampNum(o.fadein, 0, 10),
      fade_out: clampNum(o.fadeout, 0, 10),
      room_tone: o.roomtone,
      target_duration: studio.project.mode === 'timed' ? null : fitSeconds(),
      video_id: o.videoId,
      video_mode: o.vmode,
      video_level_db: Number(o.vlevel),
      video_subs: o.vsubs,
    };
    running = true;
    progress = 0;
    studio.say('render', 'Starting render…');
    try {
      const id = (await sendJson<{ job: string }>('/render', body)).job;
      job = id;
      void poll(id);
    } catch (e) {
      running = false;
      studio.say('render', errorText(e), true);
    }
  }

  async function cancel() {
    if (!job) return;
    try {
      await sendJson(`/render/${job}/cancel`, {});
      studio.say('render', 'Cancelling after the current line…');
    } catch (e) {
      studio.say('render', errorText(e), true);
    }
  }

  async function poll(id: string) {
    let s: RenderJob;
    try {
      s = await getJson<RenderJob>(`/render/${id}`);
    } catch (e) {
      studio.say('render', errorText(e), true);
      running = false;
      return;
    }
    progress = Math.round(s.progress * 100);
    if (s.status === 'running') {
      studio.say('render', `${s.step} · ${progress}%`);
      timer = setTimeout(() => void poll(id), 500);
      return;
    }
    running = false;
    if (s.status === 'done' && s.result) {
      studio.say('render', `Rendered ${s.result.duration} s of audio in ${s.result.elapsed} s.`);
      show(id, s.result);
    } else if (s.status === 'cancelled') studio.say('render', 'Render cancelled. Nothing was kept.');
    else studio.say('render', s.error || 'The render failed.', true);
    void refreshRecent();
  }

  function show(id: string, result: RenderResult) {
    shown = { id, result };
    caption = result.captions?.length ? 'Press play to see captions.' : '';
  }

  function onTime() {
    const t = player?.currentTime ?? 0;
    caption = captions.find((x) => t >= x.start && t <= x.end)?.text ?? '';
  }

  async function refreshRecent() {
    try {
      recent = (await getJson<{ renders: RecentRender[] }>('/renders')).renders;
    } catch {
      // The list is a convenience.
    }
  }

  async function reopen(r: RecentRender) {
    const s = await getJson<RenderJob>(`/render/${r.job}`);
    job = r.job;
    if (s.result) show(r.job, s.result);
    await tick();
    player?.focus();
  }
</script>

<section class="card" aria-labelledby="render-h">
  <h2 id="render-h">Render</h2>
  <div class="row">
    <button class="btn" id="render" type="button" disabled={running} onclick={() => void render()}>Render mix</button>
    <button class="btn danger" id="cancel" type="button" hidden={!running} onclick={() => void cancel()}
      >Cancel render</button
    >
  </div>
  <div class="progress" id="bar" hidden={!running}><div style:width={`${progress}%`}></div></div>
  <Status id="render-status" status={studio.status.render} />
  <div id="result" hidden={!shown}>
    <audio
      id="player"
      controls
      preload="auto"
      src={shown && mix ? fileUrl(shown.id, mix.name) : undefined}
      bind:this={player}
      ontimeupdate={onTime}
    ></audio>
    <div class="caption" id="caption" aria-live="off">{caption}</div>
    <p class="meter" id="loud">
      {#if loud}
        {@const m = loud.measured}
        <strong class={loud.met ? 'ok' : 'bad'}>{loud.met ? '✓ Target met. ' : '✗ Target not met. '}</strong
        >{`${loud.target}: ${fmtDb(m.lufs)} LUFS integrated, ${fmtDb(m.true_peak_db)} dBTP true peak, ${fmtDb(m.rms_db)} dB RMS, noise floor ${m.noise_floor_db == null || m.noise_floor_db < -150 ? 'digital silence' : fmtDb(m.noise_floor_db) + ' dB'}. `}<span
          class="hint">{loud.note}</span
        >
      {/if}
    </p>
    <p class="meter" id="fitres" hidden={!fit && !(shown?.result.line_fits ?? []).length}>
      <strong class={fit && !fit.met ? 'bad' : 'ok'}>{fit ? (fit.met ? '✓ ' : '✗ ') : ''}</strong>{fitText}
    </p>
    <!-- svelte-ignore a11y_media_has_caption (captions ride along as the video's soft subtitle track) -->
    <video
      id="vplayer"
      controls
      preload="metadata"
      hidden={!videoFile}
      src={shown && videoFile ? fileUrl(shown.id, videoFile.name) : undefined}
      style="width:100%;max-height:360px;background:#000;border-radius:8px"
    ></video>
    <ul class="plain" id="overlaps">
      {#each shown?.result.overlaps ?? [] as o, k (k)}<li class="error">{o.message}</li>{/each}
    </ul>
    <ul class="plain" id="errors">
      {#each shown?.result.errors ?? [] as e, k (k)}<li class="error">Line {e.line} was skipped: {e.error}</li>{/each}
      {#each (shown?.result.warnings ?? []).slice(0, 10) as w, k (k)}<li class="hint">{w}</li>{/each}
    </ul>
    <h3 style="font-size:1rem">Downloads</h3>
    <ul class="plain" id="files">
      {#if shown}
        <li>
          <strong>Everything (ZIP)</strong><a
            class="btn small"
            href={fileUrl(shown.id, shown.result.zip)}
            download={shown.result.zip}>Download ZIP</a
          >
        </li>
        {#each shown.result.files as f (f.name)}
          <li>
            <span class="wrapword">{`${LABELS[f.kind]}${f.speaker ? ' · ' + f.speaker : ''}: ${f.name}`}</span><a
              class="btn secondary small"
              href={fileUrl(shown.id, f.name)}
              download={f.name}
              aria-label={`Download ${f.name}`}>Download</a
            >
          </li>
        {/each}
      {/if}
    </ul>
  </div>
  <details style="margin-top:12px">
    <summary>Keyboard shortcuts</summary>
    <ul class="hint" id="shortcuts">
      <li><kbd>⌘/Ctrl</kbd> + <kbd>S</kbd>: save project</li>
      <li><kbd>⌘/Ctrl</kbd> + <kbd>Enter</kbd>: preview the line you're in</li>
      <li><kbd>⌘/Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>Enter</kbd>: render the mix</li>
      <li><kbd>Alt</kbd> + <kbd>↑</kbd>/<kbd>↓</kbd>: move the line you're in</li>
    </ul>
  </details>
  <h3 style="font-size:1rem">Renders this session</h3>
  <ul class="plain" id="recent">
    {#each recent as r (r.job)}
      <li>
        <span class="wrapword"
          >{`${r.title} · ${new Date(r.created * 1000).toLocaleTimeString()} · ${r.status}${r.duration ? ` · ${r.duration} s` : ''}`}</span
        >
        {#if r.status === 'done'}
          <button
            type="button"
            class="btn secondary small"
            aria-label={`Show render ${r.title}`}
            onclick={() => void reopen(r)}>Show</button
          >
        {/if}
      </li>
    {:else}
      <li class="hint">None yet.</li>
    {/each}
  </ul>
</section>

<style>
  .progress {
    height: 8px;
    background: var(--line);
    border-radius: 99px;
    overflow: hidden;
    margin: 10px 0;
  }
  .progress div {
    height: 100%;
    background: var(--accent);
    width: 0;
    transition: width var(--motion-progress) var(--motion-easing);
  }
  .caption {
    min-height: 3.2em;
    font-size: 1.15rem;
    font-weight: 600;
    padding: 10px 12px;
    background: var(--bg);
    border-radius: 8px;
    white-space: pre-line;
  }
  kbd {
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 0 4px;
    font: inherit;
    font-size: 0.85rem;
    background: var(--bg);
  }
  .ok {
    color: var(--good);
  }
  .bad {
    color: var(--bad);
  }
</style>
