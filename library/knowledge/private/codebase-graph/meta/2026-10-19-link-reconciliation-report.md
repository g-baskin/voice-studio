---
type: meta
title: "Link reconciliation report 2026-10-19"
created: 2026-10-19
updated: 2026-10-19
tags:
  - meta
status: developing
---

# Link reconciliation report (update mode, HEAD 0a207b37dc9809791194e8b796c9113351ebfb6e)

Before: 101 dangling wikilinks to 25 targets across chunks A, B, C. After: 0.

## Convention

All links are written `entities/<page>` or `concepts/<page>` inside double square brackets (folder prefix always present). Module pages are `<module-stem>-module` (existing stems kept, e.g. `clone_api-module`, `llm-api-module`); symbol pages are `<module-stem>-<symbol>`. Symbols without their own page link to their module page. Test files are cited as plain code paths, not wikilinks.

## Mapping

| Old target | New |
|---|---|
| cli-module, entities/cli-module, entities/cli-clean-file | entities/cli-main |
| entities/clone-speak | entities/clone-module |
| entities/clone_api-router | entities/clone_api-module |
| entities/llm_api-router | entities/llm-api-module |
| entities/quality-to-16k | entities/quality-dnsmos |
| entities/rewrite_api-router, rewrite-api-module | entities/rewrite-module |
| entities/scriptgen_api-router, scriptgen-api-module | entities/scriptgen-module |
| entities/sample_library_api-router, entities/sample_library_api-sampleuploadlimit | entities/sample_library_api-module |
| entities/server-module, server-module | entities/server-app |
| entities/studio_api-router | entities/studio-api-module |
| entities/voicelab_api-router | entities/voicelab_api-module |
| entities/voices-catalog, entities/voices-resolve | entities/voices-module |
| entities/tts-model-dir, tts-module, entities/tts-module | entities/tts-module (new page) |
| entities/web-index-html | unchanged (new page) |
| entities/tests-test-core | `tests/test_core.py` (plain text) |
| entities/tests-test-workflow | `tests/test_workflow.py` (plain text) |

## Pages created

- `entities/tts-module.md`
- `entities/web-index-html.md`

## Side effects

- `entities/cli-main.md` now links to itself where it previously linked `cli-clean-file` (clean_file is documented on that page).
- `entities/server-app.md` depends_on lists `sample_library_api-module` twice (router and SampleUploadLimit).
