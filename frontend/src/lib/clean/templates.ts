export const SLIDERS = [
  ['ai_clean', 'AI cleanup'],
  ['dereverb', 'Classic echo remover'],
  ['demetal', 'Remove metallic tone'],
  ['deharsh', 'Soften harshness'],
  ['warmth', 'Warmth'],
  ['denoise', 'Remove hiss'],
  ['room_tone', 'Natural room tone'],
] as const;

export type SliderKey = (typeof SLIDERS)[number][0];
export type Controls = Record<SliderKey, number>;
export type PresetName = 'light' | 'standard' | 'strong';
export type Presets = Record<PresetName, Controls>;

export type BuiltIn = {
  key: string;
  label: string;
  preset: PresetName;
  description: string;
  overrides: Partial<Controls>;
};
export type SavedTemplate = { name: string; preset: PresetName; settings: Controls };
export type SavedTemplates = Record<string, SavedTemplate>;
export type Template = { preset: PresetName; description: string; settings?: Controls; overrides?: Partial<Controls> };

/** Browser storage key; the Backup page exports it, so the name and JSON shape must not change. */
export const SAVED_KEY = 'naturalvoice.templates.v1';
export const MAX_SAVED = 30;
export const DEFAULT_TEMPLATE = 'ad';
const PRESET_NAMES: readonly string[] = ['light', 'standard', 'strong'];

export const TEMPLATES: readonly BuiltIn[] = [
  {
    key: 'clean',
    label: 'Already clean / preserve the voice',
    preset: 'light',
    description: 'Gentle polish for clips with quiet pauses and little ringing. No AI cleanup or echo removal.',
    overrides: { demetal: 0.25, deharsh: 0.2, warmth: 0.25 },
  },
  {
    key: 'ad',
    label: 'Typical AI ad / balanced cleanup',
    preset: 'standard',
    description: 'AI cleanup with moderate metallic-tone reduction and light echo removal.',
    overrides: {},
  },
  {
    key: 'metallic',
    label: 'Metallic voice / no echo',
    preset: 'light',
    description: 'Target persistent ringing without AI cleanup or echo removal. Keeps dry recordings dry.',
    overrides: { demetal: 0.85, deharsh: 0.4, warmth: 0.35 },
  },
  {
    key: 'echo',
    label: 'Echoey room / clearer speech',
    preset: 'standard',
    description: 'AI cleanup plus stronger echo removal. Check that word endings still sound clear.',
    overrides: { dereverb: 0.6, demetal: 0.4, deharsh: 0.3, warmth: 0.25 },
  },
  {
    key: 'noise',
    label: 'Noisy speech / reduce hiss',
    preset: 'standard',
    description:
      'AI cleanup with a little hiss reduction, without classic echo removal. Listen for softened consonants.',
    overrides: { dereverb: 0, demetal: 0.25, deharsh: 0.2, warmth: 0.25, denoise: 0.2 },
  },
  {
    key: 'strong',
    label: 'Very robotic / strong cleanup',
    preset: 'strong',
    description:
      'More aggressive cleanup for heavily processed clips. Compare with balanced cleanup to avoid a dull voice.',
    overrides: {},
  },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function isControls(value: unknown): value is Controls {
  return (
    isRecord(value) &&
    SLIDERS.every(([k]) => {
      const v = value[k];
      return typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;
    })
  );
}

/** Keeps only valid saved templates (at most 30) from stored JSON; corrupt storage yields none. */
export function parseSaved(raw: string | null): SavedTemplates {
  const saved: SavedTemplates = {};
  let stored: unknown;
  try {
    stored = JSON.parse(raw || '{}');
  } catch {
    return saved;
  }
  if (!isRecord(stored)) return saved;
  for (const [key, value] of Object.entries(stored).slice(0, MAX_SAVED)) {
    if (
      /^saved-[a-z0-9-]+$/.test(key) &&
      isRecord(value) &&
      typeof value.name === 'string' &&
      value.name.length <= 60 &&
      typeof value.preset === 'string' &&
      PRESET_NAMES.includes(value.preset) &&
      isControls(value.settings)
    ) {
      saved[key] = { name: value.name, preset: value.preset as PresetName, settings: value.settings };
    }
  }
  return saved;
}

/** Returns validated presets, or throws when any template's preset lacks a control. */
export function validatePresets(value: unknown): Presets {
  if (!isRecord(value)) throw new Error('Incomplete settings');
  for (const template of TEMPLATES) {
    const preset = value[template.preset];
    if (!isRecord(preset) || !SLIDERS.every(([k]) => Number.isFinite(preset[k])))
      throw new Error('Incomplete settings');
  }
  return value as Presets;
}

export function templateFor(key: string, saved: SavedTemplates): Template | undefined {
  const own = Object.hasOwn(saved, key) ? saved[key] : undefined;
  if (own)
    return {
      preset: own.preset,
      settings: own.settings,
      description: 'Your saved controls. Changes are temporary until saved as a new template.',
    };
  return TEMPLATES.find((t) => t.key === key);
}

export function templateLabel(key: string, saved: SavedTemplates): string {
  const own = Object.hasOwn(saved, key) ? saved[key] : undefined;
  return own ? 'Saved: ' + own.name : (TEMPLATES.find((t) => t.key === key)?.label ?? key);
}

/** Built-in templates never add room tone; saved templates restore exactly what was saved. */
export function settingsFor(template: Template, presets: Presets): Controls {
  return template.settings
    ? { ...template.settings }
    : { ...presets[template.preset], ...template.overrides, room_tone: 0 };
}

export function percent(value: number): string {
  return Math.round(value * 100) + '%';
}
