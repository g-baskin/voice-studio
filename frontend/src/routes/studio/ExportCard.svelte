<script lang="ts">
  import { api, errorText } from '#lib/studio/api.ts';
  import type { Studio } from '#lib/studio/studio.svelte.ts';

  let { studio }: { studio: Studio } = $props();

  const o = $derived(studio.opts);
  let videoName = $state('none');
  let musicName = $state('none');
  let videoInput: HTMLInputElement | undefined = $state();
  let musicInput: HTMLInputElement | undefined = $state();

  function syncTarget() {
    const acx = o.target === 'acx';
    o.roomtone = acx;
    if (acx) {
      o.rate = '44100';
      o.format = 'mp3';
    }
  }

  async function upload<T>(path: string, f: File): Promise<T> {
    const fd = new FormData();
    fd.append('file', f);
    return (await (await api(path, { method: 'POST', body: fd })).json()) as T;
  }

  async function music(input: HTMLInputElement) {
    const f = input.files?.[0];
    if (!f) return;
    if (f.size > 200 * 1024 * 1024) {
      musicName = 'too large (200 MB max)';
      input.value = '';
      return;
    }
    musicName = 'uploading…';
    try {
      const r = await upload<{ music_id: string; name: string; seconds: number }>('/music', f);
      o.musicId = r.music_id;
      musicName = `${r.name} (${r.seconds} s)`;
    } catch (e) {
      o.musicId = null;
      musicName = errorText(e);
      input.value = '';
    }
  }

  async function video(input: HTMLInputElement) {
    const f = input.files?.[0];
    if (!f) return;
    if (f.size > 2 * 1024 ** 3) {
      videoName = 'too large (2 GB max)';
      input.value = '';
      return;
    }
    videoName = 'uploading…';
    try {
      const r = await upload<{ video_id: string; name: string; seconds: number; has_audio: boolean }>('/video', f);
      o.videoId = r.video_id;
      videoName = `${r.name} (${r.seconds} s${r.has_audio ? '' : ', no audio'})`;
    } catch (e) {
      o.videoId = null;
      videoName = errorText(e);
      input.value = '';
    }
  }
</script>

