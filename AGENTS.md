# Coding agents

Read `CLAUDE.md` for workflow and behavior details, `CONTEXT.md` for domain terms, and relevant records in `docs/adr/` before architecture changes.

- Install: `uv sync --locked` (Python 3.12); install ffmpeg and run `scripts/download_models.sh` before audio tests.
- Build: `uv build`.
- Test: `uv run --locked pytest -ra`. Optional cloning integration tests require `scripts/setup_clone_engine.sh`; inspect reported skips.
- Shell lint: `shellcheck scripts/*.sh`. No Python lint/typecheck command is currently configured.
- CI lives in `.github/workflows/ci.yml` and must stay green; it runs on Ubuntu only, without the optional cloning engine or browser automation.
- Never commit with `--no-verify`.
