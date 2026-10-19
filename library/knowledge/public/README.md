---
ai_description: |
  Knowledge approved for external readers: product overviews, public briefs,
  guides, and FAQs. Use only facts cleared for this audience. Keep private
  architecture, source paths, credentials, strategy, and review notes out.
  Folder placement is not permission to publish. Use the standard knowledge
  header: Category / Version / Date / Status.
human_description: |
  Documents that explain the product to approved external audiences.
  These include public briefs and overviews as well as help guides.
  Check the owner's disclosure rules before adding or sharing content.
---

# Knowledge: Public

This area holds product explanations approved for external readers. It can contain a public brief, a feature overview, a user guide, or a FAQ.

## Common domains

| Folder | Contents |
| --- | --- |
| `overview/` | Product purpose, glossary, feature explanations, and public briefs |
| `guides/` | Steps that help users complete a task |
| `faqs/` | Answers to common customer questions |

Add another domain only when the team has approved its public scope.

## Write for the reader

Explain supported benefits and behavior in plain language. General explanations target grade 8. Avoid unnecessary implementation detail, buzzwords, and claims without evidence. Keep internal architecture, pricing strategy, competitive research notes, security details, and private source paths in `knowledge/private/`.

Library Packets, when available, turns approved sources into reader Markdown, Word, PDF, and citations. Its public citation list contains public URLs or approved safe source labels. Its full source map, quotes, hashes, gaps, and page review stay in the packet's private `_internal` area. Keep generated binaries outside `library/` and exclude private evidence from public archives.

Writing a public document does not authorize publishing or sending it.
