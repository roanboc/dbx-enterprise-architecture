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
