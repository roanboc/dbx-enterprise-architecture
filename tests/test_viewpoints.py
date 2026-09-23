"""A viewpoint narrows a view to what it admits, bands it, and says what it left out.

The viewpoint is pack data (decision 0023): the application knows its grammar — element
types, relationship types, bands, nesting, spanning — and no viewpoint by name. These tests
apply it to the sample model and to a view built by hand, because the sample holds no
process or role content and seventeen assertions pin it at 47 elements. The command line
is proved the way `test_cli.py` proves the rest of it: in-process, against a seeded store.
"""

from __future__ import annotations

import pytest
from tests.conftest import PACK, SAMPLE
from typer.testing import CliRunner

from ea.backend.duckdb_backend import DuckDBBackend
from ea.cli import app
from ea.importer import import_directory
from ea.metamodel import Registry, load_pack
from ea.models import Viewpoint
from ea.views import DEFAULT_VIEWPOINT, View, ViewEdge, ViewNode, apply_viewpoint, view_from_neighbourhood
from ea.views.model import view_from_dict, view_to_dict

APPLICATION = "PAC-CMS"  # an application component with neighbours in several layers
ASSET = "IA-COURSE-CAT"  # an information asset stewarded by positions, which are roles
STEWARD = "POS-CURR-MGR"  # a Position: a sub-type of role in the higher-education pack


# ------------------------------------------------------------------ what a viewpoint admits


def test_a_sub_type_counts_as_its_supertype(registry, graph):
    """A viewpoint admitting roles admits positions: the pack says a position is a role."""
    view = view_from_neighbourhood(registry, graph, ASSET, 1)
    assert STEWARD in view.ids() and registry.is_a("position", "role")
    vp = Viewpoint(id="roles", name="Roles", element_types=["role", "information_asset"])
    out = apply_viewpoint(view, vp, registry)
    assert STEWARD in out.ids() and ASSET in out.ids()
    assert {n.type_id for n in out.nodes} <= {"position", "role", "information_asset"}
    dropped = len(view.nodes) - len(out.nodes)
    assert dropped > 0 and f"{dropped} element(s) outside the Roles viewpoint not shown." in out.note
    assert out.viewpoint == "roles" and out.focus_ids == [ASSET]


def test_relationship_types_not_admitted_are_left_out(registry, graph):
    view = view_from_neighbourhood(registry, graph, ASSET, 1)
    kinds = sorted({e.rel_type_id for e in view.edges if e.rel_type_id})
    assert len(kinds) > 1, "the neighbourhood needs more than one kind of relationship to prove this"
    vp = Viewpoint(id="one", name="One kind", relationship_types=[kinds[0]])
    out = apply_viewpoint(view, vp, registry)
    assert {e.rel_type_id for e in out.edges} == {kinds[0]}
    assert len(out.edges) < len(view.edges)
    assert out.ids() == view.ids()  # the element filter is empty, so every element stays


def test_an_edge_goes_with_either_end_it_loses(registry, graph):
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    vp = Viewpoint(id="apps", name="Applications", element_types=["physical_application_component"])
    out = apply_viewpoint(view, vp, registry)
    kept = set(out.ids())
    assert all(e.src in kept and e.dst in kept for e in out.edges)


def test_the_layers_kept_are_the_only_ones_drawn(registry, graph):
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    assert len(view.layers()) > 1
    out = apply_viewpoint(view, None, registry, layers=["application"])
    assert out.nodes and {n.layer for n in out.nodes} == {"application"}
    assert out.viewpoint == DEFAULT_VIEWPOINT.id
    assert "outside the Layered viewpoint not shown" in out.note


def test_the_note_says_when_the_focus_is_outside(registry, graph):
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    vp = Viewpoint(id="data", name="Data only", element_types=["data_entity"])
    out = apply_viewpoint(view, vp, registry)
    assert APPLICATION not in out.ids() and out.focus_ids == []
    assert f"The focus ({APPLICATION}) is outside this viewpoint." in out.note
    assert "outside the Data only viewpoint not shown" in out.note


def test_no_viewpoint_is_the_layered_drawing(registry, graph):
    view = view_from_neighbourhood(registry, graph, APPLICATION, 1)
    out = apply_viewpoint(view, None, registry)
    assert out.ids() == view.ids() and len(out.edges) == len(view.edges)
    assert out.viewpoint == "layered" and out.note == view.note


# ------------------------------------------------------------------ bands by a related element


def _node(nid: str, name: str, type_id: str, layer: str = "business") -> ViewNode:
    return ViewNode(
        id=nid, name=name, type_id=type_id, type_name=type_id.replace("_", " ").title(), layer=layer
    )


