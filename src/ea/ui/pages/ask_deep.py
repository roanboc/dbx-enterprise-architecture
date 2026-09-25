"""Ask's deep mode (initiative 25, BPROC3): a brief settled in conversation, then a deep dive, kept.

The reader says what they need to know; the assistant settles the brief with them — what it is
about, which kind of analysis, how far it reaches, which layers, what it is for — each question
with the choices the model allows, as Propose asks about a draft. The brief reads as one
sentence before anything is written, beside the earlier deep dives on the same elements. When
the reader writes it, the deep dive is kept in the catalogue under their name and its pack — a
PDF and its diagrams as draw.io files — is theirs to download.
"""

from __future__ import annotations

from typing import Any

import dash
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, dcc, html, no_update

from ea.agent.deep_dive import KINDS, Brief, DeepDiveAnalyst
from ea.models import DeepDive, Forbidden, NotFoundError
from ea.ui import ids
from ea.ui.components import alert, icon, layer_chips, mermaid_block
from ea.ui.context import AppContext, get_context
from ea.ui.pages.deep_dives import pack
from ea.views.deep_dive_layout import figures
from ea.views.mermaid import to_mermaid
from ea.views.model import view_from_dict

SEVERITY_COLOUR = {"high": "red", "medium": "orange", "low": "blue"}
CONFIDENCE_COLOUR = {"high": "green", "medium": "yellow", "low": "red"}
EXAMPLE = "What happens if the curriculum management system is replaced?"


# ------------------------------------------------------------------ the logic
def analyst(ctx: AppContext) -> DeepDiveAnalyst:
    return ctx.analyst


def brief_of(d: DeepDive) -> Brief:
    return Brief.from_dict(d.brief)


def start(ctx: AppContext, question: str) -> dict[str, Any]:
    """The brief the reader's first words start."""
    return analyst(ctx).start(question).to_dict()


def answer(
    ctx: AppContext, brief: dict[str, Any], qid: str, key: str | None, text: str = ""
) -> dict[str, Any]:
    """The brief with one answer applied; a choice it cannot take is said on the brief, not raised."""
    b = Brief.from_dict(brief)
    text = (text or "").strip()
    q = next((q for q in analyst(ctx).questions(b) if q.qid == qid), None)
    if q is None:
        b.note = "That question is no longer open."
        return b.to_dict()
    worded = next((o["key"] for o in q.options if o.get("needs") == "text"), "")
    if not key and text and worded:
        key = worded
    if not key:
        b.note = "Pick a choice first" + (", or say it in your own words." if worded else ".")
        return b.to_dict()
    if key == worded and not text:
        b.note = "Say it in your own words first, in the box under the choices."
        return b.to_dict()
    try:
        return analyst(ctx).answer(b, qid, key, text).to_dict()
    except ValueError as exc:
        b.note = str(exc)
        return b.to_dict()


def write_state(ctx: AppContext, brief: dict[str, Any] | None) -> tuple[bool, str]:
    """(disabled, why) for Write: a deep dive needs what it is about and which kind it is."""
    if not brief:
        return True, "Start the brief first."
    if not ctx.can("keep_deep_dive"):
        return True, "Your role may not keep a deep dive."
    b = Brief.from_dict(brief)
    if not (b.subject or b.work_package):
        return True, "Say what the analysis is about first."
    if b.kind not in KINDS:
        return True, "Pick the kind of analysis first."
    return False, ""


def write(ctx: AppContext, brief: dict[str, Any]) -> DeepDive:
    """The deep dive the brief asks for, analysed and kept under the reader's name."""
    d = analyst(ctx).analyse(Brief.from_dict(brief))
    return ctx.deep_dives.keep(d, ctx.actor)


