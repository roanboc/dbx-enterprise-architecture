"""Driving the application the way a person does, and keeping the evidence.

Everything a scenario needs is a method here: go to a page, work a control, wait for
the callback behind it, and photograph the result. The waits are the delicate part —
a Dash callback is an XHR the page fires and then re-renders from, and a generated
view or a graph is drawn in the browser afterwards, so "the network went quiet" is
not the same as "the screen is finished".
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from tests.ui.evidence import Check, Scenario, Shot, slug

DASH_CALL = "/_dash-update-component"
QUIET_MS = 220  # a callback that triggers another one fires it well inside this window


@dataclass
class Ui:
    page: object  # playwright.sync_api.Page
    base_url: str
    run_dir: Path
    scenario: Scenario | None = None
    _inflight: int = 0
    _seen: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.page.on("request", self._started)
        self.page.on("requestfinished", self._ended)
        self.page.on("requestfailed", self._ended)

    # ---------------------------------------------------------------- recording
    def bind(self, scenario: Scenario) -> None:
        self.scenario = scenario

    def unbind(self) -> None:
        self.scenario = None

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        """Record an assertion without stopping the scenario, so one run sees everything."""
        assert self.scenario is not None, "check() outside a scenario"
        self.scenario.checks.append(Check(name=name, ok=bool(ok), detail=detail))
        return bool(ok)

    def must(self, name: str, ok: bool, detail: str = "") -> None:
        """An assertion the rest of the scenario depends on."""
        if not self.check(name, ok, detail):
            raise AssertionError(f"{name}: {detail}" if detail else name)

    def shot(self, caption: str, full_page: bool = True, selector: str | None = None) -> Path:
        assert self.scenario is not None, "shot() outside a scenario"
        self.settle()
        name = f"{self.scenario.scenario_id}-{slug(caption)}.png"
        path = self.run_dir / "screenshots" / name
        listbox = self.page.locator("[role='listbox']")
        if full_page and listbox.count() and listbox.first.is_visible():
            full_page = False  # a portalled dropdown lands in the wrong place when stitched
        if selector:
            self.page.locator(selector).first.screenshot(path=str(path))
        else:
            self.page.screenshot(path=str(path), full_page=full_page)
        self.scenario.shots.append(Shot(path=path, caption=caption))
        return path

    # ------------------------------------------------------------------- waiting
    def _started(self, request) -> None:  # noqa: ANN001 — playwright event payload
        if DASH_CALL in request.url:
            self._inflight += 1

    def _ended(self, request) -> None:  # noqa: ANN001
        if DASH_CALL in request.url:
            self._inflight = max(0, self._inflight - 1)

    def settle(self, timeout: float = 25.0) -> None:
        """Wait until no callback is in flight and the page has stopped re-rendering."""
        deadline = time.time() + timeout
        self.page.wait_for_timeout(60)  # give a click time to dispatch its callback
        quiet_since: float | None = None
        while time.time() < deadline:
            if self._inflight:
                quiet_since = None
                self.page.wait_for_timeout(50)
                continue
            now = time.time()
            if quiet_since is None:
                quiet_since = now
            elif (now - quiet_since) * 1000 >= QUIET_MS:
                if self._still_rendering():
                    quiet_since = None
                    continue
                self._wait_for_loaders()
                return
            self.page.wait_for_timeout(50)
        raise TimeoutError(f"the page was still working after {timeout} s")

    def _still_rendering(self) -> bool:
        """A component the renderer has marked as awaiting an output is not finished."""
        try:
            return bool(
                self.page.evaluate(
                    "() => document.querySelectorAll('[data-dash-is-loading=\"true\"]').length"
                )
            )
        except Exception:  # noqa: BLE001 — a navigating page has no document to ask
            return False

    def _wait_for_loaders(self) -> None:
        """A button that says it is working is a callback that has not finished."""
        try:
            self.page.wait_for_function(
                "() => document.querySelectorAll('.mantine-Button-loader,.mantine-LoadingOverlay-root').length === 0",
                timeout=15_000,
            )
        except Exception:  # noqa: BLE001 — a stuck loader is the scenario's finding, not a crash
            pass

    def goto(self, path: str) -> None:
        url = path if path.startswith("http") else self.base_url + path
        self.page.goto(url, wait_until="domcontentloaded")
        self.page.wait_for_selector("#page", state="attached")
        self.settle()

    def wait_mermaid(self, count: int = 1) -> None:
        """A generated view is drawn in the browser after its callback returns."""
        self.page.wait_for_function(
            "n => document.querySelectorAll('.ea-mermaid svg').length >= n",
            arg=count,
            timeout=25_000,
        )
        self.page.wait_for_timeout(250)

    def wait_graph(self) -> None:
        """Cytoscape paints onto a canvas; wait for one with something on it."""
        self.page.wait_for_function(
            "() => Array.from(document.querySelectorAll('canvas')).some(c => c.width > 0 && c.height > 0)",
            timeout=25_000,
        )
        self.page.wait_for_timeout(400)

    # ------------------------------------------------------------------ controls
    def click(self, selector: str) -> None:
        self.page.locator(self._sel(selector)).first.click()
        self.settle()

    def fill(self, selector: str, text: str) -> None:
        loc = self.page.locator(self._sel(selector)).first
        loc.click()
        loc.fill(text)
        self.settle()

    def select(self, selector: str, label: str, exact: bool = False) -> None:
        """A Mantine Select: click the input, then the option in its portal."""
        self.page.locator(self._sel(selector)).first.click()
        option = self.page.locator("[role='option']").filter(
            has_text=re.compile(f"^{re.escape(label)}$") if exact else re.compile(re.escape(label))
        )
        option.first.click()
        self.settle()

    def segmented(self, selector: str, label: str) -> None:
        root = self.page.locator(self._sel(selector)).first
        root.locator("label", has_text=re.compile(re.escape(label))).first.click()
        self.settle()

    def toggle(self, selector: str, on: bool) -> None:
        box = self.page.locator(self._sel(selector)).first
        if box.is_checked() != on:
            box.click(force=True)
        self.settle()

    def text(self, selector: str) -> str:
        loc = self.page.locator(self._sel(selector)).first
        return (loc.inner_text() if loc.count() else "").strip()

    def visible(self, selector: str) -> bool:
        loc = self.page.locator(self._sel(selector))
        return bool(loc.count()) and loc.first.is_visible()

    def disabled(self, selector: str) -> bool:
        loc = self.page.locator(self._sel(selector))
        return bool(loc.count()) and not loc.first.is_enabled()

    def body(self) -> str:
        return self.page.locator("body").inner_text()

    @staticmethod
    def pm(**parts: str) -> str:
        """The DOM id of a pattern-matching component: pm(type="mermaid-svg", id="el-view")."""
        return json.dumps(parts, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _sel(selector: str) -> str:
        """A bare component id is written as an id; a JSON id as an attribute; else CSS."""
        if re.fullmatch(r"[a-z0-9][a-z0-9-]*", selector):
            return f"#{selector}"
        if selector.startswith("{"):
            return f"[id={json.dumps(selector)}]"
        return selector

    # ------------------------------------------------------------------- session
    def persona(self, label: str) -> None:
        """Switch the debug persona in the header and wait for the page to re-render."""
        self.select("persona-select", label)
        self.page.wait_for_timeout(200)
        self.settle()

    def branch(self, label: str) -> None:
        self.select("branch-select", label)
        self.page.wait_for_timeout(200)
        self.settle()

    def role_badge(self) -> str:
        return self.text("role-badge")

    def branch_badge(self) -> str:
        return self.text("branch-badge")

    # ---------------------------------------------------------------- ag-grid
    def grid(self, grid_id: str) -> object:
        return self.page.locator(f"#{grid_id}").first

    def grid_row_count(self, grid_id: str) -> int:
        return self.page.locator(f"#{grid_id} .ag-center-cols-container .ag-row").count()

    def grid_cell(self, grid_id: str, row: int, col: str) -> str:
        loc = self.page.locator(f"#{grid_id} .ag-row[row-index='{row}'] .ag-cell[col-id='{col}']").first
        return loc.inner_text().strip() if loc.count() else ""

    def grid_click_cell(self, grid_id: str, row: int, col: str) -> None:
        self.page.locator(f"#{grid_id} .ag-row[row-index='{row}'] .ag-cell[col-id='{col}']").first.click()
        self.settle()

    def grid_tick(self, grid_id: str, rows: list[int]) -> None:
        for row in rows:
            box = self.page.locator(
                f"#{grid_id} .ag-row[row-index='{row}'] .ag-cell[col-id='sel'] input"
            ).first
            if box.count():
                box.click(force=True)
            else:
                self.page.locator(
                    f"#{grid_id} .ag-row[row-index='{row}'] .ag-selection-checkbox"
                ).first.click()
        self.settle()

    def grid_row_ids(self, grid_id: str) -> list[str]:
        return self.page.locator(f"#{grid_id} .ag-center-cols-container .ag-row").evaluate_all(
            "rows => rows.map(r => r.getAttribute('row-id'))"
        )

    def grid_cell_of(self, grid_id: str, row_id: str, col: str) -> str:
        """A cell addressed by the row's own id — the only address virtualisation cannot move."""
        loc = self.page.locator(
            f"#{grid_id} .ag-row[row-id={json.dumps(row_id)}] .ag-cell[col-id='{col}']"
        ).first
        return loc.inner_text().strip() if loc.count() else ""

    def grid_tick_of(self, grid_id: str, row_ids: list[str]) -> None:
        for row_id in row_ids:
            cell = self.page.locator(
                f"#{grid_id} .ag-row[row-id={json.dumps(row_id)}] .ag-cell[col-id='sel']"
            ).first
            cell.scroll_into_view_if_needed()
            box = cell.locator("input").first
            (box if box.count() else cell.locator(".ag-selection-checkbox").first).click(force=True)
        self.settle()

    def grid_set_of(self, grid_id: str, row_id: str, col: str, value: str) -> None:
        """Edit a cell addressed by row id, and assert on what the cell then renders."""
        cell = self.page.locator(
            f"#{grid_id} .ag-row[row-id={json.dumps(row_id)}] .ag-cell[col-id='{col}']"
        ).first
        cell.scroll_into_view_if_needed()
        cell.click()
        editor = self.page.locator(f"#{grid_id} .ag-cell-editor").first
        if editor.count():
            picker = editor.locator(".ag-picker-field-wrapper").first
            native = editor.locator("select").first
            if picker.count():
                picker.click()
                self.page.locator(f".ag-list-item:has-text({json.dumps(value)})").first.click()
            elif native.count():
                native.select_option(value)
            else:
                self.page.keyboard.press("Control+a")
                self.page.keyboard.type(value)
        else:
            cell.dblclick()
            self.page.keyboard.press("Control+a")
            self.page.keyboard.type(value)
        self.page.keyboard.press("Enter")
        self.settle()

    def grid_set(self, grid_id: str, row: int, col: str, value: str) -> None:
        """Type into an editable cell and commit it."""
        cell = self.page.locator(f"#{grid_id} .ag-row[row-index='{row}'] .ag-cell[col-id='{col}']").first
        cell.dblclick()
        self.page.keyboard.press("Control+a")
        self.page.keyboard.type(value)
        self.page.keyboard.press("Enter")
        self.settle()

    # ------------------------------------------------------------------ download
    def download(self, selector: str, expect_suffix: str = "") -> Path:
        with self.page.expect_download(timeout=30_000) as info:
            self.page.locator(self._sel(selector)).first.click()
        dl = info.value
        name = dl.suggested_filename
        path = self.run_dir / "downloads" / name
        dl.save_as(str(path))
        self.settle()
        if expect_suffix:
            self.must(
                f"the download is named {expect_suffix}",
                name.endswith(expect_suffix),
                f"got {name}",
            )
        self.must(f"{name} has content", path.stat().st_size > 0, f"{path.stat().st_size} bytes")
        return path

    # ------------------------------------------------------------------- viewport
    def narrow(self, width: int = 480, height: int = 900) -> None:
        self.page.set_viewport_size({"width": width, "height": height})
        self.page.wait_for_timeout(300)

    def wide(self, width: int = 1600, height: int = 1000) -> None:
        self.page.set_viewport_size({"width": width, "height": height})
        self.page.wait_for_timeout(300)