<section class="card" aria-labelledby="exp-h">
  <h2 id="exp-h">Export</h2>
  <div class="grid">
    <div class="field">
      <label for="target">Delivery target</label><select id="target" bind:value={o.target} onchange={syncTarget}>
        <option value="youtube">YouTube / streaming (−14 LUFS, −1 dBTP)</option>
        <option value="podcast">Podcast (−16 LUFS, −1 dBTP)</option>
        <option value="broadcast">Broadcast EBU R128 (−23 LUFS, −1 dBTP)</option>
        <option value="acx">Audiobook ACX (RMS −23…−18 dB, peak ≤ −3 dB)</option>
        <option value="raw">Raw (levels untouched)</option></select
      >
    </div>
    <div class="field">
      <label for="rate">Sample rate</label><select id="rate" bind:value={o.rate}>
        <option value="24000">24 kHz (voice's native rate)</option><option value="44100">44.1 kHz</option><option
          value="48000">48 kHz (video)</option
        ></select
      >
      <span class="hint">Resampling matches a delivery spec; it doesn't add detail.</span>
    </div>
    <div class="field">
      <label for="format">Format</label><select id="format" bind:value={o.format}>
        <option value="wav">WAV 24-bit</option><option value="flac">FLAC (lossless, smaller)</option><option value="mp3"
          >MP3 320 kbps</option
        ></select
      >
    </div>
  </div>
  <div class="row" style="margin-top:12px">
    <label><input type="checkbox" id="captions" bind:checked={o.captions} /> Captions (SRT + VTT)</label>
    <label><input type="checkbox" id="stems" bind:checked={o.stems} /> Stems per speaker</label>
    <label><input type="checkbox" id="clips" bind:checked={o.clips} /> Clip per line</label>
    <label><input type="checkbox" id="polish" bind:checked={o.polish} /> Polish voice (light de-metal + warmth)</label>
    <label><input type="checkbox" id="stoperr" bind:checked={o.stoperr} /> Stop if any line fails</label>
    <label><input type="checkbox" id="roomtone" bind:checked={o.roomtone} /> Room tone in pauses (−65 dBFS)</label>
  </div>
  <div class="grid" style="margin-top:12px">
    <div class="field">
      <label for="fit">Fit to time</label><select id="fit" bind:value={o.fit}>
        <option value="">Off (natural length)</option><option value="15">15 s spot</option><option value="30"
          >30 s spot</option
        >
        <option value="60">60 s spot</option><option value="custom">Custom length…</option></select
      >
      <span class="hint"
        >Speeds speech up or down within 0.85–1.2×, fine-tunes with a time-stretch, then adjusts pauses. Warns instead
        of going further.</span
      >
    </div>
    <div class="field" id="fit-custom-f" hidden={o.fit !== 'custom'}>
      <label for="fit-custom">Custom length (s)</label><input
        id="fit-custom"
        type="number"
        min="1"
        max="3600"
        step="0.5"
        bind:value={o.fitCustom}
      />
    </div>
  </div>
  <details style="margin-top:14px" id="video-box">
    <summary>Dub a video <span class="hint" id="video-name">{videoName}</span></summary>
    <div class="field" style="margin-top:8px">
      <label for="video"
        >Video file <span class="hint">MP4, MOV, WebM, MKV · 2 GB max · picture is copied untouched</span></label
      >
      <input
        id="video"
        type="file"
        accept=".mp4,.mov,.webm,.mkv,video/*"
        bind:this={videoInput}
        onchange={(e) => void video(e.currentTarget)}
      />
    </div>
    <div class="row" style="margin-top:6px">
      <button
        class="btn secondary small"
        id="video-clear"
        type="button"
        hidden={!o.videoId}
        onclick={() => {
          o.videoId = null;
          if (videoInput) videoInput.value = '';
          videoName = 'none';
          videoInput?.focus();
        }}>Remove video</button
      >
    </div>
    <div class="grid" style="margin-top:8px">
      <div class="field">
        <label for="vmode">Original audio</label><select id="vmode" bind:value={o.vmode}>
          <option value="replace">Replace with the dub</option><option value="duck"
            >Keep it, ducked under the dub</option
          ></select
        >
      </div>
      <div class="field">
        <label for="vlevel">Original level <span class="num" id="vlevel-v">{o.vlevel} dB</span></label><input
          id="vlevel"
          type="range"
          min="-40"
          max="6"
          step="1"
          bind:value={o.vlevel}
        />
      </div>
    </div>
    <label style="display:block;margin-top:8px"
      ><input type="checkbox" id="vsubs" bind:checked={o.vsubs} /> Add captions as a soft subtitle track (nothing burned in)</label
    >
    <p class="hint">The dub runs the full length of the video. Ducking uses the music-bed depth, attack and release.</p>
  </details>
  <details style="margin-top:14px">
    <summary>Music bed <span class="hint" id="music-name">{musicName}</span></summary>
    <div class="field" style="margin-top:8px">
      <label for="music"
        >Music file <span class="hint">WAV, FLAC, MP3, M4A, AAC, OGG, Opus, AIFF · 200 MB max</span></label
      >
      <input
        id="music"
        type="file"
        accept=".wav,.flac,.mp3,.m4a,.aac,.ogg,.opus,.aiff,.aif,audio/*"
        bind:this={musicInput}
        onchange={(e) => void music(e.currentTarget)}
      />
    </div>
    <div class="row" style="margin-top:6px">
      <button
        class="btn secondary small"
        id="music-clear"
        type="button"
        hidden={!o.musicId}
        onclick={() => {
          o.musicId = null;
          if (musicInput) musicInput.value = '';
          musicName = 'none';
          musicInput?.focus();
        }}>Remove music</button
      >
    </div>
    <div class="grid" style="margin-top:8px">
      <div class="field">
        <label for="mlevel">Music level <span class="num" id="mlevel-v">{o.mlevel} dB</span></label><input
          id="mlevel"
          type="range"
          min="-40"
          max="0"
          step="1"
          bind:value={o.mlevel}
        />
      </div>
      <div class="field">
        <label for="duckdb">Duck under speech <span class="num" id="duckdb-v">{o.duckdb} dB</span></label><input
          id="duckdb"
          type="range"
          min="0"
          max="30"
          step="1"
          bind:value={o.duckdb}
        />
      </div>
      <div class="field">
        <label for="attack">Duck attack (ms)</label><input
          id="attack"
          type="number"
          min="5"
          max="1000"
          step="5"
          bind:value={o.attack}
        />
      </div>
      <div class="field">
        <label for="release">Duck release (ms)</label><input
          id="release"
          type="number"
          min="20"
          max="3000"
          step="10"
          bind:value={o.release}
        />
      </div>
      <div class="field">
        <label for="fadein">Fade in (s)</label><input
          id="fadein"
          type="number"
          min="0"
          max="10"
          step="0.5"
          bind:value={o.fadein}
        />
      </div>
      <div class="field">
        <label for="fadeout">Fade out (s)</label><input
          id="fadeout"
          type="number"
          min="0"
          max="10"
          step="0.5"
          bind:value={o.fadeout}
        />
      </div>
    </div>
    <div class="row" style="margin-top:8px">
      <label><input type="checkbox" id="duck" bind:checked={o.duck} /> Auto-duck</label>
      <label><input type="checkbox" id="loop" bind:checked={o.loop} /> Loop short music (otherwise it stops)</label>
    </div>
  </details>
</section>

<style>
  .num {
    font-weight: 600;
    font-size: 0.95rem;
  }
</style>
