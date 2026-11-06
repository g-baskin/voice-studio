"""Who may reach the web app: loopback by default, token holders in network mode, never cross-site writers."""

import logging

import pytest
from fastapi.testclient import TestClient

from naturalvoice import access, cli, server, voices

TOKEN = "t" * 43
LAN = "http://192.168.1.5:8765"


def make(base="http://127.0.0.1", peer="127.0.0.1", **kw):
    return TestClient(server.app, base_url=base, client=(peer, 50000), follow_redirects=False, **kw)


@pytest.fixture
def network(monkeypatch):
    monkeypatch.setattr(server.app.state, "access", access.AccessPolicy(token=TOKEN), raising=False)


def test_local_browser_is_admitted():
    assert make().get("/api/presets").status_code == 200
    assert make(base="http://localhost:8765").get("/").status_code == 200


def test_other_hostnames_are_refused_even_from_this_computer():
    # A page whose DNS name was rebound to 127.0.0.1 still sends its own name as the Host.
    r = make(base="http://attacker.example:8765").get("/api/presets")
    assert r.status_code == 403 and "127.0.0.1" in r.json()["detail"]


def test_network_peers_are_refused_without_network_mode():
    assert make(peer="192.0.2.20").get("/api/presets").status_code == 403
    assert make(base=LAN, peer="192.168.1.20").get("/").status_code == 403


def test_cross_site_requests_are_refused():
    c = make()
    assert (
        c.post("/api/batch-download", json={"jobs": []}, headers={"origin": "http://evil.example"}).status_code == 403
    )
    assert c.get("/api/presets", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    # Same-origin writes reach validation, and cross-site page navigation still works.
    assert c.post("/api/batch-download", json={"jobs": []}, headers={"origin": "http://127.0.0.1"}).status_code == 422
    assert c.get("/", headers={"sec-fetch-site": "cross-site"}).status_code == 200


def test_network_mode_requires_the_token(network):
    c = make(base=LAN, peer="192.168.1.20")
    assert c.get("/api/presets").status_code == 401
    assert c.get("/").status_code == 401
    assert c.get("/?access=wrong").status_code == 401
    assert c.get("/?access=wr%C3%B6ng").status_code == 401  # non-ASCII is refused, not a server error
    assert make(base=LAN, peer="192.168.1.20", cookies={access.COOKIE: "wrong"}).get("/").status_code == 401
    # This computer keeps working without the link.
    assert make().get("/api/presets").status_code == 200


def test_access_link_sets_a_strict_cookie_and_drops_the_token(network):
    r = make(base=LAN, peer="192.168.1.20").get(f"/studio.html?access={TOKEN}&tab=2")
    assert r.status_code == 303 and r.headers["location"] == "/studio.html?tab=2"
    cookie = r.headers["set-cookie"].lower()
    assert f"{access.COOKIE}={TOKEN}".lower() in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert f"max-age={400 * 86400}" in cookie  # a home-screen app keeps working for the browser maximum
    phone = make(base=LAN, peer="192.168.1.20", cookies={access.COOKIE: TOKEN})
    assert phone.get("/api/presets").status_code == 200
    origin = {"origin": LAN}
    assert phone.post("/api/batch-download", json={"jobs": []}, headers=origin).status_code == 422
    assert phone.post("/api/batch-download", json={"jobs": []}, headers={"origin": "http://e.x"}).status_code == 403
    # Sample collections stay loopback-only, token or not.
    assert phone.get("/api/samples").status_code == 403


def test_redirect_target_stays_on_this_site():
    assert access.safe_location("//evil.example/x", [("access", TOKEN)]) == "/"
    assert access.safe_location("/voicelab.html", [("access", TOKEN), ("a", "1 2")]) == "/voicelab.html?a=1+2"


@pytest.mark.parametrize(
    ("host", "network_mode"),
    [("127.0.0.1", False), ("localhost", False), ("::1", False), ("0.0.0.0", True), ("192.168.1.5", True)],
)
def test_bind_address_decides_the_mode(host, network_mode, tmp_path):
    path = tmp_path / access.TOKEN_FILE
    assert (access.policy_for_bind(host, path).token is not None) is network_mode
    assert path.exists() is network_mode  # loopback serving never writes a token


def test_token_is_saved_owner_only_and_reused(tmp_path):
    path = tmp_path / "data" / access.TOKEN_FILE
    first = access.stored_token(path)
    assert path.read_text() == first and (path.stat().st_mode & 0o777) == 0o600
    assert access.stored_token(path) == first
    renewed = access.stored_token(path, renew=True)
    assert renewed != first and access.stored_token(path) == renewed
    assert (path.stat().st_mode & 0o777) == 0o600


def test_damaged_token_file_and_loose_leftovers_are_replaced(tmp_path):
    path = tmp_path / access.TOKEN_FILE
    leftover = tmp_path / f".{access.TOKEN_FILE}.tmp"
    leftover.write_text("old")
    leftover.chmod(0o644)
    for bad in [b"short", b"\xff" * 43, b"a b" * 15]:
        path.write_bytes(bad)
        token = access.stored_token(path)
        assert len(token) == 43 and path.read_text() == token
        assert (path.stat().st_mode & 0o777) == 0o600 and not leftover.exists()


def test_token_is_redacted_from_request_logs():
    record = logging.LogRecord("uvicorn.access", 20, "", 0, "%s %s", ("GET", f"/?a=1&access={TOKEN}&b=2"), None)
    assert access.RedactAccessToken().filter(record)
    assert TOKEN not in record.getMessage() and "access=REDACTED&b=2" in record.getMessage()


def test_serve_in_network_mode_prints_a_link_and_protects_the_app(monkeypatch, capsys, tmp_path):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    monkeypatch.setattr(server.app.state, "access", None, raising=False)
    monkeypatch.setattr(logging.getLogger("uvicorn.access"), "filters", [])
    monkeypatch.setattr(access, "lan_address", lambda host: "192.168.1.5")
    monkeypatch.setattr(voices, "DATA_DIR", tmp_path)

    assert cli.main(["serve"]) == 0
    assert server.app.state.access.token is None and not (tmp_path / access.TOKEN_FILE).exists()

    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "8765"]) == 0
    token = server.app.state.access.token
    assert token and f"http://192.168.1.5:8765/?access={token}" in capsys.readouterr().err
    assert calls[-1] == (server.app, {"host": "0.0.0.0", "port": 8765})
    assert any(isinstance(f, access.RedactAccessToken) for f in logging.getLogger("uvicorn.access").filters)

    # A restart keeps the link, so phones that opened it once stay signed in.
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "8765"]) == 0
    assert server.app.state.access.token == token and f"access={token}" in capsys.readouterr().err

    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "8765", "--new-token"]) == 0
    renewed = server.app.state.access.token
    err = capsys.readouterr().err
    assert renewed != token and "signed out" in err and f"access={renewed}" in err and token not in err
