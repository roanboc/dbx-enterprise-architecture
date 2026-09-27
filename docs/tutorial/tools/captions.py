"""Write the captions, one per line of narration, from the film's own timeline:
`captions/en.srt` and `captions/en.vtt`, for a player or a video platform.

    python docs/tutorial/tools/captions.py
"""

from __future__ import annotations

from common import CAPTIONS
from page import info, served
from playwright.sync_api import sync_playwright


def stamp(seconds: float, sep: str) -> str:
    ms = int(round(seconds * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def main() -> None:
    with served() as url, sync_playwright() as p:
        browser = p.chromium.launch()
        caps = info(browser, url)["caps"]
        browser.close()
    CAPTIONS.mkdir(exist_ok=True)
    srt = "\n".join(
        f"{i + 1}\n{stamp(c['s'], ',')} --> {stamp(c['e'] + 0.1, ',')}\n{c['text']}\n"
        for i, c in enumerate(caps)
    )
    vtt = "WEBVTT\n\n" + "\n".join(
        f"{stamp(c['s'], '.')} --> {stamp(c['e'] + 0.1, '.')}\n{c['text']}\n" for c in caps
    )
    (CAPTIONS / "en.srt").write_text(srt, encoding="utf-8")
    (CAPTIONS / "en.vtt").write_text(vtt, encoding="utf-8")
    print(f"wrote captions/en.srt and en.vtt, {len(caps)} captions")


if __name__ == "__main__":
    main()
