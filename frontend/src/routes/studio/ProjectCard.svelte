<script lang="ts">
  import { errorText, getJson, sendJson, api } from '#lib/studio/api.ts';
  import { newLine } from '#lib/studio/logic.ts';
  import type { Studio } from '#lib/studio/studio.svelte.ts';
  import type { ProjectRecord, ProjectSummary } from '#lib/studio/types.ts';
  import Status from './Status.svelte';

  let { studio, ready }: { studio: Studio; ready: boolean } = $props();

  let projects = $state<ProjectSummary[] | null>(null);
  let choice = $state('');

  const label = (p: ProjectSummary) =>
    `${p.title} · ${p.lines} lines` + (p.updated ? ` · ${new Date(p.updated * 1000).toLocaleString()}` : '');

  async function refresh(select?: string) {
    try {
      projects = (await getJson<{ projects: ProjectSummary[] }>('/projects')).projects;
      choice = select || studio.projectId || '';
    } catch (e) {
      studio.say('proj', 'Could not list projects: ' + errorText(e), true);
    }
  }

  $effect(() => {
    if (ready) void refresh();
  });

  /** Saves the project; the page's Cmd/Ctrl+S calls this too. */
  export async function save() {
    studio.say('proj', 'Saving…');
    try {
      const body = studio.payload();
      const rec = studio.projectId
        ? await sendJson<ProjectRecord>(`/projects/${studio.projectId}`, body, 'PUT')
        : await sendJson<ProjectRecord>('/projects', body);
      studio.projectId = rec.id;
      await refresh(rec.id);
      studio.say('proj', `Saved “${rec.project.title}” at ${new Date().toLocaleTimeString()}.`);
    } catch (e) {
      studio.say('proj', 'Not saved: ' + errorText(e), true);
    }
  }

  async function open() {
    const id = choice;
    if (!id) {
      studio.say('proj', 'Choose a project to open.', true);
      return;
    }
    try {
      const rec = await getJson<ProjectRecord>(`/projects/${id}`);
      studio.projectId = rec.id;
      studio.load(rec.project);
      studio.say('proj', `Opened “${rec.project.title}”.`);
    } catch (e) {
      studio.say('proj', errorText(e), true);
    }
  }

  async function duplicate() {
    const id = choice || studio.projectId;
    if (!id) {
      studio.say('proj', 'Save or choose a project to duplicate.', true);
      return;
    }
    try {
      const rec = await sendJson<ProjectRecord>(`/projects/${id}/duplicate`, {});
      studio.projectId = rec.id;
      studio.load(rec.project);
      await refresh(rec.id);
      studio.say('proj', `Made a copy: “${rec.project.title}”.`);
    } catch (e) {
      studio.say('proj', errorText(e), true);
    }
  }

  async function remove() {
    const id = choice;
    const p = projects?.find((x) => x.id === id);
    if (!id || !p) {
      studio.say('proj', 'Choose a saved project to delete.', true);
      return;
    }
    if (!confirm(`Delete “${label(p)}”? This can't be undone.`)) return;
    try {
      await api(`/projects/${id}`, { method: 'DELETE' });
      if (studio.projectId === id) studio.projectId = null;
      await refresh();
      studio.say('proj', 'Project deleted. The script on screen is still here; save it to keep it.');
    } catch (e) {
      studio.say('proj', errorText(e), true);
    }
  }

  function fresh() {
    if (studio.hasText() && !confirm('Start a new project? Unsaved changes on screen will be lost.')) return;
    studio.projectId = null;
    studio.load({ title: 'Untitled project', lines: [newLine()] });
    studio.say('proj', 'New project.');
  }
</script>

<section class="card" aria-labelledby="proj-h">
  <h2 id="proj-h">Project</h2>
  <div class="grid">
    <div class="field">
      <label for="title">Title</label><input id="title" type="text" maxlength="120" bind:value={studio.project.title} />
    </div>
    <div class="field">
      <label for="mode">Placement</label><select id="mode" bind:value={studio.project.mode}>
        <option value="sequential">Sequential (one line after another)</option>
        <option value="timed">Timed (dubbing): each line at its start time</option></select
      >
    </div>
    <div class="field">
      <label for="projects">Saved projects</label><select id="projects" bind:value={choice}>
        {#if projects === null}
          <option value="">Loading…</option>
        {:else}
          <option value="">{projects.length ? 'Choose a project…' : 'No saved projects yet'}</option>
          {#each projects as p (p.id)}<option value={p.id}>{label(p)}</option>{/each}
        {/if}
      </select>
    </div>
  </div>
  <div class="row" style="margin-top:10px">
    <button class="btn" id="save" type="button" onclick={() => void save()}>Save project</button>
    <button class="btn secondary" id="load" type="button" onclick={() => void open()}>Open</button>
    <button class="btn secondary" id="dup" type="button" onclick={() => void duplicate()}>Duplicate</button>
    <button class="btn danger" id="del" type="button" onclick={() => void remove()}>Delete</button>
    <button class="btn secondary" id="newp" type="button" onclick={fresh}>New project</button>
  </div>
  <Status id="proj-status" status={studio.status.proj} />
</section>
