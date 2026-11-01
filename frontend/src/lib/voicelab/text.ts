export const LANG_CODES: [string, string][] = [
  ['a', 'American English'],
  ['b', 'British English'],
  ['e', 'Spanish'],
  ['f', 'French'],
  ['h', 'Hindi'],
  ['i', 'Italian'],
  ['p', 'Brazilian Portuguese'],
  ['j', 'Japanese'],
  ['z', 'Mandarin Chinese'],
];

export const CLONE_SCRIPT =
  'The morning was quiet, and the coffee was still too hot to drink. I opened the window, listened to ' +
  'the birds, and thought about the long list of things I wanted to finish today. First, a short walk by the river. ' +
  'Then a call with an old friend, and maybe, if the weather holds, dinner outside on the porch.';

export const PREVIEW_MAX = 500;

/** Minutes and seconds, e.g. 1:05. */
export const fmt = (s: number): string => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

/** Inserts a tag at a selection with surrounding spaces; null when it would exceed the length limit. */
export function insertTag(
  value: string,
  start: number,
  end: number,
  tag: string,
  max = PREVIEW_MAX,
): { value: string; caret: number } | null {
  const before = value.slice(0, start);
  const after = value.slice(end);
  const ins = (before && !/\s$/.test(before) ? ' ' : '') + tag + (after && !/^\s/.test(after) ? ' ' : '');
  if ((before + ins + after).length > max) return null;
  return { value: before + ins + after, caret: start + ins.length };
}

export function kindLabel(kind: string): string {
  return kind === 'stock' ? 'Stock' : kind === 'clone' ? 'Clone' : 'Mine';
}
