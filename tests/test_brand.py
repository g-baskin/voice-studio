"""The logo files the pages, the PWA manifest and the README point to must exist and be the right size."""

import re
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from naturalvoice import server

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src/naturalvoice/web"


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", data[16:24])


@pytest.mark.parametrize(
    "name,size",
    [
        ("icon-192.png", 192),
        ("icon-512.png", 512),
        ("icon-maskable-512.png", 512),
        ("apple-touch-icon.png", 180),
        ("favicon-32.png", 32),
    ],
)
def test_icon_pngs_have_the_declared_size(name, size):
    assert png_size(WEB / name) == (size, size)


def test_banner_is_social_preview_size_and_linked_from_readme():
    assert png_size(ROOT / "docs/assets/banner.png") == (1280, 640)
    assert png_size(ROOT / "docs/assets/icon-1024.png") == (1024, 1024)
    assert "docs/assets/banner.png" in (ROOT / "README.md").read_text()


def test_manifest_icons_and_page_links_resolve_over_http():
    c = TestClient(server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    manifest = c.get("/manifest.webmanifest").json()
    assert manifest["name"] == "Voice Studio" and {i["purpose"] for i in manifest["icons"]} >= {"any", "maskable"}
    for icon in manifest["icons"]:
        assert c.get("/" + icon["src"]).status_code == 200, icon["src"]
    for page in ("index.html", "studio.html", "voicelab.html"):
        html = c.get("/" + page).text
        for href in re.findall(r'<link rel="(?:icon|apple-touch-icon|manifest)"[^>]*href="([^"]+)"', html):
            assert c.get("/" + href).status_code == 200, (page, href)
    shell = re.findall(r'"([\w.-]+\.(?:png|svg|js|css|webmanifest))"', (WEB / "sw.js").read_text())
    for f in shell:
        assert (WEB / f).exists(), f"service worker caches a missing file: {f}"
