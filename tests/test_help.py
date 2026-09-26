"""Help where the work is done (initiative 27): every screen's help, in its parts; the button
beside every screen's title; the welcome and the tips shown once each, and remembered by the
browser rather than the store; and what the side panel says a role may do, read from the rule
that enforces it."""

from __future__ import annotations

import re

import dash
import pytest
from tests.test_feeds_page import _texts

from ea.services.guide import GUIDE_DIR, SCREENS, GuideService, parse_screen
from ea.services.roles import ACTIONS
from ea.ui import ids, layout, screen_help
from ea.ui.screen_help import (
    SCREEN_ACTIONS,
    after_action,
    demote,
    first_visit,
    help_body,
    pressed,
    role_block,
    seen_state,
)

NAV_KEYS = [href.strip("/") or "home" for _, links in layout.NAV_SECTIONS for _, href, _ in links]
SCREEN_KEYS = [*NAV_KEYS, "element"]


def _ids(component) -> list:
    """Every component id anywhere in a rendered tree."""
    out: list = []

    def walk(node):
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
            return
        if node is None or isinstance(node, (str, int, float)):
            return
        if getattr(node, "id", None) is not None:
            out.append(node.id)
        for attribute in ("children", "label", "title", "leftSection", "rightSection"):
            value = getattr(node, attribute, None)
            if value is not None and not isinstance(value, str):
                walk(value)

    walk(component)
    return out


# ------------------------------------------------------------------ the pages


@pytest.mark.parametrize("key", SCREEN_KEYS)
def test_every_screen_has_its_help_in_its_parts(registry, key):
    """A screen without help is a screen a newcomer learns from a colleague or not at all."""
    help_ = GuideService(registry).screen(key)
    assert help_ is not None, f"docs/guide/{SCREENS}/{key}.md is missing"
    assert help_.title and help_.tip, key
    assert len(help_.tip) <= 110, f"the tip of {key} is {len(help_.tip)} characters"
    headings = re.findall(r"^## (.+)$", help_.markdown, re.M)
    assert headings[:4] == ["Why", "What you see", "How", "The flow"], (key, headings)
    assert set(headings) <= {"Why", "What you see", "How", "The flow", "Tips"}, (key, headings)
    assert help_.markdown.count("```mermaid") == 1, f"{key} draws its flow once"
    assert all(k in SCREEN_KEYS for k in help_.related), (key, help_.related)


@pytest.mark.parametrize("key", SCREEN_KEYS)
def test_a_screen_s_help_links_nowhere_and_names_no_element_by_identifier(registry, key):
    """A link rooted at / breaks the repository's link check, and a label ending in [X] is read by
    the view script as an element identifier: the help draws the product, not the model."""
    text = (GUIDE_DIR / SCREENS / f"{key}.md").read_text(encoding="utf-8")
    assert "](" not in text, f"{key} carries a Markdown link"
    flow = text.split("```mermaid", 1)[1].split("```", 1)[0]
    assert not re.search(r"\[[A-Z]+[0-9.]*\]", flow), f"{key}'s diagram carries a bracketed identifier"


def test_no_page_is_left_over_for_a_screen_that_is_gone(registry):
    assert set(GuideService(registry).screens()) <= set(SCREEN_KEYS)


def test_a_page_is_read_into_its_parts():
    h = parse_screen(
        "browse",
        "<!-- related: element impact -->\n# Browse\n\n> Find an element\n> and open it.\n\n## Why\n\nText.",
    )
    assert (h.title, h.tip, h.related) == ("Browse", "Find an element and open it.", ["element", "impact"])
    assert h.markdown == "## Why\n\nText."


def test_a_key_that_is_not_a_page_name_reads_nothing(registry):
    guide = GuideService(registry)
    assert guide.screen("../README") is None and guide.screen("") is None and guide.screen("nope") is None


# ------------------------------------------------------ the button and the slot


@pytest.mark.parametrize(
    "module, key, args",
    [
        ("home", "home", ()),
        ("guide", "guide", ()),
        ("browse", "browse", (None,)),
        ("ask", "ask", (None,)),
        ("impact", "impact", (None,)),
        ("target", "target", (None,)),
        ("branches", "branches", (None,)),
        ("import_page", "import", ()),
        ("feeds", "feeds", ()),
        ("propose", "propose", ()),
        ("metamodel", "metamodel", ()),
        ("organisations", "organisations", (None,)),
        ("systems", "systems", ()),
        ("health", "health", ()),
        ("users", "users", ()),
    ],
)
def test_every_screen_carries_one_help_button_beside_its_title(app_context, module, key, args):
    import importlib

    page = importlib.import_module(f"ea.ui.pages.{module}").render(app_context, *args)
    found = _ids(page)
    buttons = [i for i in found if isinstance(i, dict) and i.get("type") == ids.HELP_OPEN]
    assert buttons == [{"type": ids.HELP_OPEN, "screen": key, "place": "title"}]
    assert found.count(ids.HELP_SCREEN) == 1 and found.count(ids.HELP_HINT) == 1