def _process_view() -> View:
    """Three processes and two roles, one of them a position: what the sample does not hold."""
    return View(
        title="Enrolment",
        focus_ids=["P1"],
        nodes=[
            _node("R1", "Registrar", "role"),
            _node("R2", "Admissions manager", "position"),
            _node("P1", "Enrol a student", "process"),
            _node("P2", "Admit an applicant", "process"),
            _node("P3", "Check prerequisites", "process"),
            _node("D1", "Student record", "data_entity", "application"),
        ],
        edges=[
            ViewEdge("R1", "P1", "performs", "role__performs__process"),
            ViewEdge("R2", "P2", "performs", "role__performs__process"),
            ViewEdge("P1", "P3", "contains", "process__contains__process"),
            ViewEdge("R1", "P3", "owns", "role__owns__process"),  # not a band relationship
        ],
    )


def test_bands_by_the_role_that_performs_a_process(registry):
    vp = registry.viewpoint("process_cooperation")
    assert vp is not None and vp.bands == "related" and vp.band_type == "role"
    out = apply_viewpoint(_process_view(), vp, registry)
    by_id = {n.id: n for n in out.nodes}
    assert by_id["R1"].is_band and by_id["R2"].is_band  # a position is a role, so it is a band too
    assert not any(by_id[p].is_band for p in ("P1", "P2", "P3"))
    assert by_id["P1"].band == "R1" and by_id["P2"].band == "R2"
    # Owned, not performed: the relationship is not one the viewpoint bands by, so the
    # process goes to the viewpoint's other band rather than being placed by a guess.
    assert by_id["P3"].band == ""
    assert "D1" not in by_id  # a data entity is not in the process cooperation viewpoint
    assert vp.other_band == "Not performed by a role"


def test_a_process_two_roles_perform_lands_in_the_first_by_name(registry):
    view = _process_view()
    view.edges.append(ViewEdge("R2", "P1", "performs", "role__performs__process"))
    out = apply_viewpoint(view, registry.viewpoint("process_cooperation"), registry)
    assert next(n for n in out.nodes if n.id == "P1").band == "R2"  # "Admissions manager" < "Registrar"


def test_the_new_fields_round_trip_through_a_dict(registry):
    vp = registry.viewpoint("process_cooperation")
    banded = apply_viewpoint(_process_view(), vp, registry)
    banded.edges[0].archimate, banded.edges[0].reversed = "assignment", True
    again = view_from_dict(view_to_dict(banded))
    assert again.viewpoint == "process_cooperation"
    assert [(n.id, n.band, n.is_band) for n in again.nodes] == [
        (n.id, n.band, n.is_band) for n in banded.nodes
    ]
    assert (again.edges[0].archimate, again.edges[0].reversed) == ("assignment", True)
    assert again.edges[0].whole == "P1" and again.edges[0].part == "R1"


# ------------------------------------------------------------------ the command line

runner = CliRunner()


@pytest.fixture(autouse=True)
def _scope_reset():
    """The command line sets the role, the branch and the organisation as context variables of
    the process, and the in-process runner never unwinds them."""
    from ea.backend.branching import MAIN, set_branch
    from ea.backend.organisations import DEFAULT_ORG, set_org
    from ea.services.roles import DEFAULT_ROLE, set_role

    yield
    set_role(DEFAULT_ROLE)
    set_branch(MAIN)
    set_org(DEFAULT_ORG)


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """A seeded DuckDB file the CLI finds through the environment, as a person's shell would."""
    db = tmp_path / "ea.duckdb"
    pack = load_pack(PACK)
    backend = DuckDBBackend(str(db))
    try:
        backend.save_pack(pack)
        report = import_directory(backend, Registry(pack), SAMPLE, "sample")
        assert report.ok, report.summary()
    finally:
        backend.close()
    monkeypatch.setenv("EA_DB_PATH", str(db))
    monkeypatch.setenv("EA_PACK", str(PACK))
    monkeypatch.setenv("EA_BACKEND", "duckdb")
    monkeypatch.setenv("EA_AGENT_PROVIDER", "stub")
    return tmp_path


def _table_ids(text: str) -> set[str]:
    return {line.split("`")[1] for line in text.splitlines() if line.startswith("| `")}


