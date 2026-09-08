"""Ask: a question to the agent, answered as a document that leads with a generated architecture view."""

from __future__ import annotations

import json

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update

from ea.agent.document import AnswerDocument, compose, slug
from ea.ui import ids
from ea.ui.components import (
    alert,
    element_anchor,
    icon,
    markdown,
    mermaid_block,
    page_title,
    status_badge,
    type_badge,
    view_toolbar,
)
from ea.ui.context import AppContext, get_context
from ea.views.drawio import to_drawio
from ea.views.mermaid import to_mermaid
from ea.views.model import view_from_dict, view_to_dict

EXAMPLES = [
    "What is the impact of changing SRS_Course_Offering?",
    "Who owns the Course Catalogue and which applications contribute to it?",
    "Which data entities contain PII and where are they stored?",
    "List the information assets categorised by the Curriculum topic.",
]


def render(ctx: AppContext) -> html.Div:
    provider = ctx.agent.provider
    badge = dmc.Badge(
        f"provider: {provider.name}"
        + (f" · {getattr(provider, 'model', '')}" if getattr(provider, "model", "") else ""),
        variant="light",
        color="indigo" if provider.name == "anthropic" else "gray",
        id=ids.ASK_PROVIDER,
    )
    return html.Div(
        [
            page_title(
                "Ask the model",
                "A question becomes a document: a generated architecture view first, then the answer, the elements it names and how it was answered. Every identifier comes from a tool result; every diagram is drawn from the model.",
                badge,
            ),
            dmc.Paper(
                dmc.Stack(
                    [
                        dmc.Textarea(
                            id=ids.ASK_INPUT,
                            **{"aria-label": "Your question"},
                            placeholder="Ask about elements, ownership, dependencies, impact…",
                            autosize=True,
                            minRows=2,
                            value=EXAMPLES[0],
                            size="md",
                        ),
                        dmc.Group(
                            [
                                dmc.Button("Ask", id=ids.ASK_BUTTON, leftSection=icon("tabler:send")),
                                dmc.Button(
                                    "Reset conversation", id=ids.ASK_RESET, variant="subtle", color="gray"
                                ),
                            ],
                            gap="sm",
                        ),
                        dmc.Group(
                            [dmc.Text("Try:", size="xs", c="dimmed")]
                            + [
                                # The badge is the chip a reader sees; the wrapper is what
                                # reports the click, because a badge reports none. It
                                # generates no box, so the row is unchanged.
                                html.Div(
                                    dmc.Badge(
                                        q,
                                        variant="outline",
                                        color="gray",
                                        size="sm",
                                        className="ea-chip",
                                    ),
                                    id={"type": "ask-example", "i": i},
                                    n_clicks=0,
                                    style={"display": "contents"},
                                )
                                for i, q in enumerate(EXAMPLES)
                            ],
                            gap="xs",
                        ),
                    ],
                    gap="sm",
                ),
                p="md",
                withBorder=True,
                mb="md",
                className="ea-card",
            ),
            html.Div(id=ids.ASK_ANSWER),
            html.Div(id=ids.ASK_TRACE),
            dcc.Store(id=ids.ASK_HISTORY, data=[]),
            dcc.Store(id=ids.ASK_DOC_STORE, data=None),
        ]
    )


def _section(title: str, body, subtitle: str | None = None):
    return html.Div(
        [
            dmc.Title(title, order=2, className="ea-section-title"),
            dmc.Text(subtitle, size="xs", c="dimmed", mb=6) if subtitle else None,
            body,
        ],
        className="ea-section",
    )


def _elements_table(ctx: AppContext, doc: AnswerDocument):
    head = dmc.TableThead(dmc.TableTr([dmc.TableTh(h) for h in ("ID", "Element", "Type", "Status")]))
    rows = []
    for e in doc.elements:
        node = ctx.graph.node(e["id"])
        rows.append(
            dmc.TableTr(
                [
                    dmc.TableTd(dmc.Code(e["id"])),
                    dmc.TableTd(element_anchor(node)),
                    dmc.TableTd(type_badge(ctx.registry, node["type_id"], "xs")),
                    dmc.TableTd(status_badge(e.get("status", ""))),
                ]
            )
        )
    return dmc.TableScrollContainer(
        dmc.Table(
            [head, dmc.TableTbody(rows)],
            striped=True,
            highlightOnHover=True,
            withTableBorder=False,
            verticalSpacing="xs",
            className="ea-table",
        ),
        minWidth=560,
    )


def _timeline(doc: AnswerDocument):
    items = []
    for c in doc.tool_calls:
        args = ", ".join(f"{k}={v!r}" for k, v in c.input.items())
        items.append(
            dmc.TimelineItem(
                title=dmc.Code(c.name),
                children=dmc.Text(args[:220], size="xs", c="dimmed", style={"fontFamily": "monospace"}),
                bullet=icon("tabler:tool", 12),
            )
        )
    if not items:
        return dmc.Text("No tools were called.", c="dimmed", size="sm")
    return dmc.Timeline(items, active=len(items), bulletSize=20, lineWidth=2, color="indigo")


