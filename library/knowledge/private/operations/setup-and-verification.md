# Setup and Verification

> Category: Operations | Version: 1.0 | Date: October 2026 | Status: Active

For maintainers setting up a checkout or verifying a change: install commands, how the app and the macOS launcher run, and which checks need which models, ports and data directories.

**Related:**
- [`../architecture/system-overview.md`](../architecture/system-overview.md)
- [`../data/storage-layout.md`](../data/storage-layout.md)
- [`../voices/sample-collections-design.md`](../voices/sample-collections-design.md)
- [`../../../../docs/adr/0001-isolate-the-cloning-engine.md`](../../../../docs/adr/0001-isolate-the-cloning-engine.md)
- [`../../../../docs/adr/0004-isolate-media-analysis-and-version-references.md`](../../../../docs/adr/0004-isolate-media-analysis-and-version-references.md)

Evidence pinned to `dev` at HEAD `0a207b37dc9809791194e8b796c9113351ebfb6e`. No command below was executed while writing this document.

---

## Setup

Voice Studio has three independent Python environments. Installing one never installs another, which is the point of ADR 0001 and ADR 0004.

| Step | Command | What it does |
|---|---|---|
| Main environment | `uv sync` (or `uv sync --locked` for checks) | Python 3.12 app env (`README.md:37`, `README.md:147`) |
| Base models | `scripts/download_models.sh [dir]` | Kokoro, GTCRN, DNSMOS, CAM++ into `models/`, about 385 MB, SHA-256 verified, re-runnable (`scripts/download_models.sh:2-44`) |
| Cloning engine (optional) | `scripts/setup_clone_engine.sh [fp32\|q8\|all]` | `uv sync` in `engines/chatterbox`, then pinned Hugging Face revision models, default fp32 about 3.3 GB (`scripts/setup_clone_engine.sh:4-18`) |
| Media engine (optional) | `scripts/setup_media_engine.sh` | `uv sync --project engines/media --locked`, then `download_media_models.py` (`scripts/setup_media_engine.sh:2-6`) |
| Node tooling | `npm ci --ignore-scripts` | Lint and type tools (`README.md:148`) |

ffmpeg and `uv` must be on `PATH` (`README.md:31`). The media engine also needs Chatterbox for previewing sample versions (`docs/sample-collections.md`, Setup section).

## Running

`uv run voicestudio serve [--host H] [--port P] [--open]` starts uvicorn on `127.0.0.1:8765` by default (`src/naturalvoice/cli.py:78-81`, `src/naturalvoice/cli.py:149-156`). Set `NATURALVOICE_DATA` before starting, since it is read at import (`src/naturalvoice/voices.py:24`). Keep the default host: the sample API refuses non-loopback requests, but the other routers have no such check (see the system overview).

### macOS launcher limits

`desktop/Voice Studio.app` is a bash script, not a bundled app (`desktop/Voice Studio.app/Contents/MacOS/VoiceStudio:1-27`). It resolves the repository two levels above the bundle (`:4-5`), so moving the `.app` alone breaks it. It needs `uv` on a fixed `PATH` list (`:6`, `:11-14`), uses `NATURALVOICE_PORT` defaulting to 8765 (`:7`), treats any responder on `/api/presets` as already running (`:9-10`), starts the server in the background with a 60 second readiness wait (`:16-17`), and logs to `<repo>/data/server.log` regardless of `NATURALVOICE_DATA` (`:15-16`). It opens Chrome, Brave or Edge in app mode, else the default browser (`:23-27`). Models must already be downloaded.

## Verification matrix

| Check | Command | Needs |
|---|---|---|
| Lint | `npm run lint` | Ruff on src, tests, scripts and the three engine scripts; ESLint; ShellCheck (`package.json:5`) |
| Format check | `npm run format:check` | Ruff format, Prettier, shfmt (`package.json:7`) |
| Types | `npm run typecheck` | `web_types.py` and `code_graph.py` drift checks, mypy, three `tsc` configs (`package.json:8`) |
| All static | `npm run check` | The three above, no reformatting (`package.json:9`) |
| Python tests | `uv run --locked pytest -ra` | Models for some tests (below); `slow` marker exists (`pyproject.toml:72`) |

### Tests that skip without prerequisites

| Test | Skip condition |
|---|---|
| `tests/test_clone.py` engine tests | `clone.installed()` false (`tests/test_clone.py:123`, `:195`, `:306`, `:373`) |
| `tests/test_core.py` DNSMOS | `models/dnsmos_sig_bak_ovr.onnx` missing (`tests/test_core.py:150`) |
| `tests/test_core.py` AI clean | `models/gtcrn_simple.onnx` or `bench/refs/af_heart.wav` missing (`tests/test_core.py:173-176`) |
| `tests/test_core.py` offline TTS | `models/kokoro-v1.0.onnx` missing (`tests/test_core.py:276-278`) |
| `tests/test_core.py` UI and JS syntax | Node missing (`tests/test_core.py:22`, `:40`) |
| `tests/test_media_engine.py` | Media engine or Kokoro model missing (`tests/test_media_engine.py:15-16`) |

`tests/test_sample_library.py` monkeypatches `installed` and runs without the media engine (`tests/test_sample_library.py:22`, `:158`). Other test modules have no skip markers found by search; whether they fail without base models is unverified.

### Browser scripts

All drive Chromium through Playwright loaded from `PLAYWRIGHT_MODULE` and need a server you start yourself. They create and modify application data, so start that server with a disposable `NATURALVOICE_DATA`.

| Script | Default URL | Override |
|---|---|---|
| `tests/browser_studio.cjs` | `127.0.0.1:8772` (`:9`) | `NV_URL` |
| `tests/browser_samples.cjs` | `127.0.0.1:8773` (`:6`); header requires disposable data (`:1`) | `NV_URL` |
| `tests/browser_clone.cjs` | `127.0.0.1:8773` hardcoded (`:4`); needs `NV_REF` WAV (`:1`) | none |
| `tests/browser_voicelab.cjs` | `127.0.0.1:8771` (`:9`) | `NV_URL` |
| `tests/browser_stars.cjs` | `127.0.0.1:8765` (`:4`) | `NV_URL` |
| `tests/browser_templates.cjs` | `127.0.0.1:8765` hardcoded (`:11`) | none |
| `tests/browser_workflow.cjs` | `127.0.0.1:8765` hardcoded (`:40`) | none |

Scripts on 8765 collide with a normal running instance and its real data; prefer a separate port with `NV_URL` where supported. `tests/web_templates.cjs` is not a browser script by name; its role was not inspected (unverified).
