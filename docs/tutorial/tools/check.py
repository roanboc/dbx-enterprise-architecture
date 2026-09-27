"""Draw every tenth of a second of the film on a small canvas and list any moment that fails;
then write a still a moment after every line starts, into `build/stills/`, to look at.

    python docs/tutorial/tools/check.py [--stills]
"""

from __future__ import annotations

import argparse
import base64

from common import BUILD
from page import open_film, served
from playwright.sync_api import sync_playwright


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", action="store_true", help="also write a still a moment into every line")
    args = ap.parse_args()
    with served() as url, sync_playwright() as p:
        browser = p.chromium.launch()
        page = open_film(browser, url, 0.25)
        film = page.evaluate("filmInfo()")
        failed = page.evaluate(
            """total => { const out = [];
                for (let t = 0; t < total; t += 0.1) { try { drawAt(t); } catch (e) { out.push([t, String(e)]); } }
                return out; }""",
            film["total"],
        )
        for t, error in failed[:20]:
            print(f"  {t:7.1f}s  {error}")
        m, s = divmod(film["total"], 60)
        print(
            f"{int(m)}:{s:04.1f} long, {len(film['caps'])} lines, {len(film['clicks'])} presses; {len(failed)} moments failed"
        )
        if args.stills:
            still = open_film(browser, url, 0.5)
            folder = BUILD / "stills"
            folder.mkdir(exist_ok=True)
            for old in folder.glob("*.jpg"):
                old.unlink()
            for c in film["caps"]:
                for off in (1.2, 0.0):
                    t = min(c["e"], c["s"] + off) if off else c["e"] - 0.1
                    data = still.evaluate(f"renderAt({t}, 0.85)")
                    name = f"{t:06.1f}-{c['sid']}-{c['id']}{'-end' if not off else ''}.jpg"
                    (folder / name).write_bytes(base64.b64decode(data.split(",", 1)[1]))
            print("stills in", folder.relative_to(BUILD.parent))
        browser.close()
        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
