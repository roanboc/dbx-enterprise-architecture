from __future__ import annotations

from ea.ui import ids
from ea.ui.components import MARKDOWN_SNIPPETS, markdown, markdown_editor


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, list):
        children = [children]
    for child in children:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def test_markdown_renders_mermaid_fences_as_diagrams():
    rendered = markdown("Intro\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\nOutro", "test-md")
    classes = [getattr(c, "className", "") for c in _walk(rendered)]
    component_ids = [getattr(c, "id", None) for c in _walk(rendered)]

    assert "ea-mermaid-frame" in classes
    assert "ea-mermaid" in classes
    # The render callback declares the reset control as an Input; reader views must ship it too.
    assert {"type": "mermaid-reset", "id": "test-md-mermaid-0"} in component_ids


def test_markdown_editor_exposes_toolbar_textarea_and_preview_ids():
    editor = markdown_editor("sample", "Description (Markdown)", value="**hello**")
    component_ids = [getattr(c, "id", None) for c in _walk(editor)]

    assert editor.id == {"type": ids.MD_WRAP, "id": "sample"}
    assert "mode-edit" in editor.className
    assert {"type": ids.MD_TEXT, "id": "sample"} in component_ids
    assert {"type": ids.MD_PREVIEW, "id": "sample"} in component_ids
    assert {"type": ids.MD_MODE, "id": "sample"} in component_ids
    assert {"type": ids.MD_INSERT, "id": "sample", "kind": "heading"} in component_ids
    assert {"type": ids.MD_INSERT, "id": "sample", "kind": "bold"} in component_ids
    assert {"type": ids.MD_INSERT, "id": "sample", "kind": "table"} in component_ids
    assert {"type": ids.MD_INSERT, "id": "sample", "kind": "mermaid"} in component_ids


def test_markdown_snippets_cover_basic_authoring_actions():
    assert MARKDOWN_SNIPPETS["heading"].startswith("## ")
    assert "**" in MARKDOWN_SNIPPETS["bold"]
    assert "| Column |" in MARKDOWN_SNIPPETS["table"]
    assert MARKDOWN_SNIPPETS["mermaid"].startswith("```mermaid")


def test_the_legend_above_a_diagram_is_a_chip_per_layer_in_that_layer_s_colour(registry, graph):
    """The layers are not drawn as boxes, so the names the boxes carried are chips, not a sentence.

    A reader matches a chip to a shape at a glance; a sentence naming a colour has to be
    translated back into the picture before it is of any use.
    """
    from ea.ui.components import layer_chips, mermaid_block
    from ea.views import view_from_neighbourhood
    from ea.views.mermaid import LAYER_STYLE

    view = view_from_neighbourhood(registry, graph, "LDC-CURR", 1)
    chips = layer_chips(view)
    labels = [c.children for c in chips.children]
    assert labels == ["Business", "Application"]  # the layers this view draws, top to bottom
    fills = [c.styles["root"]["backgroundColor"] for c in chips.children]
    assert fills == [LAYER_STYLE["business"][0], LAYER_STYLE["application"][0]]
    assert all(c.styles["root"]["color"] == "#333" for c in chips.children)  # readable on a pastel
    assert layer_chips(None) is None

    block = mermaid_block("test-view", "flowchart BT\n  a --> b\n", legend=chips)
    holder = next(
        n for n in _walk(block) if getattr(n, "id", None) == {"type": "mermaid-legend", "id": "test-view"}
    )
    assert holder.children is chips  # and a callback that redraws the diagram redraws them with it


def test_split_mode_has_a_divider_a_reader_drags_or_moves_with_the_arrow_keys():
    editor = markdown_editor("sample", "Description (Markdown)")
    body = next(c for c in _walk(editor) if getattr(c, "className", "") == "ea-md-body")
    assert [c.className for c in body.children] == ["ea-md-edit-pane", "ea-md-splitter", "ea-md-preview-pane"]
    props = body.children[1].to_plotly_json()["props"]
    assert props["role"] == "separator" and props["tabIndex"] == 0
    assert props["aria-orientation"] == "vertical" and props["aria-label"]
    assert (props["aria-valuemin"], props["aria-valuenow"], props["aria-valuemax"]) == (15, 50, 85)
    # the page remembers where each editor's divider was left, by the editor's name
    assert body.to_plotly_json()["props"]["data-editor"] == "sample"


def test_the_divider_moves_the_panes_and_both_fill_the_editor_s_height():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    css = (root / "assets" / "styles.css").read_text()
    split = re.search(r"\.ea-markdown-editor\.mode-split \.ea-md-edit-pane\s*\{([^}]*)\}", css)
    assert split and "var(--ea-split" in split.group(1), "the edit pane's width follows the divider"
    assert re.search(r"\.ea-markdown-editor\.mode-split \.ea-md-splitter\s*\{[^}]*col-resize", css)
    assert re.search(r"\.ea-markdown-editor\.mode-split \.ea-md-body\s*\{[^}]*resize: vertical", css)
    script = (root / "assets" / "ea-split.js").read_text()
    for handled in ("pointerdown", "ArrowLeft", "ArrowRight", "Home", "End", "dblclick", "aria-valuenow"):
        assert handled in script, handled


def test_a_page_s_front_matter_is_folded_away_rather_than_read_as_headings():
    """The comments in a template's front matter start with `#`; read as Markdown they became
    the preview's largest headings."""
    text = (
        "---\nproposal_template:\n  # The metamodel this template is typed in\n  name: X\n---\n# Proposal\n"
    )
    rendered = markdown(text, "fm")
    parts = rendered.children
    folded = parts[0]
    assert type(folded).__name__ == "Details" and "ea-front-matter" in folded.className
    code = folded.children[1].children
    assert code.startswith("```yaml\n") and "# The metamodel this template is typed in" in code
    rest = "".join(
        getattr(p, "children", "") for p in parts[1:] if isinstance(getattr(p, "children", ""), str)
    )
    assert rest.strip() == "# Proposal" and "The metamodel" not in rest
    # a page without front matter, or a rule further down, is left alone
    assert type(markdown("Intro\n\n---\n\nMore", "fm").children[0]).__name__ == "Markdown"
