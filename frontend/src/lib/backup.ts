export const BROWSER_KEYS = ['nv-studio-draft-v1', 'naturalvoice.templates.v1'] as const;
export const MAX_ARCHIVE = 4 * 1024 ** 3 + 32 * 1024 ** 2;

export type RestoreResult = { folder: string; files: number; restart: string };

/** This browser's Clean templates and Studio draft, the only browser values a backup carries. */
export function readBrowserSettings(storage: Storage): Record<string, string> {
  const settings: Record<string, string> = {};
  for (const key of BROWSER_KEYS) {
    const value = storage.getItem(key);
    if (value !== null) settings[key] = value;
  }
  return settings;
}

/** Writes restored values; refuses to overwrite unless allowed, and rolls back if storage fails midway. */
export function applyBrowserSettings(storage: Storage, settings: Record<string, unknown>, replace: boolean): void {
  const keys = BROWSER_KEYS.filter((key) => typeof settings[key] === 'string');
  if (!keys.length) throw new Error('No browser settings in this data folder. Restart with the restored folder first.');
  if (!replace && keys.some((key) => storage.getItem(key) !== null)) {
    throw new Error('Existing browser data kept. Check the replacement box only if you want to replace it.');
  }
  const before = keys.map((key) => storage.getItem(key));
  try {
    for (const key of keys) storage.setItem(key, settings[key] as string);
  } catch (error) {
    keys.forEach((key, i) => {
      const old = before[i];
      if (old === null) storage.removeItem(key);
      else storage.setItem(key, old);
    });
    throw error;
  }
}