# ------------------------------------------------------------------ the page
def render(ctx: AppContext) -> html.Div:
    """The deep mode's panel on the Ask page."""
    return html.Div(
        [
            dmc.Paper(
                dmc.Stack(
                    [
                        dmc.Text(
                            "A deep dive settles with you what you need to know, then reads the model from "
                            "the top down: the context and an overview drawn to be presented, the "
                            "architecture and the detail in the metamodel's notation, the maturity of what "
                            "it rests on, where the model and its documentation disagree, and the findings. "
                            "It is written as a PDF with its diagrams as draw.io files, kept in the "
                            "catalogue for others to rate and build on.",
                            size="sm",
                            c="dimmed",
                        ),
                        dmc.Textarea(
                            id=ids.ASK_DD_INPUT,
                            label="What do you need to know?",
                            placeholder=EXAMPLE,
                            autosize=True,
                            minRows=2,
                            size="md",
                        ),
                        dmc.Group(
                            [
                                dmc.Button(
                                    "Start the brief",
                                    id=ids.ASK_DD_START,
                                    leftSection=icon("tabler:list-check"),
                                ),
                                dmc.Anchor("The catalogue of deep dives", href="/deep-dives", size="sm"),
                            ],
                            gap="md",
                        ),
                    ],
                    gap="sm",
                ),
                p="md",
                withBorder=True,
                mb="md",
                className="ea-card",
            ),
            html.Div(id=ids.ASK_DD_BRIEF),
            html.Div(id=ids.ASK_DD_RESULT),
            dcc.Store(id=ids.ASK_DD_STORE, data=None),
            dcc.Store(id=ids.ASK_DD_KEPT, data=None),
        ]
    )


def _current_key(q_id: str, b: Brief) -> Any:
    if q_id == "subject":
        return f"el:{b.subject[0]}" if b.subject else (f"wp:{b.work_package}" if b.work_package else None)
    if q_id == "kind":
        return b.kind or None
    if q_id == "reach":
        return str(b.reach)
    if q_id == "layers":
        return list(b.layers) or ["all"]
    if q_id == "purpose":
        return "text" if b.purpose else ("skip" if "purpose" in b.settled else None)
    return None


def _question_card(q: Any, b: Brief):
    tag = (
        dmc.Badge("asked by the assistant", color="indigo", variant="light", size="xs")
        if q.asked_by == "assistant"
        else dmc.Badge("settled", color="green", variant="light", size="xs")
        if q.settled
        else dmc.Badge("optional", color="gray", variant="light", size="xs")
        if q.optional
        else dmc.Badge("suggested" if q.answer else "open", color="orange", variant="light", size="xs")
    )
    current = _current_key(q.qid, b)
    if q.multi:
        choice = dmc.CheckboxGroup(
            dmc.Group([dmc.Checkbox(label=o["label"], value=o["key"]) for o in q.options], gap="sm"),
            id={"type": ids.ASK_DD_Q_OPT, "qid": q.qid},
            value=current,
            **{"aria-label": q.text},
        )
    else:
        choice = dmc.RadioGroup(
            dmc.Stack([dmc.Radio(label=o["label"], value=o["key"]) for o in q.options], gap=6),
            id={"type": ids.ASK_DD_Q_OPT, "qid": q.qid},
            value=current,
            size="sm",
            **{"aria-label": q.text},
        )
    worded = any(o.get("needs") == "text" for o in q.options)
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Group([dmc.Text(q.text, size="sm", fw=600), tag], justify="space-between", wrap="nowrap"),
                dmc.Text(f"Now: {q.answer}", size="xs", c="dimmed") if q.answer else None,
                choice,
                dmc.TextInput(
                    id={"type": ids.ASK_DD_Q_TEXT, "qid": q.qid},
                    placeholder="In your own words",
                    value=b.purpose if q.qid == "purpose" else "",
                    **{"aria-label": f"{q.text} — in your own words"},
                )
                if worded
                else None,
                dmc.Group(
                    dmc.Button("Answer", id={"type": ids.ASK_DD_Q_SEND, "qid": q.qid}, size="compact-sm"),
                    justify="flex-end",
                ),
            ],
            gap=6,
        ),
        p="sm",
        withBorder=True,
        className="ea-question",
    )


def _rating(d: DeepDive) -> str:
    return f"{d.rating_average} of 5, {d.rating_count} rating(s)" if d.rating_count else "not rated yet"