def test_viewpoints_lists_what_the_version_declares(cli_env, registry):
    result = runner.invoke(app, ["viewpoints"])
    assert result.exit_code == 0, result.output
    for v in registry.viewpoints():
        assert v.id in result.output and v.name in result.output
    assert "bands: by architecture layer" in result.output
    assert "bands: by element type (" in result.output
    assert "bands: by role via role__performs__process; other: Not performed by a role" in result.output
    assert "nests: " in result.output and "spans: " in result.output


def test_view_through_a_viewpoint_narrows_every_format(cli_env):
    whole = runner.invoke(app, ["view", APPLICATION, "--fmt", "md"])
    narrowed = runner.invoke(
        app, ["view", APPLICATION, "--viewpoint", "application_cooperation", "--fmt", "md"]
    )
    assert whole.exit_code == 0 and narrowed.exit_code == 0, narrowed.output
    assert _table_ids(narrowed.output) < _table_ids(whole.output)
    assert "outside the Application cooperation viewpoint not shown" in narrowed.output
    # A name, whatever its case, reaches the same viewpoint as its id.
    by_name = runner.invoke(
        app, ["view", APPLICATION, "--viewpoint", "application COOPERATION", "--fmt", "md"]
    )
    assert by_name.output == narrowed.output
    mermaid = runner.invoke(app, ["view", APPLICATION, "--viewpoint", "application_cooperation"])
    assert mermaid.exit_code == 0 and "flowchart" in mermaid.output
    drawio = runner.invoke(
        app, ["view", APPLICATION, "--viewpoint", "application_cooperation", "--fmt", "drawio"]
    )
    assert drawio.exit_code == 0 and "<mxfile" in drawio.output


def test_view_keeps_only_the_layers_named(cli_env):
    result = runner.invoke(app, ["view", APPLICATION, "--layers", "application", "--fmt", "md"])
    assert result.exit_code == 0, result.output
    whole = runner.invoke(app, ["view", APPLICATION, "--fmt", "md"])
    assert _table_ids(result.output) < _table_ids(whole.output)
    assert "outside the Layered viewpoint not shown" in result.output


def test_an_unknown_viewpoint_or_layer_is_refused_with_the_choices(cli_env):
    """Drawing the layered default instead would hand back a diagram nobody asked for."""
    result = runner.invoke(app, ["view", APPLICATION, "--viewpoint", "swimlanes"])
    assert result.exit_code == 1
    assert "no viewpoint 'swimlanes'" in result.output and "application_cooperation" in result.output
    layer = runner.invoke(app, ["view", APPLICATION, "--layers", "application,nowhere"])
    assert layer.exit_code == 1 and "no layer 'nowhere'" in layer.output and "technology" in layer.output


# ------------------------------------------------------------------- the overview
# Two levels of detail: an overview by a rule the reader can predict, and the full view.


def _ov_node(nid, layer="business", **kw):
    return ViewNode(id=nid, name=kw.pop("name", nid), type_id="t", type_name="T", layer=layer, **kw)


def _ov_edge(src, dst, label="relates", kind="association", rel="r", **kw):
    return ViewEdge(src=src, dst=dst, label=label, rel_type_id=rel, archimate=kind, **kw)


def test_an_overview_keeps_the_focus_its_neighbours_and_the_structural_lines():
    from ea.views import overview

    view = View(
        "v",
        focus_ids=["F"],
        nodes=[_ov_node("F"), _ov_node("A"), _ov_node("B"), _ov_node("C"), _ov_node("Z"), _ov_node("Y")],
        edges=[
            _ov_edge("F", "A", "accesses", "access"),  # touches the focus: kept whatever its kind
            _ov_edge("A", "B", "realises", "realization"),  # structural between neighbours: kept
            _ov_edge("B", "C", "accesses", "access"),  # a loose line beyond the focus: gone, and C with it
            _ov_edge("F", "B", "is associated with", "association"),
            _ov_edge("A", "B", "serves", "serving"),  # a second line between A and B: merged
            _ov_edge("Z", "A", "is associated with", "association"),  # two hops away by a loose line: gone
            _ov_edge("Y", "A", "flows to", "flow"),  # two hops away by a structural line: stays
        ],
    )
    out = overview(view)
    assert out.detail == "overview" and out.focus_ids == ["F"]
    assert [n.id for n in out.nodes] == ["F", "A", "B", "Y"]
    labels = {(e.src, e.dst): e.label for e in out.edges}
    assert labels == {
        ("F", "A"): "accesses",
        ("A", "B"): "realises, serves",
        ("F", "B"): "is associated with",
        ("Y", "A"): "flows to",
    }
    merged = next(e for e in out.edges if e.src == "A")
    assert merged.archimate == ""  # two kinds on one pair: a plain line carries both verbs
    assert "Overview: 2 element(s) and 3 relationship(s) not drawn." in out.note


