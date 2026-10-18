"""Product versions must agree before a build can be released."""

from pathlib import Path
import plistlib
import tomllib

import pytest

from naturalvoice import __version__


@pytest.mark.parametrize("surface", ["runtime", "lock", "desktop-build", "desktop-display"])
def test_product_versions_match_package_metadata(surface: str) -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    expected = project["project"]["version"]
    lock = tomllib.loads((root / "uv.lock").read_text())
    locked_version = next(
        package["version"] for package in lock["package"] if package["name"] == project["project"]["name"]
    )
    with (root / "desktop/Voice Studio.app/Contents/Info.plist").open("rb") as file:
        desktop = plistlib.load(file)
    versions = {
        "runtime": __version__,
        "lock": locked_version,
        "desktop-build": desktop["CFBundleVersion"],
        "desktop-display": desktop["CFBundleShortVersionString"],
    }
    assert versions[surface] == expected, f"{surface} version differs from pyproject.toml"
