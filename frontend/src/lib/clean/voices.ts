export type CatalogVoice = {
  id: string;
  name: string;
  kind: string;
  language?: string;
  gender?: string;
  starred?: boolean;
};
export type VoiceGroup = { label: string; voices: { id: string; text: string }[] };

const GROUPS = [
  ['stock', 'Stock voices'],
  ['custom', 'My voices'],
  ['clone', 'Cloned voices'],
] as const;

function text(v: CatalogVoice): string {
  return v.kind === 'stock' ? `${v.name} (${v.language}, ${v.gender})` : v.name;
}

function group(v: CatalogVoice): string {
  return v.kind === 'stock' ? 'stock' : v.kind === 'clone' ? 'clone' : 'custom';
}

/** Starred voices first, then stock, custom and cloned groups; empty groups are left out. */
export function voiceGroups(catalog: readonly CatalogVoice[]): VoiceGroup[] {
  const groups: VoiceGroup[] = [];
  const starred = catalog.filter((v) => v.starred);
  if (starred.length)
    groups.push({ label: '\u2605 Starred', voices: starred.map((v) => ({ id: v.id, text: text(v) })) });
  for (const [kind, label] of GROUPS) {
    const items = catalog.filter((v) => group(v) === kind);
    if (items.length) groups.push({ label, voices: items.map((v) => ({ id: v.id, text: text(v) })) });
  }
  return groups;
}

/** The first starred voice when there is one, otherwise af_heart, otherwise the first listed. */
export function defaultVoice(catalog: readonly CatalogVoice[]): string {
  const starred = catalog.find((v) => v.starred);
  if (starred) return starred.id;
  const groups = voiceGroups(catalog);
  const all = groups.flatMap((g) => g.voices);
  return all.find((v) => v.id === 'af_heart')?.id ?? all[0]?.id ?? 'af_heart';
}
