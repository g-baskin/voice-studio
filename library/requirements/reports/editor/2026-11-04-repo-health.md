# Repo health: pre-commit pass for feature/editor

**Data collection:** local clone plus `gh` CLI (account g-baskin, `repo` scope).
**Coverage:** a scoped pre-commit hygiene pass for this change, not the full eight-dimension audit. Not assessed: branch protection, CODEOWNERS and repository settings. No overall score is reported. CI is intentionally disabled by the owner (`AGENTS.md`), so CI density was not assessed.

## Findings

- **Secrets:** a pattern scan of every changed and new text file outside the generated build matched nothing.
- **Staged-file hygiene:** commits are staged by explicit path. The largest new file is a 79 KB generated bundle in `src/naturalvoice/ui/_app/`, which the project commits on purpose. No media, models or local data are included.
- **.gitignore:** Editor data lives under `data/` (`.gitignore:21`), and exports go to the system temp folder. Low: `models/` and `node_modules/` match directories only, so a symlink with either name shows up as untracked. Recommendation only; nothing was changed.
- **Commit convention:** the history uses one-line, imperative "Add/Fix ..." messages (`.gg/commands/commit.md`). This commit follows that style.
- **PR target:** `feature/editor` goes into `feature/svelte-pages`, which builds on `dev` and is not on GitHub until this push. The default branch is `main`, and the PR does not target it.
- **Templates:** there is no PR template in `.github/`. Low: recommendation only.
