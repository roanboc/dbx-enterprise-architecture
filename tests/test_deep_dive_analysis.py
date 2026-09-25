"""A deep dive's brief and its analysis (initiative 25, BPROC3), on both engines.

The brief is settled in conversation — a few questions, each with the choices the model
allows — and the analysis is rules over the store: the scope each kind reads, the maturity of
every element it rests on, where an element and its documentation disagree, and the seven
findings. Everything a reader is shown comes from the model; a hosted model only reads the
reader's words and writes the summary, and every identifier it cites is checked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ea.agent.deep_dive import (
    MAX_KEY,
    MAX_SCOPE,
    Brief,
    DeepDiveAnalyst,
    confidence,
)
from ea.agent.llm import ModelError, Reply, ToolUse
from ea.backend.branching import use_branch
from ea.models import Branch, DeepDive, DeepDiveElement, Element, Link, Relationship
from ea.services import DeepDiveService, GraphService, use_role
from ea.views.model import view_from_dict

NOW = datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def analyst(loaded, registry):
    return DeepDiveAnalyst(loaded, registry)


def _brief(subject: list[str], kind: str, reach: int = 2, **over) -> Brief:
    b = Brief(question="?", subject=subject, kind=kind, reach=reach, settled=["subject", "kind"])
    for k, v in over.items():
        setattr(b, k, v)
    return b


def _figures(d: DeepDive, level: int) -> list[dict]:
    return next(lv for lv in d.content["levels"] if lv["level"] == level)["figures"]


def _findings(d: DeepDive, rule: str) -> list[dict]:
    return [f for f in d.content["findings"] if f["rule"] == rule]


# ------------------------------------------------------------------ the brief
def test_a_question_naming_an_element_starts_a_brief_about_it(analyst):
    brief = analyst.start("What happens if PAC-CMS is decommissioned?")
    assert brief.subject == ["PAC-CMS"] and brief.kind == "impact"
    assert brief.ready() and "subject" in brief.settled and "kind" not in brief.settled
    questions = {q.qid: q for q in analyst.questions(brief)}
    assert list(questions) == ["subject", "kind", "reach", "layers", "purpose"]
    assert questions["subject"].settled and "Curriculum Management System" in questions["subject"].answer
    assert questions["kind"].options[0]["key"] == "impact"  # what the words point to, first
    assert {o["key"] for o in questions["kind"].options} == {
        "impact",
        "landscape",
        "transition",
        "flow",
        "quality",
    }
    assert questions["purpose"].optional and questions["purpose"].free


def test_words_without_an_identifier_are_searched_as_names(analyst):
    brief = analyst.start("Tell me about the learning management system")
    assert brief.subject == [] and not brief.ready()
    subject = analyst.questions(brief)[0]
    assert subject.options[0]["key"] == "el:PAC-LMS"
    assert subject.options[-1]["key"] == "other" and subject.options[-1]["needs"] == "text"
    brief = analyst.answer(brief, "subject", "el:PAC-LMS")
    assert brief.subject == ["PAC-LMS"] and "subject" in brief.settled
    # the reader's own words, read without a model, are searched as names too
    brief = analyst.answer(brief, "subject", "other", "the student records system")
    assert brief.subject == ["PAC-SRS"]


def test_a_work_package_is_offered_for_a_transition(analyst):
    brief = analyst.start("What does the curriculum management system upgrade change?")
    assert brief.kind == "transition"
    keys = [o["key"] for o in analyst.questions(brief)[0].options]
    assert "wp:WP-CMS-UPGRADE" in keys
    brief = analyst.answer(brief, "subject", "wp:WP-CMS-UPGRADE")
    assert brief.work_package == "WP-CMS-UPGRADE" and brief.subject == [] and brief.ready()


def test_each_answer_changes_the_brief_and_the_sentence_says_it(analyst):
    brief = analyst.start("PAC-CMS")
    brief = analyst.answer(brief, "kind", "landscape")
    brief = analyst.answer(brief, "reach", "3")
    brief = analyst.answer(brief, "layers", "application,technology")
    brief = analyst.answer(brief, "purpose", "text", "decide whether to replace it")
    assert (brief.kind, brief.reach, brief.layers) == ("landscape", 3, ["application", "technology"])
    sentence = analyst.sentence(brief)
    assert sentence.startswith("A landscape analysis of Curriculum Management System [PAC-CMS]")
    assert "three steps" in sentence and "application and technology" in sentence
    assert "decide whether to replace it" in sentence
    brief = analyst.answer(brief, "layers", "all")
    assert brief.layers == [] and "every layer" in analyst.sentence(brief)
    with pytest.raises(ValueError):
        analyst.answer(brief, "kind", "horoscope")
    assert analyst.answer(brief, "reach", "9").reach == 3


def test_a_brief_survives_the_round_trip_a_page_gives_it(analyst):
    brief = analyst.answer(analyst.start("impact of PAC-CMS"), "purpose", "text", "budget")
    assert Brief.from_dict(brief.to_dict()) == brief


def test_the_earlier_deep_dives_on_the_subject_are_listed_best_rated_first(loaded, registry, analyst):
    dives = DeepDiveService(loaded, registry)
    with use_role("reader"):
        low = dives.keep(
            DeepDive(title="Low", brief={}, content={}, elements=[DeepDiveElement("PAC-CMS", "subject")]),
            "ada",
        )
        high = dives.keep(
            DeepDive(title="High", brief={}, content={}, elements=[DeepDiveElement("PAC-CMS", "subject")]),
            "ada",
        )
        dives.rate(low.deep_dive_id, "bob", 2)
        dives.rate(high.deep_dive_id, "bob", 5)
    assert [d.title for d in analyst.earlier(analyst.start("PAC-CMS"))] == ["High", "Low"]


# ------------------------------------------------------------------ maturity
def test_maturity_is_read_from_what_each_element_carries(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "landscape"))
    level = {i: row["maturity"] for i, row in d.content["elements"].items()}
    assert level["PAC-CMS"] == 5  # described, related, approved and refreshed recently
    assert level["PAC-CAW"] == 3  # described and related, but still a draft
    assert level["DEF-COURSE"] == 1  # approved, and nothing written about it
    assert d.content["elements"]["DEF-COURSE"]["maturity_label"] == "Named"
    assert "description" in d.content["elements"]["DEF-COURSE"]["maturity_why"]
    kept = {e.element_id: e.maturity for e in d.elements}
    assert kept["PAC-CMS"] == 5 and kept["DEF-COURSE"] == 1


def test_an_element_not_refreshed_for_long_is_approved_but_not_current(loaded, registry):
    later = DeepDiveAnalyst(loaded, registry, now=NOW + timedelta(days=400))
    d = later.analyse(_brief(["PAC-CMS"], "impact"))
    assert d.content["elements"]["PAC-CMS"]["maturity"] == 4
    assert _findings(d, "maturity")  # the content its source has not refreshed for long


def test_the_confidence_follows_the_maturity_of_what_it_rests_on():
    assert confidence([5, 5, 4, 4])["level"] == "high"
    assert confidence([3, 3, 4, 2])["level"] == "medium"
    low = confidence([1, 1, 2, 5])
    assert low["level"] == "low" and "named" in low["text"].lower()
    assert confidence([])["level"] == "low"


# ---------------------------------------------------------- inconsistencies
def test_a_description_naming_an_element_nothing_joins_it_to_is_an_inconsistency(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "landscape"))
    named = [i for i in d.content["inconsistencies"] if i["rule"] == "names_unrelated"]
    assert any(i["element_id"] == "PAC-CAW" and i["other_id"] == "PAC-CMS" for i in named)
    # related elements that name each other are consistent
    assert not any(i["element_id"] == "POS-CURR-MGR" and i["other_id"] == "PAC-CMS" for i in named)


def test_a_name_inside_a_longer_name_the_description_uses_is_not_a_mention(analyst):
    # "curriculum management system" names PAC-CMS, not LAC-CMS "Curriculum Management"
    d = analyst.analyse(_brief(["PAC-CMS"], "landscape"))
    named = [i for i in d.content["inconsistencies"] if i["rule"] == "names_unrelated"]
    assert not any(i["other_id"] == "LAC-CMS" for i in named)


def test_approved_with_nothing_written_is_an_inconsistency(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "landscape"))
    status = {i["element_id"] for i in d.content["inconsistencies"] if i["rule"] == "status"}
    assert "LAC-CMS" in status and "PAC-CMS" not in status


def test_a_live_element_related_to_a_retired_one_is_an_inconsistency(loaded, analyst):
    e = loaded.get_element("PTC-RDBMS")
    e.current_state = "retired"
    loaded.update_element(e, "test")
    d = analyst.analyse(_brief(["PAC-SRS"], "impact"))
    state = [i for i in d.content["inconsistencies"] if i["rule"] == "state"]
    assert any({i["element_id"], i["other_id"]} == {"PAC-SRS", "PTC-RDBMS"} for i in state)


def test_a_malformed_or_repeated_link_is_an_inconsistency(loaded, analyst):
    loaded.set_links(
        "PAC-CMS",
        [
            Link("PAC-CMS", "https://example.edu/cmdb/cms", "CMDB"),
            Link("PAC-CMS", "https://example.edu/cmdb/cms", "CMDB again"),
            Link("PAC-CMS", "wiki page somewhere", "Design"),
        ],
        "test",
    )
    d = analyst.analyse(_brief(["PAC-CMS"], "impact"))
    links = [i for i in d.content["inconsistencies"] if i["rule"] == "link" and i["element_id"] == "PAC-CMS"]
    assert len(links) == 2
    assert d.content["elements"]["PAC-CMS"]["maturity"] == 1  # its documentation is broken


# ------------------------------------------------------------------ findings
def test_many_elements_depending_on_one_is_a_single_point_of_dependency(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "landscape"))
    points = _findings(d, "single_point")
    assert any(f["elements"][0] == "IA-COURSE-CAT" for f in points)


def test_a_work_package_planning_a_change_is_not_a_dependant(analyst):
    d = analyst.analyse(_brief([], "transition", work_package="WP-CMS-UPGRADE"))
    assert all("WP-CMS-UPGRADE" not in f["elements"] for f in _findings(d, "single_point"))


def test_what_stays_related_to_an_element_being_decommissioned_is_a_finding(loaded, analyst):
    loaded.insert_relationship(
        Relationship(
            "R-FORMS-LMS",
            "physical_technology_component__realises__physical_application_component",
            "PTC-FORMS",
            "PAC-LMS",
        ),
        "test",
    )
    d = analyst.analyse(_brief(["PTC-FORMS"], "impact"))
    retiring = _findings(d, "retiring")
    assert retiring and retiring[0]["severity"] == "high"
    assert {"PTC-FORMS", "PAC-LMS"} <= set(retiring[0]["elements"])
    # the relationship that leaves with it is not left pointing at nothing
    assert all("PAC-CMS" not in f["elements"] for f in retiring)


def test_a_change_reaching_outside_its_work_package_is_a_finding(analyst):
    d = analyst.analyse(_brief([], "transition", work_package="WP-CMS-UPGRADE"))
    outside = _findings(d, "outside_package")
    assert outside
    reached = set(outside[0]["elements"])
    assert "IA-UNIT-OUTLINES" in reached and "PAC-CMS" in reached
    assert d.work_package == "WP-CMS-UPGRADE"


def test_an_element_below_the_business_that_traces_up_to_nothing_is_a_finding(loaded, analyst):
    loaded.insert_element(
        Element(
            "PAC-ORPHAN",
            "physical_application_component",
            "Orphan Tool",
            description_md="A tool nothing else in the model relates to at all.",
            status="approved",
        ),
        "test",
    )
    d = analyst.analyse(_brief(["PAC-ORPHAN"], "impact"))
    untraced = _findings(d, "untraced")
    assert untraced and untraced[0]["elements"] == ["PAC-ORPHAN"] and untraced[0]["severity"] == "high"
    assert d.content["elements"]["PAC-ORPHAN"]["maturity"] == 2  # described, related to nothing
    assert d.content["confidence"]["level"] == "low"
    assert _findings(d, "maturity")


def test_a_declared_relationship_type_with_no_instance_is_a_finding(loaded, registry, analyst):
    empty = GraphService(loaded, registry).completeness("capability")["empty"]
    d = analyst.analyse(_brief(["CAP-CURR-DEV"], "impact"))
    got = _findings(d, "empty_relationship")
    assert bool(got) == bool(empty)
    if got:
        assert got[0]["severity"] == "low" and got[0]["elements"] == ["CAP-CURR-DEV"]


def test_disagreeing_documentation_is_a_finding(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "landscape"))
    doc = _findings(d, "documentation")
    assert doc and "PAC-CAW" in doc[0]["elements"]


def test_every_finding_cites_elements_the_deep_dive_holds(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "landscape"))
    held = set(d.content["elements"])
    for f in d.content["findings"]:
        assert f["severity"] in ("high", "medium", "low") and f["level"] in (1, 2, 3, 4)
        assert f["elements"] and set(f["elements"]) <= held, f
        assert f["id"].startswith("F") and f["text"] and f["why"]


def test_the_purpose_puts_the_findings_it_is_about_first(analyst):
    plain = analyst.analyse(_brief(["PAC-CMS"], "landscape"))
    about = analyst.analyse(
        _brief(["PAC-CMS"], "landscape", purpose="whether the documentation can be trusted")
    )
    assert plain.content["headline"][0]["rule"] != "documentation"
    assert about.content["headline"][0]["rule"] == "documentation"


# ------------------------------------------------------------ top-down levels
def test_a_deep_dive_reads_from_the_top_down_in_two_styles(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "impact"))
    levels = d.content["levels"]
    assert [lv["level"] for lv in levels] == [1, 2, 3, 4]
    assert [lv["title"] for lv in levels] == ["Context", "Overview", "Architecture", "Detail"]
    assert [lv["style"] for lv in levels] == ["presentation", "presentation", "architecture", "architecture"]
    assert [f["kind"] for f in _figures(d, 1)] == ["context_map"]
    assert [f["kind"] for f in _figures(d, 2)] == [
        "layer_bands",
        "heat_map",
        "chart_maturity",
        "chart_findings",
    ]
    assert all(f["kind"] == "view" for f in _figures(d, 3) + _figures(d, 4))
    fids = [f["fid"] for lv in levels for f in lv["figures"]]
    assert fids == sorted(fids, key=lambda x: tuple(int(p) for p in x.split("."))) and len(set(fids)) == len(
        fids
    )


def test_every_shape_stands_for_an_element_the_deep_dive_holds_and_a_chart_for_none(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "impact"))
    held = set(d.content["elements"])
    ctx = _figures(d, 1)[0]
    assert ctx["centre"] == ["PAC-CMS"]
    assert {i for g in ctx["groups"] for i in g["ids"]} <= held
    assert any(g["key"] == "serves" and "CAP-CURR-DEV" in g["ids"] for g in ctx["groups"])
    assert any(g["key"] == "who" and "POS-CURR-MGR" in g["ids"] for g in ctx["groups"])
    bands, heat, mat, fin = _figures(d, 2)
    assert {i for b in bands["bands"] for i in b["ids"]} <= held
    assert {c["id"] for c in heat["cells"]} <= held
    for chart in (mat, fin):
        assert "ids" not in str(chart) and all(set(s) == {"label", "value"} for s in chart["series"])
    assert sum(s["value"] for s in mat["series"]) == len(heat["cells"])
    for f in _figures(d, 3) + _figures(d, 4):
        view = view_from_dict(f["view"])
        assert view.nodes and set(view.ids()) <= held, f["title"]


@pytest.mark.parametrize(
    ("kind", "titles"),
    [
        ("impact", ["What it serves", "Depends on it (upstream)", "It depends on (downstream)"]),
        ("flow", ["Where it comes from", "Where it goes", "The whole flow"]),
        ("quality", ["The area, its findings marked"]),
    ],
)
def test_each_kind_draws_its_own_architecture(analyst, kind, titles):
    d = analyst.analyse(_brief(["PAC-CMS"], kind))
    assert [f["title"] for f in _figures(d, 3)] == titles


def test_a_landscape_draws_one_view_per_layer_band(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "landscape"))
    bands = [b["title"] for b in _figures(d, 2)[0]["bands"]]
    assert [f["title"] for f in _figures(d, 3)] == bands
    assert {"Strategy", "Business", "Application", "Technology"} <= set(bands)


def test_a_transition_draws_the_package_as_it_is_as_targeted_and_what_it_touches(analyst):
    d = analyst.analyse(_brief([], "transition", work_package="WP-CMS-UPGRADE"))
    views = _figures(d, 3)
    assert [f["title"] for f in views] == ["As it is", "As targeted", "What it touches outside the package"]
    assert views[1]["marked"] and not views[0]["marked"]
    targeted = view_from_dict(views[1]["view"])
    assert {"PAC-CAW", "PTC-FORMS", "PAC-CMS"} <= set(targeted.ids())
    # what is only proposed or planned — the work package itself among them — is not there yet
    assert not {"PAC-CAW", "IF-CMS-SRS", "WP-CMS-UPGRADE"} & set(view_from_dict(views[0]["view"]).ids())


def test_the_detail_zooms_into_the_key_elements_subject_first(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "landscape"))
    detail = _figures(d, 4)
    assert 1 <= len(detail) <= MAX_KEY
    assert detail[0]["element_id"] == "PAC-CMS" and detail[0]["view"]["focus_ids"] == ["PAC-CMS"]


def test_the_layers_asked_for_narrow_what_is_read(analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "landscape", layers=["application"]))
    layers = {row["layer"] for i, row in d.content["elements"].items() if row["role"] != "context"}
    assert layers == {"application"}


# ------------------------------------------------------------ what is kept
def test_the_analysis_is_a_deep_dive_ready_to_keep(loaded, registry, analyst):
    d = analyst.analyse(_brief(["PAC-CMS"], "impact", purpose="replace it"))
    assert d.deep_dive_id == "" and d.kind == "impact" and d.title.startswith("Impact: Curriculum Management")
    assert d.brief["subject"] == ["PAC-CMS"] and d.brief["purpose"] == "replace it"
    roles = {e.element_id: e.role for e in d.elements}
    assert roles["PAC-CMS"] == "subject" and roles["CAP-CURR-DEV"] == "drawn"
    assert d.content["summary"] and d.content["brief_sentence"].startswith("An impact analysis")
    assert d.content["trace"]["provider"] == "rules" and d.content["trace"]["steps"]
    with use_role("reader"):
        kept = DeepDiveService(loaded, registry).keep(d, "ada")
    assert "physical_application_component" in kept.type_ids and kept.content == d.content


def test_a_deep_dive_run_again_names_the_one_it_came_from(loaded, registry, analyst):
    with use_role("reader"):
        first = DeepDiveService(loaded, registry).keep(analyst.analyse(_brief(["PAC-CMS"], "impact")), "ada")
    again = analyst.again(first)
    assert again.from_deep_dive == first.deep_dive_id and again.subject == ["PAC-CMS"]
    d = analyst.analyse(again)
    assert d.content["references"]["deep_dives"][0]["deep_dive_id"] == first.deep_dive_id


def test_an_analysis_stays_within_what_a_request_may_read(loaded, registry, monkeypatch):
    analyst = DeepDiveAnalyst(loaded, registry)

    def refuse():
        raise AssertionError("a deep dive built the whole in-process graph")

    monkeypatch.setattr(analyst.graph, "graph", refuse)
    for kind in ("impact", "landscape", "flow", "quality"):
        d = analyst.analyse(_brief(["PAC-CMS"], kind, reach=3))
        assert len([r for r in d.content["elements"].values() if r["role"] != "context"]) <= MAX_SCOPE


def test_a_deep_dive_reads_the_branch_the_reader_is_on(loaded, registry, analyst):
    loaded.create_branch(Branch("b-dd", "Try"), "ada")
    with use_branch("b-dd"):
        loaded.insert_element(
            Element("PAC-NEW", "physical_application_component", "Brand New System", status="draft"), "ada"
        )
        loaded.insert_relationship(
            Relationship(
                "R-NEW",
                "physical_application_component__realises__capability",
                "PAC-NEW",
                "CAP-CURR-DEV",
            ),
            "ada",
        )
        on_branch = analyst.analyse(_brief(["CAP-CURR-DEV"], "landscape", reach=1))
    on_main = analyst.analyse(_brief(["CAP-CURR-DEV"], "landscape", reach=1))
    assert "PAC-NEW" in on_branch.content["elements"] and "PAC-NEW" not in on_main.content["elements"]


# ---------------------------------------------------------- a hosted model
class _Model:
    """A stand-in for a hosted model: plays back the replies it is given, and records the asks."""

    provider, model = "test", "stand-in"

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def turn(self, system, messages, tools):
        self.seen.append((system, list(messages), [t["name"] for t in tools]))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _say(text: str) -> Reply:
    return Reply(text, [], "end", "stand-in", {"role": "assistant", "content": text})


def _call(name: str, args: dict) -> Reply:
    return Reply("", [ToolUse("t1", name, args)], "tools", "stand-in", {"role": "assistant", "content": ""})


def test_a_hosted_model_reads_the_reader_s_words_into_the_brief(loaded, registry):
    model = _Model(
        [
            _call("search_elements", {"text": "curriculum"}),
            _call(
                "settle_brief",
                {
                    "subject": ["PAC-CMS", "PAC-NOPE"],
                    "kind": "impact",
                    "reach": 2,
                    "purpose": "plan the upgrade",
                    "ask": "Should the approval workflow be counted as part of it?",
                },
            ),
            _say("Settled."),
        ]
    )
    analyst = DeepDiveAnalyst(loaded, registry, model=model)
    brief = analyst.start("what breaks if we swap out the curriculum system?")
    assert brief.subject == ["PAC-CMS"]  # an identifier no tool returned is dropped
    assert (brief.kind, brief.purpose) == ("impact", "plan the upgrade")
    questions = analyst.questions(brief)
    assert questions[-1].qid == "assistant" and questions[-1].asked_by == "assistant"
    assert "approval workflow" in questions[-1].text
    assert "search_elements" in model.seen[0][2] and "settle_brief" in model.seen[0][2]


def test_a_hosted_model_writes_the_summary_and_its_identifiers_are_checked(loaded, registry):
    model = _Model(
        [_say("Replacing Curriculum Management System [PAC-CMS] touches [CAP-CURR-DEV] and [XYZ-MADEUP].")]
    )
    d = DeepDiveAnalyst(loaded, registry, model=model).analyse(_brief(["PAC-CMS"], "impact"))
    assert d.content["summary"].startswith("Replacing Curriculum")
    assert d.content["trace"]["ungrounded"] == ["XYZ-MADEUP"]
    assert d.content["trace"]["provider"] == "test"


def test_without_the_model_the_rules_still_answer(loaded, registry):
    model = _Model([ModelError("the endpoint is asleep")])
    d = DeepDiveAnalyst(loaded, registry, model=model).analyse(_brief(["PAC-CMS"], "impact"))
    assert d.content["summary"] and d.content["trace"]["provider"] == "rules"
    assert "asleep" in d.content["trace"]["model_error"]
