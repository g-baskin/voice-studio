# Commit: check, review, commit and push

Use this procedure when the user requests a commit. Follow `AGENTS.md` and `CLAUDE.md`.
Work on `dev` by default. Keep CI disabled; these checks run locally. Do not install dependencies,
change branches, publish releases or alter Git configuration without authorization.

1. Run `git status`. Identify only the intended changes; preserve unrelated work and never stage
   credentials, local data, models, caches or generated build output.
2. Run each command separately, without piping its output:
   - `npm run check` — lint, format checking and type checking, including ShellCheck.
   - `uv run --locked pytest -ra` — the complete Python suite, including its Node checks.
   - `uv build` — source distribution and wheel.
   Inspect skips: report unavailable models, cloning integration or other prerequisites explicitly.
   If a tool or dependency is missing, stop and report it rather than silently omitting its check.
3. Fix failing checks without weakening assertions, skipping tests or suppressing real errors.
   For formatting failures, use `npm run format`, then rerun the failed check. Rerun tests after code
   changes. If a failure cannot be fixed, stop before committing and explain why.
4. Run `git status`, `git diff --staged` and `git diff`. Read the complete intended diff, including the
   contents of new files; exclude unrelated files from this commit.
5. Spawn exactly one read-only reviewer with the full intended diff and this brief:

   > Review only this diff for real bugs, regressions, leftover debug code and unintended changes.
   > Score each issue from 0–100 confidence. Pre-existing issues and stylistic nitpicks are false
   > positives. Report only issues at confidence 80 or above, with file:line and a one-line fix.
   > If none, reply CLEAR. Be fast; this is not a deep audit. Do not edit files or modify Git state.

   If a reviewer cannot run, stop and report the unavailable review; do not treat it as CLEAR.
   If CLEAR, continue without asking. Otherwise show verified findings and use one `ask_user`
   choice question with id `land`, offering exactly:
   - **Fix it first, then commit & push** (recommended; keeps the branch green).
   - **Commit & push anyway** (issue stays open in the log).

   If the user picks fix-first, fix the findings and rerun the commands in step 2; no second review
   is required. An unresolved failing check still blocks committing regardless of the review choice.
6. Stage only explicit, relevant filenames using `git add <specific files>` — never `git add -A`.
   Run `git diff --staged --check` and inspect the staged file list before committing.
7. Commit with `git commit -m "<message>"`. Use one concise line starting with Add, Update, Fix,
   Remove or Refactor. Never use `--no-verify`. If a hook fails, fix its cause and rerun it normally.
8. If the current branch has an upstream, run `git push` **in the foreground**. Otherwise report
   that no upstream exists instead of creating one. Never force-push or push directly to protected
   `main`. Report authentication failures without exposing credentials or changing Git settings.
9. Verify the final working-tree and branch status. Report the commit, check results, review outcome,
   push result and any remaining caveats. Do not claim a push or check succeeded without its result.

This agent command is a workflow, not an installed Git hook: a manual `git commit` does not invoke it.
