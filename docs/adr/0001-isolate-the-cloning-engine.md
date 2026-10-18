---
status: accepted
---

# 0001 — Isolate the Chatterbox-Turbo cloning engine

Recorded: 2026-10-18. This is a retrospective record of the existing implementation, not a new architecture
change or a claim about the original decision date. The evidence is the cloning guide and the code/configuration
linked below; alternatives listed in that guide were not benchmarked unless explicitly stated there.

## Context and Problem Statement

Voice Studio needs local, CPU-based voice cloning alongside Kokoro speech on Intel macOS. The main environment
pins ONNX Runtime 1.19.2 for that platform. The Chatterbox-Turbo ONNX model needs operations unsupported by that
runtime: the cloning guide reports a `GroupQueryAttention softcap` load failure. The cloning environment uses
ONNX Runtime 1.23.2 instead.

Sharing one interpreter would tie both engines to one runtime version. Changing the current split would affect
installation, model loading, process lifecycle and the request/response protocol, not merely a package name.

## Considered Options

The following options summarize the documented constraints, not an invented account of past deliberations:

- **Chatterbox-Turbo ONNX in a separate environment and persistent worker:** the implemented option. Keeps the
  main runtime pin while allowing a different runtime for cloning, at the cost of a second environment and IPC.
- **Chatterbox-Turbo in the main environment:** the existing runtime cannot load the model. Upgrading that runtime
  would require revisiting the main app's Intel-macOS compatibility constraint; this record does not claim that
  a shared-runtime upgrade has been tested.
- **Other cloning engines:** the guide lists XTTS-v2, F5-TTS, NeuTTS Air, Zonos and OpenVoice V2 as unbenchmarked
  candidates, with licensing, dependency or quality concerns. Those notes are not comparative test results.

## Decision Outcome

Keep Chatterbox-Turbo's ONNX implementation in its own project-local Python environment, called through a
persistent subprocess using JSON lines on standard input/output. Use reference recordings for cloned voices;
keep them distinct from custom Kokoro voices.

The existing guide selects this engine for permissive licensing, CPU/Intel-macOS suitability and avoiding a
PyTorch dependency. Runtime isolation addresses the documented incompatibility. Persistence amortizes model
loading over multiple requests; the idle timeout releases the worker when unused.

## Consequences

- The main speech and cloning engines can use different ONNX Runtime versions and dependency locks.
- Cloning remains optional; its environment and roughly 3.3 GB of full-precision models must be installed separately.
- A warm worker avoids repeated startup loading, but cold starts and CPU rendering still take noticeable time.
- The parent must manage startup, idle shutdown, request IDs, timeouts and worker failures across a process boundary.
- The ONNX export does not apply the Perth watermark described for the upstream PyTorch package. Existing consent
  requirements and responsible-use guidance remain necessary; this is not a claim of misuse prevention.
- This record does not establish Windows/Linux support or certify the licenses of alternative engines.

## Evidence

- [Cloning engine, alternatives and isolation rationale](../cloning.md)
- [Main runtime pin](../../pyproject.toml)
- [Cloning runtime pin](../../engines/chatterbox/pyproject.toml)
- [Parent process and lifecycle](../../src/naturalvoice/clone.py)
- [Worker protocol and model loading](../../engines/chatterbox/worker.py)

## Record lifecycle

This accepted decision is immutable. If the architecture changes, add a new numbered ADR stating that it
supersedes 0001; only change this record's status to identify the superseding ADR. Preserve the original rationale.