def test_an_overview_without_a_focus_keeps_every_element_and_thins_the_lines():
    from ea.views import overview

    view = View(
        "v",
        nodes=[_ov_node("A"), _ov_node("B"), _ov_node("C")],
        edges=[_ov_edge("A", "B", "accesses", "access"), _ov_edge("B", "C", "composes", "composition")],
    )
    out = overview(view)
    assert [n.id for n in out.nodes] == ["A", "B", "C"]
    assert [(e.src, e.dst) for e in out.edges] == [("B", "C")]


def test_a_viewpoint_names_what_an_overview_keeps_and_what_it_nests_always_stays():
    from ea.views import overview

    vp = Viewpoint(id="v", name="v", nest=["holds"], overview_relationships=["uses"])
    view = View(
        "v",
        focus_ids=["F"],
        nodes=[_ov_node("F"), _ov_node("A"), _ov_node("B"), _ov_node("C")],
        edges=[
            _ov_edge("F", "A"),
            _ov_edge("F", "B"),
            _ov_edge("F", "C"),
            _ov_edge(
                "A", "B", "uses", "access", rel="uses"
            ),  # named by the viewpoint: kept though not structural
            _ov_edge(
                "B", "C", "realises", "realization", rel="r"
            ),  # structural, but the viewpoint names its own: gone
            _ov_edge("A", "C", "holds", "composition", rel="holds"),  # nested by the viewpoint: always kept
        ],
    )
    out = overview(view, vp)
    kept = {(e.src, e.dst) for e in out.edges}
    assert ("A", "B") in kept and ("A", "C") in kept and ("B", "C") not in kept


def test_an_overview_holds_at_most_thirty_elements_and_keeps_the_most_connected():
    from ea.views import overview
    from ea.views.model import OVERVIEW_MAX_NODES

    hub = _ov_node("F")
    others = [_ov_node(f"n{i:02d}") for i in range(40)]
    edges = [_ov_edge("F", n.id) for n in others]
    edges += [
        _ov_edge("n00", "n01", "realises", "realization"),
        _ov_edge("n00", "n02", "realises", "realization"),
    ]
    out = overview(View("v", focus_ids=["F"], nodes=[hub, *others], edges=edges))
    assert len(out.nodes) == OVERVIEW_MAX_NODES and "F" in {n.id for n in out.nodes}
    assert {"n00", "n01", "n02"} <= {n.id for n in out.nodes}  # the best connected stay
    assert "11 of them the least connected" in out.note


def test_band_elements_stay_in_an_overview():
    from ea.views import overview

    view = View(
        "v",
        focus_ids=["P"],
        nodes=[_ov_node("P"), _ov_node("R", is_band=True), _ov_node("Q", band="R")],
        edges=[_ov_edge("R", "Q", "performs", "assignment", rel="performs")],
    )
    out = overview(
        view, Viewpoint(id="v", name="v", bands="related", band_type="t", band_relationships=["performs"])
    )
    assert {n.id for n in out.nodes} == {"P", "R"}  # nothing joins Q to the focus; the band stays


def test_the_overview_on_the_sample_thins_a_neighbourhood(registry, graph):
    from ea.views import overview

    full = apply_viewpoint(
        view_from_neighbourhood(registry, graph, "LDC-CURR", 2), registry.viewpoint("layered"), registry
    )
    brief = overview(full, registry.viewpoint("layered"))
    assert len(brief.nodes) < len(full.nodes) and len(brief.edges) < len(full.edges)
    assert all(
        e.archimate
        in ("composition", "aggregation", "realization", "assignment", "serving", "triggering", "flow", "")
        for e in brief.edges
        if "LDC-CURR" not in (e.src, e.dst) and e.rel_type_id not in registry.viewpoint("layered").nest
    )
    assert brief.detail == "overview" and view_from_dict(view_to_dict(brief)).detail == "overview"


def test_view_at_the_overview_level_from_the_command_line(cli_env):
    full = runner.invoke(app, ["view", "LDC-CURR", "--depth", "2", "--fmt", "md"])
    brief = runner.invoke(app, ["view", "LDC-CURR", "--depth", "2", "--fmt", "md", "--detail", "overview"])
    assert brief.exit_code == 0 and full.exit_code == 0, brief.output
    assert brief.output.count("-->") < full.output.count("-->")
    assert "Overview:" in brief.output
    assert runner.invoke(app, ["view", "LDC-CURR", "--detail", "sketchy"]).exit_code != 0