def document_card(ctx: AppContext, doc: AnswerDocument) -> dmc.Paper:
    md = doc.markdown()
    who = doc.provider + (f" · {doc.model}" if doc.model else "")
    views = []
    for i, v in enumerate(doc.views):
        views.append(
            _section(
                v.title,
                mermaid_block(f"ask-view-{i}", to_mermaid(v)),
                v.note
                or (
                    "Generated from the model: layers top to bottom, every shape an element you can open."
                    if i == 0
                    else None
                ),
            )
        )
    children = [
        dmc.Group(
            [
                dmc.Stack(
                    [
                        dmc.Title(doc.title, order=2, size="h2"),
                        dmc.Text(f"Answered {doc.created_at} · {who}", size="xs", c="dimmed"),
                    ],
                    gap=2,
                ),
                view_toolbar(
                    ids.ASK_DOC_MD,
                    ids.ASK_DOC_DRAWIO,
                    copy_content=md,
                    drawio_reason=(
                        "" if doc.views else "This answer drew no diagram, so there is nothing to export."
                    ),
                ),
            ],
            justify="space-between",
            align="flex-start",
            mb="sm",
        ),
        *views,
        _section("Answer", markdown(doc.answer, "ask-answer-md")),
        alert(
            "These identifiers appear in the answer but no tool returned them; treat them as unverified: "
            + ", ".join(doc.ungrounded_ids),
            "yellow",
        )
        if doc.ungrounded_ids
        else None,
        _section("Elements in this answer", _elements_table(ctx, doc)) if doc.elements else None,
        _section("How this was answered", _timeline(doc)),
    ]
    return dmc.Paper(children, p="lg", withBorder=True, mb="md", className="ea-card ea-document")


def register(app: dash.Dash) -> None:
    @app.callback(
        Output(ids.ASK_ANSWER, "children"),
        Output(ids.ASK_TRACE, "children"),
        Output(ids.ASK_DOC_STORE, "data"),
        Input(ids.ASK_BUTTON, "n_clicks"),
        State(ids.ASK_INPUT, "value"),
        prevent_initial_call=True,
        running=[(Output(ids.ASK_BUTTON, "loading"), True, False)],
    )
    def ask(n, question):
        if not n or not (question or "").strip():
            return no_update, no_update, no_update
        ctx = get_context()
        res = ctx.agent.ask(question.strip())
        if res.error:
            return alert(res.error, "red"), None, None
        doc = compose(question.strip(), res, ctx.agent.toolbox)
        stored = {
            "name": slug(doc.title),
            "md": doc.markdown(),
            "view": view_to_dict(doc.views[0]) if doc.views else None,
        }
        items = []
        for i, c in enumerate(res.tool_calls):
            items.append(
                dmc.AccordionItem(
                    [
                        dmc.AccordionControl(
                            dmc.Group(
                                [
                                    dmc.Code(c.name),
                                    dmc.Text(
                                        json.dumps(c.input, ensure_ascii=False)[:120], size="xs", c="dimmed"
                                    ),
                                ],
                                gap="sm",
                            )
                        ),
                        dmc.AccordionPanel(
                            dmc.Code(
                                c.result_preview, block=True, style={"whiteSpace": "pre-wrap", "fontSize": 11}
                            )
                        ),
                    ],
                    value=f"call-{i}",
                )
            )
        trace = dmc.Paper(
            [
                dmc.Title(
                    f"Tool trace · {len(items)} calls · provider {res.provider}",
                    order=2,
                    className="ea-section-title",
                ),
                dmc.Accordion(items, variant="separated")
                if items
                else dmc.Text("No tools were called.", c="dimmed", size="sm"),
            ],
            p="md",
            withBorder=True,
            className="ea-card",
        )
        return document_card(ctx, doc), trace, stored

    @app.callback(
        Output(ids.DOWNLOAD, "data", allow_duplicate=True),
        Input(ids.ASK_DOC_MD, "n_clicks"),
        Input(ids.ASK_DOC_DRAWIO, "n_clicks"),
        State(ids.ASK_DOC_STORE, "data"),
        State({"type": ids.MERMAID_POS, "id": "ask-view-0"}, "data"),
        prevent_initial_call=True,
    )
    def download_doc(n_md, n_drawio, stored, positions):
        if not stored or not (n_md or n_drawio):
            return no_update
        if dash.ctx.triggered_id == ids.ASK_DOC_DRAWIO:
            if not stored.get("view"):
                return no_update
            view = view_from_dict(stored["view"])
            return dcc.send_string(
                to_drawio(view, get_context().base_url(), positions or None), f"{stored['name']}.drawio"
            )
        return dcc.send_string(stored["md"], f"{stored['name']}.md")

    @app.callback(
        Output(ids.ASK_ANSWER, "children", allow_duplicate=True),
        Output(ids.ASK_TRACE, "children", allow_duplicate=True),
        Input(ids.ASK_RESET, "n_clicks"),
        prevent_initial_call=True,
    )
    def reset(n):
        if n:
            get_context().agent.reset()
        return None, None

    @app.callback(
        Output(ids.ASK_INPUT, "value"),
        Input({"type": "ask-example", "i": dash.ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def example(clicks):
        trig = dash.ctx.triggered_id
        if not trig or not any(clicks):
            return no_update
        return EXAMPLES[trig["i"]]
