# Security audit - 2026-11-01 - backup-browser-tests

## Executive summary

- Scope: backup.py, backup_api.py, Backup page/script, server middleware ordering, browser runner/support and new regression tests.
- Coverage: reduced, feature-specific Python/FastAPI and vanilla JavaScript review. The skill's SvelteKit/Neon guidance does not describe this stack.
- Findings: 0 outstanding Critical, High or Medium findings in this scope.
- Ship Gate status: cleared to proceed to quality review, not approval to commit or ship.
- Independent read-only reviewer: agent 2bedd4f7, SOURCE REVIEW, no high-confidence findings.

## Surface coverage checklist

### SvelteKit attack surface

Not applicable. FastAPI routes require loopback and same-origin requests, behind existing LocalAccess.
RUNTIME: cross-origin and remote-peer requests denied in test_backup.py.

### Authorization and tenancy (Drizzle / Neon)

No database or tenant model. Only the local owner can reach backup routes. No arbitrary restore destination
is accepted: a new owner-only folder is allocated beside the data directory. Existing data is not overwritten.

### Secrets and environment

SOURCE REVIEW and RUNTIME: export allowlist excludes llm.json and access-token. Browser keys are allowlisted.
The test runner replaces application data and temporary paths, and removes inherited provider credentials.

### Webhooks and third-party intake

No webhooks. ZIP intake validates names, entry types, duplicates, file count, expanded size, manifest and
checksums. RUNTIME tests reject traversal, symlinks, case collisions and corrupted checksums.
Checksums are integrity evidence, not archive authentication. UI says to restore only trusted archives.

### Dependencies and supply chain

No dependencies added or installed. Dependency vulnerability scanning was not part of this feature review.

### Headers and transport

Backup export sends no-store. All backup operations remain loopback-only, including when the app allows
network-token sessions. ZIPs are unencrypted; the UI and guide explicitly warn about private recordings.

### AI-generated code patterns

SOURCE REVIEW and RUNTIME: request write gate plus shared audio semaphore prevent app writes during export.
Tests cover overlap and recovery after disk failure. Archive restore cleanup targets only its newly allocated
folder. Single-server and no external filesystem writer assumptions are stated in the UI and docs.

### PII and logging hygiene

No archive contents or credentials are logged. Browser artifacts use generated fixtures, separate data and
owner-only parent folders. Artifact paths are printed; artifacts persist for inspection, not uploaded.

## Findings detail

No outstanding medium-or-higher findings. During implementation, fixed export's processing-lock release on
temporary-directory creation failure and enforced the same manifest-size bound on export and restore.
Regression tests cover both. No whole-application security verdict is claimed.

## Remediation summary

No open medium-or-higher findings after implementation corrections and the independent review.

## Re-evaluation

RUNTIME: 17 targeted Python tests passed after corrections. Backup browser download/restore, consent,
malformed ZIP and mobile-reflow tests passed. The independent reviewer read the corrected candidate.
Not checked: hostile local OS, multiple server processes sharing data, dependency CVEs or real-user backups.

## Next step

Proceed to quality review and full local verification. Commit/push still need the user's explicit approval.

## Final candidate supplement

Candidate pin: `backup-browser-tests/2026-11-01-candidate.json` (reports excluded from its subject set).
Quality review found test-harness gaps, not new product archive vulnerabilities: disabled Ollama discovery,
disabled uv synchronization/downloads, strengthened browser-value assertions and added a real restored-server
restart. Independent re-review 9364c63e checked isolation first and returned CLEAR.
The added `.gitignore` rule protects restored private data under the checkout; its regression test passes.
Final runtime evidence is in `backup-browser-tests/2026-11-01-verification.json`: all nine browser suites
pass, 208 current non-slow tests pass, and the five unchanged slow tests passed in the earlier full run.
The 1.08 MB disposable restore drill took 0.0107 seconds and preserved the original/post-backup canary.
No real-user library recovery time or off-device backup configuration is claimed.
