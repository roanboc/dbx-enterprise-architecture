"""The graph panel: grouping, prefixed ids, grid positions without overlaps, type graph."""

from ea.ui import graph as gp


def _raw(registry, graph):
    return gp.raw_from_subgraph(registry, graph.neighbours("LDC-CURR", 1))


def test_grouping_by_domain_makes_parents_and_prefixed_ids(registry, graph):
    els = gp.elements(registry, _raw(registry, graph), "domain", "grouped")
    groups = [e for e in els if e["classes"] == "group"]
    nodes = [e for e in els if e["data"].get("element_id")]
    edges = [e for e in els if "source" in e["data"]]
    assert {g["data"]["label"] for g in groups} == {"Information", "Integration"}
    assert all(
        n["data"]["id"].startswith("domain:") and n["data"]["parent"].startswith("g:domain:") for n in nodes
    )
    assert all(
        e["data"]["source"].startswith("domain:") and e["data"]["target"].startswith("domain:") for e in edges
    )
    centre = [n for n in nodes if n["data"]["centre"]]
    assert len(centre) == 1 and centre[0]["data"]["element_id"] == "LDC-CURR"
    assert all(n["data"]["fill"].startswith("#") and n["data"]["stroke"].startswith("#") for n in nodes)


def test_grouped_grid_positions_do_not_overlap(registry, graph):
    els = gp.elements(registry, _raw(registry, graph), "type", "grouped")
    pos = [e["position"] for e in els if "position" in e]
    assert len(pos) == 16
    for i, a in enumerate(pos):
        for b in pos[i + 1 :]:
            assert abs(a["x"] - b["x"]) >= gp.NODE_W or abs(a["y"] - b["y"]) >= gp.NODE_H


def test_no_grouping_and_other_layouts(registry, graph):
    els = gp.elements(registry, _raw(registry, graph), "", "organic")
    assert not [e for e in els if e["classes"] == "group"]
    assert all("position" not in e for e in els)
    assert gp.layout_spec("organic")["name"] == "cose-bilkent"
    assert gp.layout_spec("grouped")["name"] == "preset"


def test_type_graph_has_any_diamond_and_subtype_edges(registry):
    raw = gp.raw_from_types(registry)
    assert any(n["kind"] == "any" for n in raw["nodes"])
    assert any(e["kind"] == "sub" for e in raw["edges"])
    els = gp.elements(registry, raw, "domain", "grouped")
    any_node = next(e for e in els if e["classes"] == "any")
    assert not gp.is_element_node(any_node["data"])
    assert not any_node["data"].get("parent")
    typed = next(e for e in els if e["classes"].startswith("type"))
    assert gp.is_element_node(typed["data"]) and gp.element_id_of(typed["data"]) == typed["data"]["type_id"]


def test_every_layout_spec_leaves_cytoscape_its_defaults():
    """A spec travels as JSON, so an option set to None arrives as null and replaces the
    layout's own default rather than leaving it be. Concentric's `concentric` is a function
    Cytoscape calls on every node; null there threw on every run, and the half-applied update
    it left behind lost the group boxes in every layout chosen after it."""

    def nulls(value, path=""):
        if value is None:
            return [path]
        if isinstance(value, dict):
            return [p for k, v in value.items() for p in nulls(v, f"{path}.{k}")]
        return []

    for option in gp.LAYOUT_OPTIONS:
        spec = gp.layout_spec(option["value"])
        assert not nulls(spec), f"{option['label']} sets {nulls(spec)} to null"
        assert spec["name"], option
