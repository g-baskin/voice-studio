# Repository health gate: shark-audio

**Mode:** local clone plus `gh` for PR creation only; no repository settings queried or changed.
**Scope:** changed-file hygiene for this feature, not a whole-repository score.

- Docs: README, docs/speak.md and docs/frontend.md describe the new page, build steps and attribution limits.
- .gitignore: `.svelte-kit/` added at root; `frontend/.gitignore` covers its `node_modules` and `.svelte-kit`. The committed build lives in `src/naturalvoice/ui` so the app runs with `uv` alone; `npm run frontend:check` fails when it is stale.
- Dependencies: frontend devDependencies pinned exactly with a lockfile; no Python dependency changes.
- CI: unchanged and still disabled, per the owner's instruction.
- Branching: isolated worktree and feature branch; PR into `dev`; merging needs separate approval.
- Not assessed: branch protection, CODEOWNERS, repository settings.
