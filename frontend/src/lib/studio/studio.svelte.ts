import { tick } from 'svelte';
import { DRAFT, toEditor, toPayload } from './logic.ts';
import type {
  EditorProject,
  ProjectInput,
  ProjectPayload,
  RewriteStatus,
  Status,
  StatusKey,
  Style,
  Voice,
} from './types.ts';

export type ExportOptions = {
  target: string;
  rate: string;
  format: string;
  captions: boolean;
  stems: boolean;
  clips: boolean;
  polish: boolean;
  stoperr: boolean;
  roomtone: boolean;
  fit: string;
  fitCustom: number | null;
  musicId: string | null;
  mlevel: number;
  duckdb: number;
  attack: number | null;
  release: number | null;
  fadein: number | null;
  fadeout: number | null;
  duck: boolean;
  loop: boolean;
  videoId: string | null;
  vmode: string;
  vlevel: number;
  vsubs: boolean;
};

/** Shared editor state for the Studio page and its sections. */
export class Studio {
  catalog = $state<Voice[]>([]);
  myStyles = $state<Style[]>([]);
  cloneTags = $state<string[]>([]);
  rewriteStatus = $state<RewriteStatus | null>(null);
  deliveryInfo = $state<Record<string, string>>({});
  project = $state<EditorProject>(toEditor({}));
  projectId = $state<string | null>(null);
  status = $state<Record<StatusKey, Status>>({
    proj: { text: '', bad: false },
    paste: { text: '', bad: false },
    gen: { text: '', bad: false },
    ai: { text: '', bad: false },
    render: { text: '', bad: false },
  });
  opts = $state<ExportOptions>({
    target: 'podcast',
    rate: '24000',
    format: 'wav',
    captions: true,
    stems: false,
    clips: false,
    polish: false,
    stoperr: false,
    roomtone: false,
    fit: '',
    fitCustom: 30,
    musicId: null,
    mlevel: -24,
    duckdb: 12,
    attack: 80,
    release: 400,
    fadein: 1,
    fadeout: 2,
    duck: true,
    loop: true,
    videoId: null,
    vmode: 'replace',
    vlevel: -6,
    vsubs: true,
  });
  /** Line id -> preview object URL; survives reorders and project reloads like the legacy page. */
  previews = new Map<string, string>();
  /** Bumped when the project list should be fetched again (after a save or render). */
  projectsVersion = $state(0);
  recentVersion = $state(0);

  say(key: StatusKey, text: string, bad = false): void {
    this.status[key] = { text, bad };
  }

  payload(): ProjectPayload {
    return toPayload(this.project);
  }

  load(p: ProjectInput): void {
    this.project = toEditor(p);
  }

  saveDraft(): void {
    try {
      localStorage.setItem(DRAFT, JSON.stringify({ projectId: this.projectId, project: this.payload() }));
    } catch {
      // Storage full or blocked.
    }
  }

  hasText(): boolean {
    return this.project.lines.some((l) => l.text.trim());
  }

  /** Focuses an element inside a line card once the DOM reflects the latest change. */
  async focusLine(id: string | undefined, selector = 'textarea'): Promise<void> {
    if (!id) return;
    await tick();
    const card = document.querySelector(`#lines [data-id="${CSS.escape(id)}"]`);
    const target = card?.querySelector<HTMLElement>(selector);
    target?.focus();
  }
}
