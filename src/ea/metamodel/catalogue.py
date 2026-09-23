"""The metamodels the repository ships, read off the disk rather than listed in code.

A starter is a pack committed under `packs/`, one directory each. Nothing here names a
framework: principle `P5` says a framework's name belongs in a pack, so the catalogue is
whatever the directory holds, read from each file's own header. Adding a pack is adding a
directory.

The directory is not part of the installed wheel, so a wheel install finds nothing. That is
a catalogue with no entries, never an error: the page that offers starters says it has none.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ea.models import is_pack_id, pack_id_from_legacy, slugify

log = logging.getLogger(__name__)

#: The file a pack directory is recognised by.
PACK_FILE = "metamodel.yaml"


@dataclass(frozen=True)
class Starter:
    """One shipped metamodel, as much of it as its header says. The file is not parsed in full
    here: a catalogue is a list to choose from, and reading fifty element types to draw a row
    is work nobody asked for."""

    pack_id: str
    name: str
    version: str
    status: str
    description: str
    path: Path
    element_types: int = 0
    relationship_types: int = 0

    @property
    def ref(self) -> str:
        return f"{self.pack_id}@{self.version}"

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}"


def _header(data: dict[str, Any], path: Path) -> Starter | None:
    meta = data.get("pack") or {}
    name = str(meta.get("name") or "").strip()
    given = str(meta.get("id") or "").strip()
    if not (name or given):
        log.warning("%s has no pack name or identifier; not offered as a starter", path)
        return None
    # The same folding the loader does, so a starter's identifier here is the one it will be
    # stored under — which is what lets the page say whether the store already holds it.
    pack_id = given if is_pack_id(given) else pack_id_from_legacy(given or slugify(name))
    return Starter(
        pack_id=pack_id,
        name=name or given,
        version=str(meta.get("version") or "1"),
        status=str(meta.get("status") or "draft"),
        description=str(meta.get("description") or "").strip(),
        path=path,
        element_types=len(data.get("element_types") or []),
        relationship_types=len(data.get("relationship_types") or []),
    )


def starters(directory: Path | str) -> list[Starter]:
    """Every shipped metamodel under `directory`, by name.

    Never raises. A directory that is absent, unreadable, or holds a file that is not a pack
    gives a shorter list and a line in the log — the catalogue is a convenience, and an
    adopter who cannot reach it still has `ea load-pack` and the file upload.
    """
    root = Path(directory)
    out: list[Starter] = []
    try:
        candidates = sorted(root.glob(f"*/{PACK_FILE}"))
    except OSError as exc:  # an unreadable or missing directory is an empty catalogue
        log.info("no starter metamodels under %s: %s", root, exc)
        return out
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            found = _header(data, path)
        except (OSError, yaml.YAMLError) as exc:
            log.warning("%s could not be read as a starter metamodel: %s", path, exc)
            continue
        if found is not None:
            out.append(found)
    return sorted(out, key=lambda s: s.name.lower())
