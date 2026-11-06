# Build and release guide

Shark Audio currently ships as a source checkout, not a hosted service or standalone installer.
The macOS app starts the engine in that checkout. Python wheels/source distributions are build artifacts;
they do not bundle ffmpeg, model downloads, a Python runtime or the optional cloning environment.
Do not advertise them as standalone desktop installs.

## Clean-checkout setup and checks

The tested platform is Intel macOS with Python 3.12. Linux and Windows remain unverified.
Install Git, [uv](https://docs.astral.sh/uv/) and [ffmpeg](https://ffmpeg.org/) first.
The build commands below were checked with uv 0.9.13. Allow space for the Python dependencies in addition
to the roughly 385 MB of base models; optional cloning adds about 3.3 GB of models.
No API keys are required for local use.

```sh
git clone https://github.com/g-baskin/voice-studio.git
cd voice-studio
git switch dev
uv sync --locked
uv lock --check
uv lock --check --project engines/chatterbox
uv run --locked pytest -q tests/test_release.py
scripts/download_models.sh
uv run --locked pytest -q
uv run --locked voicestudio serve --open
```

For a release candidate, check out the exact reviewed commit instead of continuing on a moving branch.
The root `.python-version` selects Python 3.12. Keep both `uv.lock` files in Git; `--locked` fails rather
than silently updating dependencies. The cloning engine has its own version and is not the product version.
To exercise cloning, run `scripts/setup_clone_engine.sh` and repeat the tests; without it, cloning integration
tests may skip. Review skips before claiming complete verification.

Run `shellcheck scripts/*.sh` with ShellCheck installed. Browser tests require Node, Playwright with Chromium
and a running server; see the README and each `tests/browser_*.cjs` header for their commands. Do not count
Python tests alone as a browser or cross-platform check. Model downloads and generation tests write files
and can take several minutes.

## Build and inspect the Python artifacts

From the reviewed checkout:

```sh
uv build
```

This builds an sdist and a wheel into `dist/`; by default uv builds the wheel from the sdist, checking that
its inputs are present there. The backend is `uv_build` as declared in `pyproject.toml`. With uv 0.9.13 it uses
the bundled backend fast path. Record the uv version used when preparing a release.

For source version 0.3.0, inspect the artifacts with:

```sh
python3 -m zipfile -l dist/voice_studio-0.3.0-py3-none-any.whl
python3 -m tarfile -l dist/voice_studio-0.3.0.tar.gz
shasum -a 256 dist/voice_studio-0.3.0-py3-none-any.whl dist/voice_studio-0.3.0.tar.gz
```

Use the actual version in filenames after a bump. Verify that the wheel contains `naturalvoice/web/`
(including HTML, JS, CSS, icons and the web manifest), `voicelab_features.json`, `voicelab_embeddings.npz`,
license metadata and both `voicestudio`/`naturalvoice` command entry points. Check package metadata and
`naturalvoice/__init__.py` agree on the version. Never include `.env`, user audio, `data/`, `.venv/` or downloaded
model directories. An artifact build alone does not prove a fresh install works: run the clean-checkout setup
above and the app checks on the target platform before releasing.

## Version and changelog policy

- `pyproject.toml` is the authoritative product version. Match it in `src/naturalvoice/__init__.py` and both
  `CFBundleVersion` and `CFBundleShortVersionString` in `desktop/Voice Studio.app/Contents/Info.plist`.
- After changing the package version, run `uv lock` intentionally and review the lock diff. Do not upgrade
  dependencies incidentally. `tests/test_release.py` checks the runtime, lock and both desktop versions.
- While the project is pre-1.0, use patch increments for compatible fixes and minor increments for new features
  or breaking changes. Clearly label breaking changes and migration steps in the changelog.
- Add user-facing changes under `[Unreleased]` in [CHANGELOG.md](../CHANGELOG.md). Do not invent past releases:
  the initial repository snapshot was already version 0.3.0 and no release tags existed when this guide was added.

## Manual release checklist (only with explicit approval)

No workflow publishes automatically. Normal development and pushes to `dev` are **not** releases.

1. Choose the version, align the version files, update the lock, and promote the relevant changelog entries
   to a dated version heading. Keep an `[Unreleased]` section for subsequent changes.
2. Run the checks and artifact inspection above from a clean candidate checkout. Record the commit, tool
   versions, test results and any skipped/platform checks. Keep secrets and generated user data out of Git.
3. Review and merge the approved candidate from `dev` into `main`. Verify the exact `main` commit and rebuild
   artifacts there; don't select stale artifacts from an earlier version in `dist/`.
4. Only after approval, create an annotated `vX.Y.Z` tag at that verified commit and push that specific tag.
   Run Git pushes in the foreground.
5. Create a GitHub Release for the existing tag using the changelog entry as notes. Describe the supported
   source-checkout installation and its model/ffmpeg prerequisites, and list untested platforms. Attach only
   the verified artifacts and their SHA-256 checksums if distributing Python artifacts.
6. Verify the public tag, release notes and downloads match the reviewed commit/version. Never move an
   existing release tag; fix mistakes with a new version and clearly mark an unusable release in its notes.

These are maintainer instructions, not authorization to create a tag, publish a release or upload to PyPI.
