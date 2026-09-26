"""Every icon a page names is one the application ships.

An icon is drawn from an SVG in `assets/icons/`, so that no request leaves the browser for
one; a name with no file behind it draws an empty box and says nothing, and only a reader
looking at the screen would notice. This reads the names out of the code instead.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_icon_the_pages_name_is_bundled():
    named: dict[str, set[str]] = {}
    for path in (ROOT / "src" / "ea" / "ui").rglob("*.py"):
        for name in re.findall(r"[\"']tabler:([a-z0-9-]+)[\"']", path.read_text(encoding="utf-8")):
            named.setdefault(name, set()).add(path.name)
    missing = {
        n: sorted(files)
        for n, files in named.items()
        if not (ROOT / "assets" / "icons" / f"{n}.svg").is_file()
    }
    assert named and not missing, f"icons named but not bundled in assets/icons/: {missing}"
