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
