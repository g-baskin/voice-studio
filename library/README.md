---
ai_description: |
  Documentation library, schema v2. Read the folder README before writing.
  knowledge/ holds reference and audience explanations; requirements/ holds
  PRDs; issues/ holds IRDs. notes/ is human-only: do not read, write, summarize,
  or cite its contents. Keep generated binary packet files outside library/.
  Shared CTR records live in knowledge/private/contracts/.
human_description: |
  Start here to find product plans, issue plans, and reference documents.
  Public knowledge is approved for external readers; private knowledge is
  for the team. Notes are unmaintained human scratch material.
---

# Library

This library holds the sources that explain the repository, its product plans, and its decisions. Schema version: **v2**.

Read each folder's README before adding a document. The full schema is in [`knowledge/private/standards/documentation-framework.md`](knowledge/private/standards/documentation-framework.md).

## Find a document

| Folder | What goes here |
| --- | --- |
| [`knowledge/public/`](knowledge/public/README.md) | Approved product overviews, public briefs, user guides, and FAQs |
| [`knowledge/private/`](knowledge/private/README.md) | Internal engineering and business knowledge, ADRs, shared CTR contracts, and standards |
| [`requirements/`](requirements/README.md) | Product requirements documents (PRDs), grouped by backlog, in-work, and completed |
| [`issues/`](issues/README.md) | Issue requirements documents (IRDs), using the same lifecycle |
| `notes/` | Human-only scratch space; agents do not read or write here |

## Prepare the sources or explain them to readers

App Primer Zero prepares a repository before implementation. When available, use it to record current state, organize private knowledge, draft shared contracts and the foundation plan, and prepare a bounded handoff. A Draft plan or contract does not grant implementation approval.

Library Packets turns supported sources into documents for founders, investors, sales, service, account teams, public readers, or engineers. Each selected document has Markdown, editable Word, branded PDF, and citations. These are audience explanations and decision briefs; they can go beyond help guides. The workflow reports missing source coverage rather than filling gaps with invented facts.

Use these workflows only when installed and needed. A team can maintain this library without them. Check the source, intended readers, public exclusions, and output location before generating a packet.

## Source documents and generated files

Keep curated Markdown sources in the proper knowledge domain. Keep brand assets, rendered sites, Word files, PDFs, and other build outputs outside `library/`, at the agreed output location. Edit the source and regenerate outputs instead of editing a generated mirror. Authored wiki Markdown belongs under `knowledge/`; a wiki export is a generated mirror.

A public packet contains only approved reader documents, safe citations, and approved visuals. Keep source paths, quotes, hashes, gaps, and review records in its private `_internal` area. Exclude that area from public delivery. Folder placement alone does not authorize publication.
