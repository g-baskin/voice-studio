from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from contextlib import contextmanager
from collections.abc import Iterator
from unittest.mock import patch


def environment(folder: Path) -> dict[str, str]:
    env = dict(os.environ)
    # Browser tests must never inherit paid-provider credentials or a real data directory.
    for key in list(env):
        if key.startswith(("OPENAI_", "OPENROUTER_", "ELEVENLABS_", "NATURALVOICE_LLM_")):
            del env[key]
    env.update(
        NATURALVOICE_DATA=str(folder / "data"), TMPDIR=str(folder / "tmp"), NV_SCREENSHOTS=str(folder / "screenshots")
    )
    for name in ("data", "tmp", "screenshots"):
        (folder / name).mkdir()
    return env


def serve(fd: int) -> None:
    import uvicorn
    from naturalvoice import clone, llm, sample_library, server

    if engine := os.environ.get("NV_TEST_MEDIA_ENGINE"):
        sample_library.ENGINE = Path(engine)
    try:
        with patch.object(llm, "ollama_chat_models", return_value=[]):
            uvicorn.run(server.app, fd=fd, log_level="warning")
    finally:
        clone.stop()


@contextmanager
def test_server(root: Path, env: dict[str, str], log_path: Path) -> Iterator[str]:
    with socket.socket() as listener, log_path.open("w") as log:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve", str(listener.fileno())],
            env=env,
            cwd=root,
            pass_fds=(listener.fileno(),),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 60
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"Test server exited. See {log_path}")
                try:
                    with urllib.request.urlopen(url + "/api/presets", timeout=1) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"Server startup timed out. See {log_path}") from None
                    time.sleep(0.1)
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def verify_restored(root: Path, folder: Path, env: dict[str, str]) -> None:
    receipt = json.loads((folder / "restore-check.json").read_text())
    restored = Path(receipt["folder"]).resolve()
    if restored.parent != folder.resolve() or not restored.name.startswith("voice-studio-restored-"):
        raise RuntimeError("Restore receipt is outside this suite's disposable data.")
    restored_env = {**env, "NATURALVOICE_DATA": str(restored)}
    with test_server(root, restored_env, folder / "restored-server.log") as url:
        with urllib.request.urlopen(url + "/api/studio/projects", timeout=10) as response:
            projects = json.load(response)["projects"]
        assert len(projects) == 1 and projects[0]["title"] == "Backup fixture"
        with urllib.request.urlopen(url + "/api/studio/projects/" + projects[0]["id"], timeout=10) as response:
            assert json.load(response)["project"]["title"] == "Backup fixture"
        with urllib.request.urlopen(url + "/api/backups/browser", timeout=10) as response:
            assert json.load(response) == receipt["browser"]
    print("Restore restart passed: saved project loads and both browser settings survive.", flush=True)


def run_suite(root: Path, name: str, output: Path) -> None:
    folder = output / name
    folder.mkdir()
    env = environment(folder)
    env["PYTHONPATH"] = str(root / "src")
    env["NV_REF"] = str(folder / "reference.wav")
    env["NV_PERF"] = str(folder / "performance.wav")
    env["NV_RESTORE_RECEIPT"] = str(folder / "restore-check.json")
    if name == "clone":
        from naturalvoice import audio, tts

        reference, sr = tts.speak(
            "This is a synthetic reference recording for an automated test. Welcome to Voice Studio. We are testing a local voice workflow.",
            humanize=False,
        )
        audio.save(env["NV_REF"], reference, sr)
        performance, sr = tts.speak("Welcome to the local voice test.", humanize=False)
        audio.save(env["NV_PERF"], performance, sr)
    with test_server(root, env, folder / "server.log") as url:
        env["NV_URL"] = url
        with (folder / "browser.log").open("w") as browser_log:
            result = subprocess.run(
                ["node", str(root / "tests" / f"browser_{name}.cjs")],
                cwd=root,
                env=env,
                stdout=browser_log,
                stderr=subprocess.STDOUT,
                timeout=900,
            )
        print((folder / "browser.log").read_text(), end="", flush=True)
        if result.returncode:
            raise RuntimeError(f"{name}: browser check failed; artifacts in {folder}")
    if name == "backup":
        verify_restored(root, folder, env)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated local browser checks. No existing server is used.")
    parser.add_argument("--serve", type=int, help=argparse.SUPPRESS)
    parser.add_argument("suites", nargs="*", help="Optional suite names; default: all browser_*.cjs checks")
    args = parser.parse_args()
    if args.serve is not None:
        serve(args.serve)
        return 0
    root = Path(__file__).resolve().parents[1]
    available = sorted(
        p.stem.removeprefix("browser_") for p in (root / "tests").glob("browser_*.cjs") if p.stem != "browser_support"
    )
    names = args.suites or available
    if set(names) - set(available):
        parser.error("Unknown suite. Available: " + ", ".join(available))
    subprocess.run(
        [
            "node",
            "-e",
            "const p=require(process.env.PLAYWRIGHT_MODULE||'playwright'); (async()=>{const b=await p.chromium.launch();console.log('Chromium '+b.version());await b.close()})().catch(e=>{console.error(e.message);process.exitCode=1})",
        ],
        check=True,
    )
    output = Path(tempfile.mkdtemp(prefix="voice-studio-browser-"))
    print(f"Isolated data, screenshots and logs: {output}", flush=True)
    passed: list[str] = []
    try:
        for name in names:
            print(f"Running {name}", flush=True)
            run_suite(root, name, output)
            passed.append(name)
    finally:
        (output / "results.json").write_text(json.dumps({"passed": passed, "requested": names}, indent=2))
    print(f"Browser tests pass ({len(passed)}/{len(names)}). Artifacts: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
