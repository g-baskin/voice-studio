# Coding agents

Read `CLAUDE.md` for workflow and behavior details, `CONTEXT.md` for domain terms, and relevant records in `docs/adr/` before architecture changes.

- After HTML ID/tag changes, run `uv run python scripts/web_types.py --write` to refresh checked DOM declarations.
- CI lives in `.github/workflows/ci.yml` but is disabled at the owner's request. Keep checks local; do not re-enable CI without approval.
- For commit requests, follow `.gg/commands/commit.md`: local checks, tests, build and a read-only review before staging/committing.

<!-- gg:init:start -->
## Voice Studio

Local voice production: clean recordings, render scripts and timed dubs, and design or clone voices; cloud speech providers are optional. The product/distribution is `voice-studio`, but the Python package remains `naturalvoice` and both CLI names are supported for compatibility.

## Boundaries and invariants

- Custom voices are Kokoro vectors; cloned voices are reference recordings consumed by Chatterbox. Matching a recording within stock-voice space is not cloning. Keep these categories distinct in storage and UI terminology.
- Chatterbox runs in its own Python 3.12 environment through a persistent JSON-lines subprocess. Do not merge its dependencies into the main environment: root ONNX Runtime is pinned to 1.19.2 for Intel-Mac wheels, while the engine independently pins 1.23.2.
- The media engine (`engines/media`: speaker detection, background separation, YouTube download) is a third isolated Python 3.12 environment with its own `uv.lock`. Never merge its dependencies into the root or Chatterbox environments.
- The sample library API accepts only loopback hosts and same-origin requests. It is not a multi-user authenticated API.
- `access.LocalAccess` guards the whole app: loopback peer and host by default; `serve` with a non-loopback host adds an access token (cookie), saved owner-only in `DATA_DIR/access-token` until `serve --new-token`. Tests that run `serve` must point `voices.DATA_DIR` at a temporary folder. Cross-site writes and API reads are always refused. Test clients must use `base_url="http://127.0.0.1", client=("127.0.0.1", 50000)`.
- Reference versions are immutable: each build saves a new cloned voice. Never overwrite or replace earlier versions or source recordings.
- Voice Lab's shipped embeddings are fingerprint-validated, but the local `stock_features_v{FEATURE_VERSION}.npz` cache is not and overrides shipped entries. Feature-semantic changes need local-cache versioning too; rebuilding shipped embeddings alone leaves stale results.
- Timed dubbing preserves explicit cue starts and reports overlaps rather than cutting speech or shifting later cues. Fitting is capped at a 1.2 speed factor; captions follow placed audio (`tests/test_studio.py`).
- ACX mastering adds room tone deliberately: default tests require a noise floor above -75 dB and at most -60 dB. Do not remove it as unwanted noise; disabling room tone is a separate option.
- Release versions must agree across `pyproject.toml`, the root package entry in `uv.lock`, `naturalvoice.__version__`, and both desktop plist version fields (`tests/test_release.py`). The cloning engine has an independent version.

## Runtime and verification prerequisites

- Audio work needs ffmpeg and base models from `scripts/download_models.sh`. Optional cloning requires `scripts/setup_clone_engine.sh` separately; root dependency installation does not install the engine, and its integration tests can skip when absent.
- Optional sample collections require `scripts/setup_media_engine.sh` (locked `uv sync` of `engines/media` plus hash-checked model downloads). Root installation does not install it.
- Browser checks are standalone scripts, not the manifest checks. For Studio, start `uv run voicestudio serve --port 8772`, then run `PLAYWRIGHT_MODULE=/path/to/playwright node tests/browser_studio.cjs` with an existing Chromium installation. Set `NATURALVOICE_DATA` to disposable storage before starting the server: these checks write application data. Other browser scripts use different ports; inspect their URL settings rather than assuming 8772.
- The macOS `.app` is a checkout-relative shell launcher, not a self-contained distribution: it needs `uv`, the surrounding repository and separately downloaded models. Moving only the app bundle breaks that relationship.
<!-- gg:init:end -->
