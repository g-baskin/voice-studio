# Repo health: pre-commit pass for feature/clip-mode

**Data collection:** local clone plus `gh` CLI.
**Coverage:** a scoped pre-commit hygiene pass for this change, not the full eight-dimension audit.
- **Not assessed:** branch protection, CODEOWNERS and repository settings. No overall score is reported.
- **CI:** intentionally disabled by the owner (`AGENTS.md`), so CI density was not assessed.

## Findings

- **Secrets:** a pattern scan of every changed and new text file outside the generated build (API keys, tokens, `sk-`, `ghp_`, AWS keys, private key headers) matched nothing.
- **Debug leftovers:** no `console.log`, `debugger`, `breakpoint()` or stray `print(` on added lines. `git diff --check` is clean.
- **Staged-file hygiene:**
  - **By path:** files are staged by explicit path.
  - **Excluded:** the untracked `models` symlink (to the main checkout's models) is left out on purpose.
  - **Largest files:** the regenerated code graph (244 KB) and one generated UI bundle (143 KB); the project commits both on purpose.
  - **No data:** no media, models or local data are included.
- **Commit convention:** one imperative "Add ..." line, matching the history and `.gg/commands/commit.md`.
- **PR target:** this branch stacks on `feature/editor` (PR #18, which targets `feature/svelte-pages`), so the PR base is `feature/editor`, not `main`. Retarget it after #18 merges.
- **Templates:** there is still no PR template in `.github/`. Low: recommendation only.
