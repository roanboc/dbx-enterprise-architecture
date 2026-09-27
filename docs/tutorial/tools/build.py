"""Build the page the film is drawn on: `build/render.html`, with its fonts, its narration, the
voiced timings, the shots' regions, the engine and the scenes in one file beside the shots.

    python docs/tutorial/tools/build.py
"""

from __future__ import annotations

import base64
import json
import re

from common import BUILD, FONTS, MANIFEST, NARRATION, SRC, VODUR, load


def fonts() -> str:
    css = (FONTS / "fonts.css").read_text(encoding="utf-8")

    def inline(m: re.Match) -> str:
        return f"url(data:font/woff2;base64,{base64.b64encode((FONTS / m.group(1)).read_bytes()).decode()})"

    return "<style>" + re.sub(r"url\(([\w.-]+\.woff2)\)", inline, css) + "</style>"


def main() -> None:
    if not MANIFEST.exists():
        raise SystemExit("no shots yet: run tools/capture.py first")
    data = "\n".join(
        [
            f"const NARRATION = {json.dumps(load(NARRATION))};",
            f"const VODUR = {json.dumps(load(VODUR))};",
            f"const SHOTS = {json.dumps(load(MANIFEST))};",
        ]
    )
    code = "\n".join((SRC / name).read_text(encoding="utf-8") for name in ("engine.js", "scenes.js"))
    page = (
        '<!doctype html><html><head><meta charset="utf-8">'
        + fonts()
        + "<style>html,body{margin:0;background:#000}canvas{display:block;width:100vw}</style>"
        + "</head><body><script>\n"
        + data
        + "\n"
        + code
        + "\n</script></body></html>"
    )
    (BUILD / "render.html").write_text(page, encoding="utf-8")
    print("built", (BUILD / "render.html").relative_to(BUILD.parent), "with", len(load(MANIFEST)), "shots")


if __name__ == "__main__":
    main()
