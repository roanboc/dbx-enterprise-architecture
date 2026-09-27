"""Where the tutorial's tools read and write, shared by every step."""

from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]  # docs/tutorial
REPO = HERE.parents[1]
SRC = HERE / "src"
FONTS = HERE / "fonts"
CAPTIONS = HERE / "captions"
BUILD = HERE / "build"  # not committed: shots, voice, frames, the mix
DIST = HERE / "dist"  # not committed: the video
SHOTS = BUILD / "shots"
MODELS = Path(os.environ.get("EA_TUTORIAL_MODELS", HERE / "models"))
NARRATION = SRC / "narration.json"
VODUR = SRC / "vodur.json"
MANIFEST = SHOTS / "shots.json"
FILM = "ea-repository-tour"

for folder in (BUILD, DIST, SHOTS, BUILD / "vo"):
    folder.mkdir(parents=True, exist_ok=True)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def narration() -> dict:
    return load(NARRATION)
