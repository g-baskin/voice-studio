import importlib.util
from pathlib import Path


def test_runner_isolates_data_and_credentials(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "browser_tests", Path(__file__).parents[1] / "scripts/browser_tests.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("NATURALVOICE_DATA", "/do-not-touch")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    env = module.environment(tmp_path)
    assert env["NATURALVOICE_DATA"] == str(tmp_path / "data")
    assert env["TMPDIR"] == str(tmp_path / "tmp")
    assert env["NV_SCREENSHOTS"] == str(tmp_path / "screenshots")
    assert "OPENROUTER_API_KEY" not in env and "OPENAI_API_KEY" not in env


def test_runner_disables_ollama_discovery(tmp_path, monkeypatch):
    import uvicorn
    from naturalvoice import llm, voices

    spec = importlib.util.spec_from_file_location(
        "browser_tests", Path(__file__).parents[1] / "scripts/browser_tests.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(voices, "DATA_DIR", tmp_path)
    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "NATURALVOICE_LLM_URL"):
        monkeypatch.delenv(key, raising=False)

    def forbidden():
        raise AssertionError("Existing Ollama must not be contacted")

    def run(*args, **kwargs):
        assert llm.config() is None
        assert llm.status()["available"] is False

    monkeypatch.setattr(llm, "ollama_chat_models", forbidden)
    monkeypatch.setattr(uvicorn, "run", run)
    module.serve(1)
    assert llm.ollama_chat_models is forbidden


def test_stopping_a_stuck_server_also_stops_what_it_started(tmp_path):
    import os
    import subprocess
    import sys
    import time

    spec = importlib.util.spec_from_file_location(
        "browser_tests", Path(__file__).parents[1] / "scripts/browser_tests.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pid_file = tmp_path / "worker.pid"
    # A "server" that ignores SIGTERM and starts a long-running "worker", like a server stuck mid-render.
    server = (
        "import signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "w = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(w.pid))\n"
        "time.sleep(120)\n"
    )
    process = subprocess.Popen([sys.executable, "-c", server], start_new_session=True)
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text():
            break
        time.sleep(0.05)
    worker = int(pid_file.read_text())

    module.stop_server(process, grace=0.5)

    for _ in range(100):
        try:
            os.kill(worker, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(worker, 9)
        raise AssertionError("the server's worker survived stop_server")