def test_the_element_page_carries_its_help_too(app_context):
    from ea.ui.pages import element

    some = app_context.repo.search(limit=1)[0]
    found = _ids(element.render(app_context, some.element_id))
    assert {"type": ids.HELP_OPEN, "screen": "element", "place": "title"} in found
    assert ids.HELP_SCREEN in found


def test_the_shell_keeps_what_was_closed_in_the_browser_and_holds_the_side_panel():
    shell = layout.shell("EA Repository", "pack", [{"value": "main", "label": "main"}])
    stores = [
        c for c in _walk(shell) if getattr(c, "id", None) == ids.HELP_SEEN and type(c).__name__ == "Store"
    ]
    assert stores and stores[0].storage_type == "local"
    drawer = next(c for c in _walk(shell) if getattr(c, "id", None) == ids.HELP_DRAWER)
    assert drawer.keepMounted is True and drawer.opened is False
    assert drawer.closeButtonProps == {"aria-label": "Close help"}


def _walk(node):
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, (list, tuple)):
            stack.extend(n)
            continue
        if n is None or isinstance(n, (str, int, float)):
            continue
        yield n
        for attribute in ("children", "title"):
            value = getattr(n, attribute, None)
            if value is not None and not isinstance(value, str):
                stack.append(value)


# --------------------------------------------------- the welcome and the tips


def test_the_welcome_shows_once_in_the_first_screen_a_browser_opens():
    kind, state = first_visit(None, "browse")
    assert kind == "welcome" and state["welcome"] is True and state["screens"] == ["browse"]
    assert first_visit(state, "browse")[0] is None  # the tip of the screen the welcome stood on is spent


def test_each_screen_s_tip_shows_once_while_tips_are_on():
    _, state = first_visit(None, "home")
    kind, state = first_visit(state, "ask")
    assert kind == "tip" and "ask" in state["screens"]
    assert first_visit(state, "ask")[0] is None
    off, _ = after_action("tips-off", state)
    assert first_visit(off, "impact")[0] is None


def test_the_guide_brings_the_welcome_and_the_tips_back():
    state, again = after_action("reset", {"welcome": True, "tips": False, "screens": ["ask"]})
    assert again is True and state == {"v": 1, "welcome": False, "tips": True, "screens": []}
    assert first_visit(state, "ask")[0] == "welcome"


def test_closing_changes_nothing_that_is_remembered():
    assert after_action("close", {"welcome": True}) == (None, False)


def test_a_record_from_elsewhere_starts_afresh():
    assert seen_state("nonsense") == {"v": 1, "welcome": False, "tips": True, "screens": []}
    assert seen_state({"welcome": 1, "screens": ["a", 3, None]})["screens"] == ["a"]
    assert first_visit({"welcome": True}, None) == (None, seen_state({"welcome": True}))


def test_a_button_drawn_with_no_clicks_is_not_a_press():
    button = {"type": ids.HELP_OPEN, "screen": "ask", "place": "title"}
    spec = [{"id": button, "property": "n_clicks"}]
    assert pressed(button, [None], spec) is False
    assert pressed(button, [1], spec) is True
    assert pressed("url", [1], spec) is False


# ------------------------------------------------------------- the side panel


def test_the_side_panel_draws_the_flow_and_says_what_the_role_may_do(app_context):
    body = help_body(app_context, "branches")
    text = _texts(body)
    assert "Your role" in text
    assert {"type": "mermaid-src", "id": "help-branches-mermaid-0"} in _ids(body)


def test_what_a_role_may_do_is_what_the_rule_allows():
    reader = _texts(role_block("branches", "reader"))
    assert "Another role is needed to create a branch (Architect)" in reader
    assert "approve a branch or send it back (Reviewer)" in reader
    admin = _texts(role_block("branches", "admin"))
    assert "You may create a branch" in admin and "merge a branch without a review" in admin
    assert "Another role" not in admin
    assert "Every role may read and use this screen." in _texts(role_block("impact", "reader"))


def test_every_action_the_side_panel_names_is_one_the_rule_knows():
    """A screen's help that names an action nobody enforces would promise what nothing keeps."""
    named = {a for actions in SCREEN_ACTIONS.values() for a, _ in actions}
    assert named <= set(ACTIONS), named - set(ACTIONS)
    assert set(SCREEN_ACTIONS) <= set(SCREEN_KEYS)


def test_a_page_s_own_headings_sit_under_the_one_that_holds_it():
    assert (
        demote("## Why\n### Deeper\ntext ## not a heading", 2)
        == "#### Why\n##### Deeper\ntext ## not a heading"
    )


def test_the_help_callbacks_are_wired_to_the_shell_and_the_pages():
    app = dash.Dash(__name__)
    screen_help.register(app)
    outputs = " ".join(str(cb["output"]) for cb in app.callback_map.values())
    for target in (ids.HELP_DRAWER, ids.HELP_BODY, ids.HELP_HINT, ids.HELP_SEEN):
        assert target in outputs, target
