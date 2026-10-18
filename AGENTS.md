# Coding agents

Read `CLAUDE.md` for workflow and behavior details, `CONTEXT.md` for domain terms, and relevant records in `docs/adr/` before architecture changes.

- Install: `uv sync --locked` (Python 3.12); install ffmpeg and run `scripts/download_models.sh` before audio tests.
- Build: `uv build`.
- Test: `uv run --locked pytest -ra`. Optional cloning integration tests require `scripts/setup_clone_engine.sh`; inspect reported skips.
- Quality tools: install Node 22.13+ (22.x), ShellCheck and shfmt; run `npm ci --ignore-scripts` after `uv sync --locked`.
- Check locally: `npm run check` (lint, format check and type check); individual commands are `npm run lint`, `npm run format:check` and `npm run typecheck`. Apply formatting with `npm run format`.
- After HTML ID/tag changes, run `uv run python scripts/web_types.py --write` to refresh checked DOM declarations.
- CI lives in `.github/workflows/ci.yml` but is disabled at the owner's request. Keep checks local; do not re-enable CI without approval.
- For commit requests, follow `.gg/commands/commit.md`: local checks, tests, build and a read-only review before staging/committing.
- Never commit with `--no-verify`.
