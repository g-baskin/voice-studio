# PRD-001d: Storage and request boundaries *(Retroactive)*

> **Status:** Shipped. Parent: [PRD-001](./prd-001-voice-sample-collections-index.md)

## Data model

Under `NATURALVOICE_DATA/sample-library/{sources,people,samples}/<32-hex id>/record.json` (`src/naturalvoice/sample_library.py:37-50`). JSON is published atomically via temp file, fsync and replace (`:53-63`; `tests/test_sample_library.py:284`). Writes are serialized by an `fcntl` lock file (`:80-89`). Budget 2 GB with a 1 GB free-space reserve (`:31-32`, `92-100`; `tests/test_sample_library.py:165`). Reference WAVs live in the existing voices store (`:359`).

## Request boundary

Every route requires a loopback peer and localhost host, rejects foreign `Origin`, and rejects `sec-fetch-site: cross-site` (`src/naturalvoice/sample_library_api.py:23-34`, `83`). Upload size is bounded in ASGI middleware before multipart parsing (`:37-80`) and again while streaming (`:166-175`). Only unaccepted uploads are deleted on failure (`:197-200`). This is not authentication.

## Endpoints (`src/naturalvoice/sample_library_api.py`)

| Method and path | Line |
|---|---|
| GET `/api/samples` | 115 |
| POST `/api/samples/sources` (202) | 126 |
| GET `/api/samples/sources/{key}` | 208 |
| POST `/api/samples/sources/{key}/retry` (202) | 214 |
| GET `/api/samples/sources/{key}/audio/{original or dialogue}` | 236 |
| POST `/api/samples/people` (201) | 250 |
| GET `/api/samples/people/{key}` | 256 |
| POST `/api/samples/people/{key}/samples` (201) | 275 |
| GET `/api/samples/audio/{key}` | 281 |
| POST `/api/samples/people/{key}/versions` (201) | 292 |
| POST `/api/samples/people/{key}/active` | 302 |

Errors map to 404/400/507 (`:86-95`).