def brief_panel(ctx: AppContext, brief: dict[str, Any]) -> dmc.Paper:
    """The brief as one sentence, its questions, and the earlier deep dives on the same elements."""
    a = analyst(ctx)
    b = Brief.from_dict(brief)
    disabled, why = write_state(ctx, brief)
    earlier = a.earlier(b)
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Text("The brief", fw=700, size="sm"),
                dmc.Text(a.sentence(b), size="lg", id=ids.ASK_DD_SENTENCE),
                alert(b.note, "yellow") if b.note else None,
                dmc.SimpleGrid(
                    [_question_card(q, b) for q in a.questions(b)],
                    cols={"base": 1, "md": 2},
                    spacing="sm",
                ),
                dmc.Stack(
                    [
                        dmc.Text(
                            "Earlier deep dives on the same elements, best rated first — one may already "
                            "answer it:",
                            size="sm",
                            fw=500,
                        ),
                        *[
                            dmc.Group(
                                [
                                    dmc.Anchor(d.title, href=f"/deep-dives?open={d.deep_dive_id}", size="sm"),
                                    dmc.Text(
                                        f"{KINDS.get(d.kind, {}).get('label', d.kind)} · {_rating(d)} · "
                                        f"{str(d.created_at or '')[:10]}",
                                        size="xs",
                                        c="dimmed",
                                    ),
                                ],
                                gap="sm",
                            )
                            for d in earlier
                        ],
                    ],
                    gap=4,
                )
                if earlier
                else None,
                dmc.Group(
                    [
                        dmc.Button(
                            "Write the deep dive",
                            id=ids.ASK_DD_WRITE,
                            leftSection=icon("tabler:report-analytics"),
                            disabled=disabled,
                        ),
                        dmc.Text(why, size="xs", c="dimmed", id=ids.ASK_DD_WRITE_HINT),
                    ],
                    gap="sm",
                ),
            ],
            gap="sm",
        ),
        p="md",
        withBorder=True,
        mb="md",
        className="ea-card",
    )


