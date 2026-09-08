"""The round claims to cover everything. This is where that claim is checked.

It reads the scenario modules as text — no browser, no application, nothing to install —
so the claim is checked on every change, by CI, in the job that already runs. A page, a
command or a download that nothing exercises fails here rather than being discovered by
a reader of the report noticing an absence.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "tests" / "ui"
SRC = ROOT / "src" / "ea"

# Every file the application can hand to a reader, and the control that produces it. The
# count is asserted against the call sites, so a new producer fails this test until a
# scenario downloads it.
DOWNLOAD_TRIGGERS = {
    "el-view-md": "the element view as Markdown",
    "el-view-drawio": "the element view as draw.io",
    "imp-view-md": "the impact view as Markdown",
    "imp-view-drawio": "the impact view as draw.io",
    "tg-view-md": "the target-state view as Markdown",
    "tg-view-drawio": "the target-state view as draw.io",
    "ask-doc-md": "the answer document as Markdown",
    "ask-doc-drawio": "the answer document as draw.io",
    "mm-export": "the metamodel as a YAML pack",
    "im-template": "the import template archive",
    "pr-template": "the Proposal Template",
}


def _scenario_modules() -> list[Path]:
    return sorted(UI.glob("test_*.py"))


def _suite_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in _scenario_modules())


@pytest.fixture(scope="module")
def suite() -> str:
    mods = _scenario_modules()
    if not mods:
        pytest.skip("the scenario modules have not been written yet")
    return _suite_source()


def _scenarios() -> list[dict]:
    """Every @pytest.mark.scenario in the suite, read without importing it."""
    out: list[dict] = []
    for path in _scenario_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                name = ast.unparse(deco.func)
                if not name.endswith("mark.scenario"):
                    continue
                # A value that is not a plain string — an f-string naming the identifier
                # the scenario created, say — is still a value. Keep the source of it.
                kwargs = {
                    kw.arg: (kw.value.value if isinstance(kw.value, ast.Constant) else ast.unparse(kw.value))
                    for kw in deco.keywords
                    if kw.arg
                }
                kwargs["module"] = path.name
                kwargs["test"] = node.name
                out.append(kwargs)
    return out


def test_every_scenario_declares_what_it_proves(suite: str) -> None:
    missing = [
        f"{s.get('module')}::{s.get('test')}"
        for s in _scenarios()
        if not all(s.get(k) for k in ("scenario_id", "group", "title", "expected"))
    ]
    assert not missing, f"scenarios missing scenario_id/group/title/expected: {missing}"


def test_scenario_ids_are_unique(suite: str) -> None:
    ids = [s["scenario_id"] for s in _scenarios() if s.get("scenario_id")]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"the same scenario id is used twice: {duplicates}"


def test_every_page_is_exercised(suite: str) -> None:
    from ea.ui.app import PAGES

    routes = {f"/{p}" for p in PAGES} | {"/element/"}
    missing = sorted(r for r in routes if r not in suite)
    assert not missing, f"no scenario opens: {missing}"


def test_every_command_line_command_is_exercised(suite: str) -> None:
    from ea.cli import app as cli_app

    names = {
        (c.name or (c.callback.__name__ if c.callback else "")).replace("_", "-")
        for c in cli_app.registered_commands
    }
    for group in cli_app.registered_groups:
        for c in group.typer_instance.registered_commands:  # type: ignore[union-attr]
            names.add(f"{group.name} {c.name or (c.callback.__name__ if c.callback else '')}")
    names = {n for n in names if n and not n.endswith("-cmd")}

    def is_run(name: str) -> bool:
        # A command reaches the runner as its own argument, so `branch list` is written
        # `"branch", "list"` rather than as one string.
        parts = [re.escape(part) for part in name.split()]
        pattern = r"[\"']\s*,\s*[\"']".join(parts)
        return bool(re.search(rf"[\"']{pattern}[\"']", suite))

    missing = sorted(n for n in names if not is_run(n))
    assert not missing, f"no scenario runs: {missing}"


def test_every_download_producer_is_exercised(suite: str) -> None:
    missing = sorted(f"{k} ({v})" for k, v in DOWNLOAD_TRIGGERS.items() if k not in suite)
    assert not missing, f"nothing downloads: {missing}"


def _download_trigger_ids() -> set[str]:
    """The controls that produce a file: the inputs of every callback writing the download."""
    import ea.ui.ids as ids

    found: set[str] = set()
    for path in (SRC / "ui").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for block in re.split(r"@app\.callback", text)[1:]:
            head = block.split("def ", 1)[0]
            if "ids.DOWNLOAD" not in head:
                continue
            for const in re.findall(r"Input\(\s*ids\.([A-Z0-9_]+)", head):
                value = getattr(ids, const, None)
                if isinstance(value, str):
                    found.add(value)
    return found


def test_the_download_producers_are_all_listed() -> None:
    """A producer added to the application must gain a scenario, not slip past this file."""
    found = _download_trigger_ids()
    missing = sorted(found - set(DOWNLOAD_TRIGGERS))
    stale = sorted(set(DOWNLOAD_TRIGGERS) - found)
    assert not missing, f"the application produces files this file does not list: {missing}"
    assert not stale, f"this file lists producers the application no longer has: {stale}"


def test_every_role_is_exercised(suite: str) -> None:
    from ea.models import ROLES

    people = [r for r in ROLES if r != "agent"]  # the agent role belongs to tools, not a person
    missing = sorted(r for r in people if r not in suite.lower())
    assert not missing, f"no scenario runs as: {missing}"


def test_most_component_ids_are_exercised(suite: str) -> None:
    """Not every id is a control a reader touches, so this reports rather than demands 100%."""
    import ea.ui.ids as ids

    values = {
        v
        for k, v in vars(ids).items()
        if not k.startswith("_") and isinstance(v, str) and re.fullmatch(r"[a-z][a-z0-9-]+", v)
    }
    touched = {v for v in values if v in suite}
    share = len(touched) / len(values)
    untouched = sorted(values - touched)
    assert share >= 0.6, (
        f"only {share:.0%} of the {len(values)} component ids are named by a scenario; untouched: {untouched}"
    )
