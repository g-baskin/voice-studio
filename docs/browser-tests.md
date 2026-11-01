# Local browser checks

Run all browser suites with:

```sh
npm run test:browser
```

Prerequisites: the root Python environment, ffmpeg, base voice/cleanup models, an existing Playwright Node
module and its Chromium binary. The full suite also requires the separately installed cloning and media
engines. The runner does not install anything, silently skip suites, enable CI or use your running app.
If Playwright is not a local dependency, point to an existing installation:

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright npm run test:browser
```

Run selected suites when working on a smaller surface:

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/node_modules/playwright npm run test:browser -- backup motion templates
```

Available suites: backup, clone, motion, samples, stars, studio, templates, voicelab, workflow.
Missing browser/model/engine prerequisites fail the affected run. A selected subset is not a full-suite pass.

Each suite gets its own data directory, temporary audio workspace, screenshots, browser log and server log.
A pre-bound ephemeral loopback socket prevents attaching to your real server or racing for a fixed port.
The runner removes inherited paid-provider credentials and disables automatic Ollama discovery in its test server. It generates synthetic reference/performance clips
for cloning instead of requiring personal recordings. Test servers are stopped by their exact child process;
the cloning worker is stopped on normal server shutdown.

The printed artifact folder is retained on success and failure, including disposable data and any restored
folders. `results.json` lists requested and passed suites; screenshots capture final pages even after an
assertion fails. These artifacts are synthetic but can be large; remove a particular printed folder yourself
when no longer needed. No broad temporary-directory cleanup is performed.

For isolated worktrees sharing already-installed assets, set `NATURALVOICE_MODELS`,
`NATURALVOICE_CLONE_ENGINE`, and `NV_TEST_MEDIA_ENGINE` to those existing directories. These are read-only
model/engine inputs, not your application data folder. The media override is specific to the test launcher.

The scripts can still run individually with `NV_URL`, but only the runner guarantees disposable server/data
isolation. Never point a standalone script at your real app: some tests create and delete fixtures.
