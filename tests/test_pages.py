"""Pages answer at clean addresses; old .html addresses redirect; the SvelteKit build is served."""

import re

import pytest
from fastapi.testclient import TestClient

from naturalvoice import server


def client(peer: str = "127.0.0.1") -> TestClient:
    return TestClient(server.app, base_url="http://127.0.0.1", client=(peer, 50000), follow_redirects=False)


@pytest.mark.parametrize("path", ["/", "/studio", "/voice-lab", "/samples", "/backup"])
def test_clean_addresses_serve_pages(path):
    r = client().get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "Shark Audio" in r.text


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("/index.html", "/"),
        ("/studio.html?voice=af_heart", "/studio?voice=af_heart"),
        ("/voicelab.html", "/voice-lab"),
        ("/samples.html", "/samples"),
        ("/backup.html", "/backup"),
    ],
)
def test_old_addresses_redirect_and_keep_the_query(old, new):
    r = client().get(old)
    assert r.status_code == 302 and r.headers["location"] == new


def test_svelte_page_assets_resolve():
    html = client().get("/backup").text
    assets = re.findall(r'(?:href|src)="\./(_app/[^"]+)"', html)
    assert assets, "backup page references no build assets"
    for asset in assets:
        assert client().get("/" + asset).status_code == 200, asset


def test_pages_keep_the_local_access_guard():
    assert client("192.0.2.9").get("/backup").status_code == 403
    assert client("192.0.2.9").get("/_app/version.json").status_code == 403
