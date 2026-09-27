"""Capture the real application for the tour: every screen the film shows, as the app draws it.

A store of its own is seeded with the sample model of a fictional university, a reviewer is
assigned and a branch is put in review, and the application is started on it with the offline
reader and the debug persona, exactly as the browser round runs it. Each shot is a screenshot
at twice the size of the window, so the film can move in on a control and stay sharp, with the
position of every control the narration names. They land in `build/shots/`, with
`shots.json` saying where each named control is.

    uv run --group gui python docs/tutorial/tools/capture.py
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from common import BUILD, MANIFEST, REPO, SHOTS
from playwright.sync_api import Page, sync_playwright

VIEW = {"width": 1600, "height": 900}
SCALE = 2
FOCUS = "DE-SRS-COURSE-OFFERING"
QUESTION = "What is the impact of changing SRS_Course_Offering?"
BRANCH = "Curriculum review portal"
RETURNING = "{v:1,welcome:true,tips:false,screens:[]}"  # a reader who has closed the welcome and the tips


def _ea(env: dict, *args: str) -> None:
    ea = Path(sys.executable).parent / "ea"
    subprocess.run([str(ea), *args], cwd=REPO, env=env, check=True, capture_output=True, text=True)


def seed(db: Path) -> dict:
    """A store of its own: the pack, the sample model, a reviewer, and a branch in review."""
    for old in db.parent.glob(db.name + "*"):
        old.unlink()
    env = dict(os.environ, EA_DB_PATH=str(db), EA_BACKEND="duckdb")
    _ea(env, "init", "--pack", "packs/higher_education/metamodel.yaml")
    _ea(env, "import", "data/sample", "--source", "sample")
    _ea(env, "reviewers", "set", "Data Entity", "data-stewards")
    _ea(
        env,
        "branch",
        "create",
        BRANCH,
        "--description",
        "Unit proposals reviewed online",
        "-w",
        "WP-CMS-UPGRADE",
    )
    branch = "curriculum-review-portal"
    _ea(
        env,
        "--branch",
        branch,
        "set",
        FOCUS,
        "DE-SRS-COURSE",
        "--target-state",
        "change",
        "-w",
        "WP-CMS-UPGRADE",
    )
    _ea(env, "branch", "review", branch)
    return env


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(env: dict) -> tuple[subprocess.Popen, str]:
    port = _free_port()
    env = dict(
        env,
        PORT=str(port),
        EA_PACK="packs/higher_education/metamodel.yaml",
        EA_AUTH="mock",
        EA_AGENT_PROVIDER="stub",
        EA_SECRET_KEY="tutorial-capture",
        EA_TIMEZONE="Australia/Brisbane",
    )
    log = (BUILD / "server.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=REPO,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            with urllib.request.urlopen(base + "/", timeout=2) as r:  # noqa: S310 — localhost
                if r.status == 200:
                    return proc, base
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit("the application did not start: see build/server.log")


class Camera:
    """A browser on the application, and the shots taken of it."""

    def __init__(self, page: Page, base: str):
        self.page, self.base, self.shots = page, base, {}
        self._inflight = 0
        page.on("request", lambda r: self._count(r, 1))
        page.on("requestfinished", lambda r: self._count(r, -1))
        page.on("requestfailed", lambda r: self._count(r, -1))

    def _count(self, request, step: int) -> None:
        if "_dash-update-component" in request.url:
            self._inflight = max(0, self._inflight + step)

    def settle(self, quiet_ms: int = 700, timeout: float = 40) -> None:
        """Wait until no callback is in flight and nothing on the page says it is loading."""
        deadline, quiet = time.time() + timeout, None
        self.page.wait_for_timeout(80)
        while time.time() < deadline:
            busy = self._inflight or self.page.evaluate(
                "() => document.querySelectorAll('[data-dash-is-loading=\"true\"], .mantine-Button-loader').length"
            )
            if busy:
                quiet = None
            elif quiet is None:
                quiet = time.time()
            elif (time.time() - quiet) * 1000 >= quiet_ms:
                return
            self.page.wait_for_timeout(60)

    def goto(self, path: str) -> None:
        self.page.goto(self.base + path)
        self.page.wait_for_selector("#page h1", timeout=40_000)
        self.settle()

    def diagrams(self, count: int = 1) -> None:
        self.page.wait_for_function(
            "n => document.querySelectorAll('.ea-mermaid svg').length >= n", arg=count, timeout=40_000
        )
        self.page.wait_for_timeout(600)

    def shot(self, sid: str, regions: dict[str, str], full: bool = False) -> None:
        """The window, or the whole page, and where each named control stands on it."""
        self.settle()
        if full:
            self.page.evaluate("() => window.scrollTo(0, 0)")
            self.page.wait_for_timeout(200)
        self.page.mouse.move(VIEW["width"] - 2, 60)  # no hover state on the picture
        self.page.wait_for_timeout(150)
        # A whole page is stitched at the window's size, so nothing sized to the window grows;
        # the navigation, fixed to the window, stops at its foot and the film draws it on down.
        self.page.screenshot(path=str(SHOTS / f"{sid}.png"), full_page=full, animations="disabled")
        height = self.page.evaluate("() => document.documentElement.scrollHeight") if full else VIEW["height"]
        nav = self.page.evaluate(
            """() => { const n = document.querySelector('.mantine-AppShell-navbar');
                const r = n.getBoundingClientRect(), s = getComputedStyle(n);
                return {box: [r.x, r.y, r.width, r.height], fill: s.backgroundColor, edge: s.borderRightColor}; }"""
        )
        found = {}
        for name, selector in regions.items():
            box = self.page.locator(selector).first.bounding_box()
            if not box:
                raise SystemExit(f"{sid}: {name} ({selector}) is not on the screen")
            found[name] = [round(box["x"]), round(box["y"]), round(box["width"]), round(box["height"])]
        path = self.page.url.replace(self.base, "") or "/"
        self.shots[sid] = {
            "file": f"{sid}.png",
            "w": VIEW["width"],
            "h": height,
            "path": path,
            "title": self.page.locator("#page h1").first.inner_text().strip(),
            "nav": {"box": [round(v) for v in nav["box"]], "fill": nav["fill"], "edge": nav["edge"]},
            "regions": found,
        }
        print("shot", sid, path, list(found), flush=True)


def tour(cam: Camera, newcomer: Camera) -> None:
    page = cam.page
    # A newcomer's first screen, with its welcome.
    newcomer.goto("/")
    newcomer.page.wait_for_selector("#help-hint .ea-welcome", timeout=20_000)
    newcomer.shot("home-welcome", {"welcome": "#help-hint", "nav": ".mantine-AppShell-navbar"})

    cam.goto("/")
    cam.shot("home", {"nav": ".mantine-AppShell-navbar", "page": "#page"})

    cam.goto("/browse")
    cam.shot("browse-help", {"help": "#page .ea-help-button", "title": "#page .ea-page-title"})
    page.click("#page .ea-help-button")
    page.wait_for_selector(".mantine-Drawer-content:has(#help-title)", state="visible")
    cam.diagrams()
    cam.shot("browse-help-open", {"panel": ".mantine-Drawer-content:has(#help-title)"})
    page.keyboard.press("Escape")
    page.wait_for_selector(".mantine-Drawer-content:has(#help-title)", state="hidden")

    page.fill("#browse-text", "course")
    cam.settle()
    page.wait_for_timeout(800)
    cam.shot(
        "browse",
        {
            "search": "#browse-text",
            "grid": "#browse-grid",
            "row": "#browse-grid .ag-row:has-text('SRS_Course_Offering')",
        },
    )

    cam.goto(f"/element/{FOCUS}")
    cam.shot(
        "element",
        {
            "title": "#page .ea-page-title",
            "attributes": "#el-attr-values",
            "tabs": "#page [role=tablist]",
            "graphtab": "#page [role=tab]:has-text('Graph')",
            "impact": "#page .ea-page-title a[href^='/impact']",
        },
    )
    page.get_by_role("tab", name=re.compile("^Graph")).click()
    cam.settle()
    cam.diagrams()
    cam.shot(
        "element-graph",
        {
            "tabs": "#page [role=tablist]",
            "graph": "#page canvas >> visible=true",
            "view": "#page .ea-mermaid >> visible=true",
        },
        full=True,
    )

    cam.goto("/ask")
    page.fill("#ask-input", QUESTION)
    cam.settle()
    cam.shot("ask", {"input": "#ask-input", "button": "#ask-button"})
    page.click("#ask-button")
    page.wait_for_selector("#ask-answer .ea-mermaid svg", timeout=60_000)
    cam.settle()
    cam.diagrams()
    cam.shot(
        "ask-answer",
        {"answer": "#ask-answer", "view": "#ask-answer .ea-mermaid", "table": "#ask-answer table"},
        full=True,
    )

    cam.goto(f"/impact?element={FOCUS}")
    if page.locator("#imp-result .ea-mermaid, #imp-result table").count() == 0:
        page.click("#imp-run")
        cam.settle()
    cam.shot(
        "impact",
        {
            "result": "#imp-result",
            "element": "#imp-element",
            "upstream": "#imp-result table >> nth=0",
            "graph": "#page canvas >> visible=true",
            "view": "#page .ea-mermaid >> visible=true",
        },
        full=True,
    )

    cam.goto("/propose")
    page.click("#pr-example")
    cam.settle()
    mode = page.locator('[id=\'{"id":"pr-text","type":"md-mode"}\']').first
    mode.locator("label", has_text="Split").first.click()
    cam.settle()
    page.wait_for_timeout(600)
    cam.shot(
        "propose",
        {
            "where": ".ea-propose-where",
            "editor": ".ea-markdown-editor",
            "divider": ".ea-md-splitter",
            "example": "#pr-example",
            "analyse": "#pr-analyse",
        },
        full=True,
    )
    page.click("#pr-analyse")
    page.wait_for_selector("#pr-result .ag-root", timeout=60_000)
    cam.settle()
    page.wait_for_timeout(800)
    cam.shot(
        "propose-analysed",
        {"result": "#pr-result", "conv": "#pr-conv", "rows": "#pr-el-grid", "apply": "#pr-apply"},
        full=True,
    )

    cam.goto("/branches")
    page.locator("#br-status label", has_text="In review").first.click()
    cam.settle()
    opener = page.locator("[id*='br-open']").first
    if opener.count():
        opener.click()
        cam.settle()
        page.wait_for_timeout(600)
    cam.shot(
        "branches",
        {
            "list": "#br-list",
            "detail": "#br-detail",
            "approve": "#br-detail button:has-text('Approve')",
            "merge": "#br-detail button:has-text('Merge ticked rows')",
            "log": "#br-grid",
        },
        full=True,
    )

    cam.goto("/target")
    page.wait_for_timeout(800)
    cam.shot(
        "target",
        {"page": "#page", "matrix": "#page table >> nth=0", "elements": "#page table >> nth=1"},
        full=True,
    )

    cam.goto("/feeds")
    cam.shot("feeds", {"page": "#page", "runs": "#runs-list"}, full=True)

    cam.goto("/metamodel")
    page.wait_for_timeout(1000)
    cam.shot("metamodel", {"page": "#page", "tabs": "#mm-tabs"})
    page.get_by_role("tab", name="Notation").click()
    cam.settle()
    cam.diagrams()
    cam.shot("metamodel-notation", {"preview": "#page .ea-mermaid >> visible=true"}, full=True)

    cam.goto("/organisations")
    cam.shot("organisations", {"page": "#page", "table": "#page table"})

    cam.goto("/users")
    cam.shot(
        "users", {"page": "#page", "grant": "#page .mantine-Paper-root:has-text('Grant a role')"}, full=True
    )

    cam.goto("/health")
    page.wait_for_timeout(800)
    cam.shot(
        "health",
        {
            "page": "#page",
            "fresh": "#page .mantine-Paper-root:has-text('Freshness')",
            "complete": "#page .mantine-Paper-root:has-text('Completeness')",
        },
        full=True,
    )

    cam.goto("/guide")
    cam.shot(
        "guide",
        {
            "contents": "#page .ea-guide-contents",
            "help": "#page .ea-help-button",
            "title": "#page .ea-page-title",
        },
    )


def main() -> None:
    env = seed(BUILD / "tour.duckdb")
    proc, base = serve(env)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()

            def context(returning: bool):
                ctx = browser.new_context(
                    viewport=VIEW,
                    device_scale_factor=SCALE,
                    locale="en-AU",
                    timezone_id="Australia/Brisbane",
                    reduced_motion="reduce",
                )
                if returning:
                    ctx.add_init_script(
                        f"window.localStorage.setItem('help-seen', JSON.stringify({RETURNING}))"
                    )
                ctx.add_init_script("try { localStorage.removeItem('ea-split'); } catch (e) {}")
                page = ctx.new_page()
                page.set_default_timeout(40_000)
                return Camera(page, base)

            cam, newcomer = context(True), context(False)
            tour(cam, newcomer)
            shots = {**newcomer.shots, **cam.shots}
            MANIFEST.write_text(json.dumps(shots, indent=1) + "\n", encoding="utf-8")
            browser.close()
        print(f"captured {len(shots)} shots into {SHOTS.relative_to(REPO)}")
    finally:
        os.killpg(proc.pid, 15)


if __name__ == "__main__":
    main()
