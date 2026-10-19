---
ai_description: |
  Shared interface agreements live here as CTR-<###>-<slug>.md.
  The contract author records the user's acceptance of an exact revision.
  The requirements author pins accepted revisions in affected PRDs.
  Draft or disputed terms do not clear dependent implementation.
human_description: |
  Stable agreements shared by feature plans. Each CTR names its provider,
  consumers, behavior, approval, and checks. These are interface contracts,
  not legal agreements.
---

# Contracts

One CTR records one shared, observable boundary. The contract author drafts the terms and records the user's acceptance of the exact revision. The requirements author pins accepted revisions in each affected PRD under `## Contract dependencies` and keeps those links current as PRD folders move.

Use `CTR-<###>-<slug>.md` with the next unused number. Accepted terms stay immutable. Changed terms receive a new CTR number with links between the old and new records. Keep records here when PRDs move between lifecycle folders.

Draft text is not an accepted agreement. App Primer Zero can prepare Draft records or pin existing Accepted revisions; its output does not supply approval. Legal agreements belong elsewhere.
