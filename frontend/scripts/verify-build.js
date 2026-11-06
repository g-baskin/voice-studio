// Fails when the committed UI build in src/naturalvoice/ui is stale, so the Python app never serves old pages.
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative } from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const committed = fileURLToPath(new URL('../../src/naturalvoice/ui', import.meta.url));

/** @param {string} root */
function files(root) {
  /** @type {Map<string, Buffer>} */
  const found = new Map();
  /** @param {string} dir */
  const walk = (dir) => {
    for (const name of readdirSync(dir).sort()) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else found.set(relative(root, path), readFileSync(path));
    }
  };
  walk(root);
  return found;
}

const temp = mkdtempSync(join(tmpdir(), 'shark-ui-'));
try {
  execFileSync('npx', ['vite', 'build', '--logLevel', 'error'], {
    env: { ...process.env, SHARK_UI_OUT: temp },
    stdio: 'inherit',
  });
  const fresh = files(temp);
  const current = files(committed);
  const stale = [...new Set([...fresh.keys(), ...current.keys()])].filter(
    (name) => !fresh.get(name)?.equals(current.get(name) ?? Buffer.alloc(0)) || !current.has(name),
  );
  if (stale.length) {
    console.error(`UI build is out of date (${stale.length} files). Run: npm run frontend:build`);
    process.exitCode = 1;
  } else console.log(`UI build is current (${fresh.size} files).`);
} finally {
  rmSync(temp, { recursive: true, force: true });
}