def result_card(ctx: AppContext, d: DeepDive) -> dmc.Paper:
    """What was written: the brief, how far it can be trusted, what matters most, and the pack."""
    c = d.content
    conf = c.get("confidence") or {}
    by_id = {f["id"]: f for f in c.get("findings") or []}
    headline = [by_id[h["id"]] for h in c.get("headline") or [] if h["id"] in by_id]
    first_view = next((f for f in figures(c) if f["kind"] == "view"), None)
    ungrounded = (c.get("trace") or {}).get("ungrounded") or []
    view = view_from_dict(first_view["view"]) if first_view else None
    return dmc.Paper(
        dmc.Stack(
            [
                dmc.Group(
                    [
                        dmc.Stack(
                            [
                                dmc.Title(d.title, order=2, size="h3"),
                                dmc.Text(
                                    f"Kept in the catalogue {str(d.created_at or '')[:16]} by {d.created_by}",
                                    size="xs",
                                    c="dimmed",
                                ),
                            ],
                            gap=2,
                        ),
                        dmc.Group(
                            [
                                dmc.Button(
                                    "Download the pack",
                                    id=ids.ASK_DD_PACK,
                                    leftSection=icon("tabler:file-zip"),
                                    variant="light",
                                ),
                                dmc.Anchor(
                                    "Open in the catalogue",
                                    href=f"/deep-dives?open={d.deep_dive_id}",
                                    size="sm",
                                ),
                            ],
                            gap="sm",
                        ),
                    ],
                    justify="space-between",
                    align="flex-start",
                ),
                dmc.Text(c.get("brief_sentence", ""), size="sm"),
                dmc.Group(
                    [
                        dmc.Badge(
                            f"confidence: {conf.get('level', '')}",
                            color=CONFIDENCE_COLOUR.get(conf.get("level"), "gray"),
                            variant="light",
                        ),
                        dmc.Text(conf.get("text", ""), size="xs", c="dimmed"),
                    ],
                    gap="sm",
                    wrap="nowrap",
                ),
                dmc.Text(c.get("summary", ""), size="sm"),
                alert(
                    "These identifiers appear in the summary but the analysis did not read them; treat them "
                    "as unverified: " + ", ".join(ungrounded),
                    "yellow",
                )
                if ungrounded
                else None,
                dmc.Text("What you need to know", fw=600, size="sm"),
                dmc.Stack(
                    [
                        dmc.Group(
                            [
                                dmc.Badge(
                                    f["severity"], color=SEVERITY_COLOUR.get(f["severity"], "gray"), size="sm"
                                ),
                                dmc.Text(f["title"], size="sm"),
                            ],
                            gap="sm",
                            wrap="nowrap",
                        )
                        for f in headline
                    ],
                    gap=4,
                )
                if headline
                else dmc.Text("The rules found nothing to report in what was read.", size="sm", c="dimmed"),
                dmc.Text(
                    f"The pack holds the PDF and {len(figures(c))} diagram(s) as draw.io files, from the "
                    "context down to the detail.",
                    size="xs",
                    c="dimmed",
                ),
                mermaid_block("dd-first-view", to_mermaid(view), legend=layer_chips(view)) if view else None,
            ],
            gap="sm",
        ),
        p="lg",
        withBorder=True,
        mb="md",
        className="ea-card ea-document",
    )


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.ASK_DD_BRIEF, "children"),
        Output(ids.ASK_DD_STORE, "data"),
        Input(ids.ASK_DD_START, "n_clicks"),
        State(ids.ASK_DD_INPUT, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.ASK_DD_START, "loading"), True, False)],
    )
    def begin(n, question):
        if not n:
            return no_update, no_update
        if not (question or "").strip():
            return alert("Say what you need to know first.", "yellow"), None
        ctx = get_context()
        brief = start(ctx, question.strip())
        return brief_panel(ctx, brief), brief

    @app.callback(
        Output(ids.ASK_DD_BRIEF, "children", allow_duplicate=True),
        Output(ids.ASK_DD_STORE, "data", allow_duplicate=True),
        Input({"type": ids.ASK_DD_Q_SEND, "qid": ALL}, "n_clicks"),
        State({"type": ids.ASK_DD_Q_OPT, "qid": ALL}, "value"),
        State({"type": ids.ASK_DD_Q_OPT, "qid": ALL}, "id"),
        State({"type": ids.ASK_DD_Q_TEXT, "qid": ALL}, "value"),
        State({"type": ids.ASK_DD_Q_TEXT, "qid": ALL}, "id"),
        State(ids.ASK_DD_STORE, "data"),
        prevent_initial_call=True,
    )
    def reply(clicks, values, value_ids, texts, text_ids, brief):
        trig = dash.ctx.triggered_id
        if not trig or not brief or not any(clicks or []):
            return no_update, no_update
        qid = trig["qid"]
        value = next((v for v, i in zip(values, value_ids, strict=False) if i["qid"] == qid), None)
        text = next((t for t, i in zip(texts, text_ids, strict=False) if i["qid"] == qid), "") or ""
        key = ",".join(value) if isinstance(value, list) else value
        ctx = get_context()
        brief = answer(ctx, brief, qid, key, text)
        return brief_panel(ctx, brief), brief

    @app.callback(
        Output(ids.ASK_DD_RESULT, "children"),
        Output(ids.ASK_DD_KEPT, "data"),
        Input(ids.ASK_DD_WRITE, "n_clicks"),
        State(ids.ASK_DD_STORE, "data"),
        prevent_initial_call=True,
        running=[(Output(ids.ASK_DD_WRITE, "loading"), True, False)],
    )
    def write_it(n, brief):
        if not n or not brief:
            return no_update, no_update
        ctx = get_context()
        disabled, why = write_state(ctx, brief)
        if disabled:
            return alert(why, "yellow"), no_update
        try:
            d = write(ctx, brief)
        except Forbidden as exc:
            return alert(str(exc), "red"), no_update
        except (ValueError, NotFoundError) as exc:
            return alert(str(exc), "yellow"), no_update
        return result_card(ctx, d), d.deep_dive_id

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.ASK_DD_PACK, "n_clicks"),
        State(ids.ASK_DD_KEPT, "data"),
        prevent_initial_call=True,
    )
    def download_pack(n, deep_dive_id):
        if not n or not deep_dive_id:
            return no_update
        name, data = pack(get_context(), deep_dive_id)
        return dcc.send_bytes(data, name)
