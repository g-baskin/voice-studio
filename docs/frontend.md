# Interface development

Shark Audio's pages are moving from plain HTML (`src/naturalvoice/web/`) to SvelteKit 3 with Svelte 5 runes
(`frontend/`). The Python app serves both, so the move happens one page at a time.

| Address | Source |
|---|---|
| `/speak` | SvelteKit: `frontend/src/routes/speak/+page.svelte` |
| `/backup` | SvelteKit: `frontend/src/routes/backup/+page.svelte` |
| `/`, `/studio`, `/voice-lab`, `/samples` | Plain HTML in `src/naturalvoice/web/` (not migrated yet) |

Old `.html` addresses redirect to these, keeping their query string.

## How it is served

`frontend/` builds with `@sveltejs/adapter-static` into `src/naturalvoice/ui/`. That folder is committed, so
running the app needs only `uv`, not Node. `server.PAGES` maps each clean address to its HTML file, and
`/_app/*` serves the build's scripts and styles. SvelteKit pages reuse the shared `app.css` and icons from
`src/naturalvoice/web/`, so both kinds of page look the same during the move.

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

`npm run check` includes `frontend:check`.

## Moving a page

1. Add `frontend/src/routes/<name>/+page.svelte` using runes (`$state`, `$derived`, `$props`), keeping element
   IDs the browser checks rely on.
2. Point its `server.PAGES` entry at `UI / "<name>.html"`, remove the old HTML and script, and mark the nav entry
   in `frontend/src/lib/nav.ts` as `svelte: true`.
3. Remove the page from `scripts/web_types.py`, rebuild, and run its browser suite with `npm run test:browser`.
