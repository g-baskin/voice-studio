# Interface development

Every Shark Audio page is a SvelteKit 3 page written with Svelte 5 runes, in `frontend/`.

| Address | Source |
|---|---|
| `/` (Clean) | `frontend/src/routes/+page.svelte`, logic in `frontend/src/lib/clean/` |
| `/speak` | `frontend/src/routes/speak/+page.svelte` |
| `/studio` | `frontend/src/routes/studio/` (one component per card), logic in `frontend/src/lib/studio/` |
| `/voice-lab` | `frontend/src/routes/voice-lab/` (cloning panel in `ClonePanel.svelte`), logic in `frontend/src/lib/voicelab/` |
| `/samples` | `frontend/src/routes/samples/+page.svelte`, logic in `frontend/src/lib/samples/` |
| `/backup` | `frontend/src/routes/backup/+page.svelte` |

Old `.html` addresses redirect to these, keeping their query string.

## How it is served

`frontend/` builds with `@sveltejs/adapter-static` into `src/naturalvoice/ui/`. That folder is committed, so
running the app needs only `uv`, not Node. `server.PAGES` maps each clean address to its built page, and
`/_app/*` serves the build's scripts and styles. `src/naturalvoice/web/` keeps the shared assets the pages use:
`app.css`, the icons, the web manifest and the service worker.

Links are full page loads (`data-sveltekit-reload` in `frontend/src/app.html`), as they were before the move:
each page boots fresh, and Studio's autosave on `pagehide` still runs when you leave it.

## Working on it

Install the interface tools once (pinned in `frontend/package-lock.json`):

```sh
npm --prefix frontend ci
```

For live reloading, start the app (`uv run sharkaudio serve`), then in another terminal:

```sh
npm --prefix frontend run dev   # http://localhost:5173, API calls go to the app on port 8765
```

Set `SHARK_API` to use a different app address. Before committing:

```sh
npm run frontend:build   # rewrite src/naturalvoice/ui
npm run frontend:check   # svelte-check, Prettier, and a check that the committed build is current
```

`npm run check` includes `frontend:check`. Keep the element ids, labels and button text the browser suites use;
`npm run test:browser` runs them against the built pages. Clean's template and queue logic is also tested
directly from Node (`tests/web_templates.cjs`).
