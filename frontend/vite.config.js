import { fileURLToPath } from 'node:url';
import process from 'node:process';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import pkg from './package.json' with { type: 'json' };

// The Python app serves this build; SHARK_UI_OUT lets the freshness check build elsewhere.
const out = process.env.SHARK_UI_OUT ?? fileURLToPath(new URL('../src/naturalvoice/ui', import.meta.url));
const api = process.env.SHARK_API ?? 'http://127.0.0.1:8765';
// Shared assets the Python app serves from src/naturalvoice/web.
const SHARED = ['/app.css', '/icon.svg', '/favicon-32.png', '/apple-touch-icon.png', '/manifest.webmanifest'];
const LEGACY = new Set(SHARED);

export default defineConfig({
  plugins: [
    sveltekit({
      adapter: adapter({ pages: out, assets: out, strict: true }),
      // A fixed version keeps builds reproducible; the local app never needs update polling.
      version: { name: pkg.version, pollInterval: 0 },
      prerender: {
        handleHttpError: ({ path, message }) => {
          if (!LEGACY.has(path)) throw new Error(message);
        },
      },
    }),
  ],
  server: { proxy: Object.fromEntries(['/api', ...SHARED].map((path) => [path, api])) },
});
