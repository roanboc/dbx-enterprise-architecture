"""Command line: initialise, load packs, import CSVs, ask graph questions, work on branches."""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from ea.backend.branching import MAIN, set_branch
from ea.config import Settings
from ea.models import ConflictError, Forbidden, NotFoundError, ValidationError
from ea.services.roles import set_role

app = typer.Typer(
    help="EA repository — a generic, metamodel-driven enterprise architecture repository.",
    no_args_is_help=True,
)
branch_app = typer.Typer(
    help="Branches of the model: create, diff, merge item by item, abandon.", no_args_is_help=True
)
app.add_typer(branch_app, name="branch")


@app.callback()
def main(
    branch: str = typer.Option(
        None,
        "--branch",
        "-b",
        envvar="EA_BRANCH",
        help="Work on this branch instead of main (every read and write of the command honours it).",
    ),
    role: str = typer.Option(
        None,
        "--as",
        envvar="EA_ROLE",
        help="Run as this role: reader, reviewer, architect, admin (default) or agent.",
    ),
):
    set_branch(branch or MAIN)
    set_role(role)
    _require_branch_exists(branch)


def _require_branch_exists(branch: str | None) -> None:
    """A branch named on the command line has to be one that exists.

    Writing to a branch nobody created used to be accepted: the rows went to an overlay no
    `branch list` mentions and no `branch diff` can read, and reappeared if somebody later
    created a branch with that name.
    """
    if not branch or branch == MAIN:
        return
    from ea.backend import backend_from_settings

    backend = backend_from_settings(Settings.from_env())
    try:
        if backend.get_branch(branch) is None:
            _refuse(
                f"no branch with id {branch!r}; `ea branch list` says which there are, "
                f"and `ea branch create` makes one"
            )
    finally:
        backend.close()


def _refuse(message: str) -> None:
    """Say what is wrong and stop, the way a failed import stops: a message and exit 1."""
    typer.echo(message, err=True)
    raise typer.Exit(1)


def _ctx(settings: Settings | None = None):
    from ea.backend import backend_from_settings
    from ea.metamodel import Registry, load_pack
    from ea.services import GraphService, RepositoryService

    settings = settings or Settings.from_env()
    backend = backend_from_settings(settings)
    packs = backend.list_packs()
    if packs:
        pack = backend.load_pack(packs[0]["pack_id"])
    else:
        pack = load_pack(settings.pack_path)
        backend.save_pack(pack)
    registry = Registry(pack)
    return settings, backend, registry, RepositoryService(backend, registry), GraphService(backend, registry)


def _branches():
    from ea.services import BranchService

    _, backend, registry, *_ = _ctx()
    return backend, registry, BranchService(backend, registry)


@app.command()
def init(
    pack: Path = typer.Option(None, help="metamodel pack to load (default: EA_PACK)"),
    db: Path = typer.Option(None, help="DuckDB file (default: EA_DB_PATH)"),
):
    """Create the database and load a metamodel pack."""
    from ea.metamodel import load_pack

    settings = Settings.from_env()
    if db:
        settings.db_path = str(db)
    if pack:
        settings.pack_path = str(pack)
    _, backend, registry, *_ = _ctx(settings)
    p = load_pack(settings.pack_path)
    backend.save_pack(p)
    typer.echo(
        f"database {settings.db_path}: pack '{p.id}' loaded ({len(p.element_types)} element types, {len(p.relationship_types)} relationship types)"
    )


@app.command("load-pack")
def load_pack_cmd(path: Path):
    """(Re)load a metamodel pack from YAML."""
    from ea.metamodel import load_pack

    _, backend, *_ = _ctx()
    p = load_pack(path)
    backend.save_pack(p)
    typer.echo(f"pack '{p.id}' version {p.version} loaded")


@app.command("export-pack")
def export_pack(out: Path, pack_id: str = typer.Option(None, help="pack id (default: the loaded pack)")):
    """Write the stored metamodel back to YAML."""
    from ea.metamodel import dump_pack

    _, backend, registry, *_ = _ctx()
    p = backend.load_pack(pack_id) if pack_id else registry.pack
    if p is None:
        # Refused before the destination is opened: a pack that cannot be found must not
        # cost the reader the file they were writing over.
        held = ", ".join(sorted(x["pack_id"] for x in backend.list_packs())) or "none"
        _refuse(f"no pack with id {pack_id!r} in this database; it holds: {held}")
    dump_pack(p, out)
    typer.echo(f"pack '{p.id}' written to {out}")


def _readable_directory(directory: Path) -> None:
    """A directory that cannot be read is refused with the reason, not with a stack trace.

    It exits the way an import that found errors exits, because that is what this is.
    """
    reason = ""
    if not directory.exists():
        reason = "does not exist"
    elif not directory.is_dir():
        reason = "is a file, not a directory of CSV files"
    elif not os.access(directory, os.R_OK):
        reason = "cannot be read: check its permissions"
    if reason:
        typer.echo(f"{directory} {reason}", err=True)
        raise typer.Exit(1)


@app.command("import")
def import_cmd(
    directory: Path,
    source: str = typer.Option("", help="source system name recorded on every row"),
    mapping: Path = typer.Option(None, help="mapping YAML for the source's files and columns"),
    dry_run: bool = typer.Option(False, help="validate and report, load nothing"),
    actor: str = typer.Option("import"),
):
    """Import elements, relationships and links from CSV files (validated against the metamodel)."""
    from ea.importer import import_directory, load_mapping

    _readable_directory(directory)
    _, backend, registry, *_ = _ctx()
    m = load_mapping(mapping) if mapping else None
    report = import_directory(backend, registry, directory, source, m, actor, dry_run)
    typer.echo(report.summary())
    for iss in report.issues:
        typer.echo("  " + str(iss))
    raise typer.Exit(code=0 if report.ok else 1)


@app.command()
def validate(directory: Path, source: str = typer.Option(""), mapping: Path = typer.Option(None)):
    """Validate CSV files against the metamodel without loading."""
    import_cmd(directory, source, mapping, True)


@app.command()
def stats():
    """Element and relationship counts per type."""
    _, _, registry, repo, _ = _ctx()
    s = repo.stats()
    typer.echo(f"{s['elements']} elements, {s['relationships']} relationships")
    for row in s["by_type"]:
        if row["count"]:
            typer.echo(f"  {row['count']:6d}  {row['name']}")
    if s["unknown_types"]:
        typer.echo(f"  unknown types in store: {s['unknown_types']}")


@app.command()
def find(text: str, type_id: str = typer.Option(None, "--type"), limit: int = 50):
    """Search elements: every word must match in the name, key, id, description or attributes; ranked."""
    from ea.services import SearchService

    _, backend, registry, *_ = _ctx()
    t = registry.resolve_type(type_id) if type_id else None
    if type_id and t is None:
        # Ignoring it would answer the unrestricted search and look like a narrow one.
        _refuse(f"no element type {type_id!r} in this metamodel; `ea summary` lists them")
    for h in SearchService(backend, registry).search(text, t.id if t else None, limit=limit):
        e = h.element
        where = f"  [{h.matched_in}: {h.snippet[:60]}]" if h.matched_in and h.matched_in != "name" else ""
        typer.echo(f"{e.element_id:24s} {e.type_id:32s} {e.name}{where}")


@app.command("set")
def set_cmd(
    element_ids: list[str],
    status: str = typer.Option(None, help="draft, approved or retired"),
    lifecycle: str = typer.Option(None, help="lifecycle text"),
    current_state: str = typer.Option(None, "--current-state"),
    target_state: str = typer.Option(None, "--target-state"),
    work_package: str = typer.Option(None, "--work-package", "-w"),
    note: str = typer.Option(None, "--note"),
    attr: str = typer.Option(None, help="one attribute as name=value"),
    actor: str = typer.Option("cli"),
):
    """The same change on many elements at once (bulk edit), on the current branch."""
    _, _, _, repo, _ = _ctx()
    fields = {
        "status": status,
        "lifecycle_status": lifecycle,
        "current_state": current_state,
        "target_state": target_state,
        "target_work_package": work_package,
        "target_note": note,
    }
    attribute = None
    if attr:
        name, _, value = attr.partition("=")
        attribute = (name.strip(), value)
    out = repo.bulk_update(element_ids, actor, fields, attribute)
    typer.echo(f"updated {len(out['updated'])}, refused {len(out['refused'])}")
    for r in out["refused"]:
        typer.echo(f"  {r['element_id']}: {r['reason']}")


@app.command()
def health(fmt: str = typer.Option("table", help="table or md")):
    """Freshness per source system and completeness per element type."""
    from ea.services import HealthService

    _, backend, registry, *_ = _ctx()
    svc = HealthService(backend, registry)
    fresh, comp = svc.freshness(), svc.completeness()
    sep = "| " if fmt == "md" else ""
    typer.echo(f"Freshness (as of {fresh['as_of']})")
    if fmt == "md":
        typer.echo(
            "| source | elements | relationships | last updated | stale 30 d | stale 90 d | stale 180 d | never updated |"
        )
        typer.echo("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in fresh["sources"]:
        typer.echo(
            f"{sep}{r['source']:20s} {sep}{r['elements']:6d} {sep}{r['relationships']:6d} {sep}{r['last_updated']:16s} "
            f"{sep}{r['stale_30']:5d} {sep}{r['stale_90']:5d} {sep}{r['stale_180']:5d} {sep}{r['never_updated']:5d}{' |' if fmt == 'md' else ''}"
        )
    typer.echo("")
    typer.echo(f"Completeness ({comp['elements']} elements)")
    if fmt == "md":
        typer.echo("| type | elements | description | links | relationships | attributes | target decided |")
        typer.echo("| --- | --- | --- | --- | --- | --- | --- |")
    for r in comp["types"]:
        typer.echo(
            f"{sep}{r['type'][:32]:32s} {sep}{r['elements']:5d} {sep}{r['description_pct']:3d}% {sep}{r['links_pct']:3d}% "
            f"{sep}{r['relationships_pct']:3d}% {sep}{r['attributes_pct']:3d}% {sep}{r['target_pct']:3d}%{' |' if fmt == 'md' else ''}"
        )


@app.command()
def get(element_id: str):
    """Show an element with its relationships."""
    _, _, _, repo, _ = _ctx()
    d = repo.element_detail(element_id)
    e = d["element"]
    typer.echo(
        f"{e.element_id} [{d['type'].name if d['type'] else e.type_id}] {e.name}  status={e.status} version={e.version}"
    )
    if e.description_md:
        typer.echo(e.description_md)
    if e.attrs:
        typer.echo("attributes: " + json.dumps(e.attrs, ensure_ascii=False))
    for ln in d["links"]:
        typer.echo(f"link: {ln.url} {ln.label}")
    for r in d["outgoing"]:
        o = r["other"]
        typer.echo(
            f"  -> {r['label']}{' (' + r['relationship'].qualifier + ')' if r['relationship'].qualifier else ''}: {o.element_id if o else r['relationship'].dst_id} {o.name if o else ''}"
        )
    for r in d["incoming"]:
        o = r["other"]
        typer.echo(
            f"  <- {r['label']}{' (' + r['relationship'].qualifier + ')' if r['relationship'].qualifier else ''}: {o.element_id if o else r['relationship'].src_id} {o.name if o else ''}"
        )


@app.command()
def neighbours(element_id: str, depth: int = 1, direction: str = "both"):
    """Elements within N hops."""
    _, _, _, _, graph = _ctx()
    sub = graph.neighbours(element_id, depth, direction)
    for n in sub["nodes"]:
        typer.echo(f"{n['depth']}  {n['element_id']:24s} {n['type_name']:32s} {n['name']}")


@app.command()
def trace(
    element_id: str,
    direction: str = typer.Option("out", help="out (what this depends on) or in (what depends on this)"),
    depth: int = 5,
):
    """Transitive reach along relationship direction."""
    if direction not in ("in", "out"):
        _refuse(f"--direction is 'in' or 'out', not {direction!r}")
    _, _, _, _, graph = _ctx()
    for r in graph.trace(element_id, direction, depth):
        typer.echo(
            f"{r['depth']}  {r['element_id']:24s} {r['type_name']:32s} {r['name']}   via {' > '.join(r['rel_labels'])}"
        )


@app.command()
def impact(element_id: str, depth: int = 3):
    """Blast radius: upstream dependants and downstream dependencies, with a completeness footer."""
    _, _, _, _, graph = _ctx()
    res = graph.impact(element_id, depth)
    e = res["element"]
    typer.echo(f"Impact of {e['element_id']} [{e['type_name']}] {e['name']}")
    typer.echo(f"  depends on this (upstream, {len(res['upstream'])}):")
    for r in res["upstream"]:
        typer.echo(f"    {r['depth']}  {r['element_id']:24s} {r['type_name']:32s} {r['name']}")
    typer.echo(f"  this depends on (downstream, {len(res['downstream'])}):")
    for r in res["downstream"]:
        typer.echo(f"    {r['depth']}  {r['element_id']:24s} {r['type_name']:32s} {r['name']}")
    c = res["completeness"]
    typer.echo(
        f"  completeness: {c['populated']}/{c['declared']} relationship types for this element type have any instances"
    )
    for name in c["empty"]:
        typer.echo(f"    no instances: {name}")


@app.command()
def view(
    element_id: str,
    depth: int = 1,
    impact: bool = False,
    fmt: str = "mermaid",
    out: str = "",
):
    """An architecture view of an element as Mermaid (default), Markdown or a draw.io file (--fmt md|drawio)."""
    from ea.views import view_from_impact, view_from_neighbourhood
    from ea.views.drawio import to_drawio
    from ea.views.mermaid import to_markdown, to_mermaid

    _, _, registry, _, graph = _ctx()
    if impact:
        v = view_from_impact(registry, graph, graph.impact(element_id, max(depth, 1) if depth != 1 else 3))
    else:
        v = view_from_neighbourhood(registry, graph, element_id, depth)
    text = {"mermaid": to_mermaid, "md": to_markdown, "drawio": to_drawio}.get(fmt, to_mermaid)(v)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        typer.echo(f"{out}: {len(v.nodes)} elements, {len(v.edges)} relationships")
    else:
        typer.echo(text)


@app.command()
def target(
    work_package: str = typer.Option(
        None, "--work-package", "-w", help="a work package element id; default: all"
    ),
    fmt: str = typer.Option("table", help="table or md (a Markdown section with the marked view)"),
):
    """Current state against target state, per work package: counts, the artefacts, and a marked view."""
    from ea.services import TargetStateService
    from ea.services.target import CURRENT_STYLE, TARGET_STYLE, state_label
    from ea.views import view_from_ids
    from ea.views.mermaid import to_markdown

    _, backend, registry, _, graph = _ctx()
    svc = TargetStateService(backend, registry)
    if work_package and backend.get_element(work_package) is None:
        # Falling back to the whole model reports every element as though it belonged to a
        # work package that does not exist.
        held = ", ".join(w.element_id for w in svc.work_packages()) or "none"
        _refuse(f"no element with id {work_package!r}; the work packages are: {held}")
    summary = svc.summary(work_package)
    if fmt == "md":
        title = "Target state"
        if work_package:
            wp = backend.get_element(work_package)
            title = f"Target state of {wp.name if wp else work_package}"
        view = view_from_ids(
            registry, graph, svc.scope_ids(work_package), title, [work_package] if work_package else []
        )
        typer.echo(to_markdown(view, marked=True))
        return
    typer.echo(
        f"{summary['elements']} elements, {summary['relationships']} relationships"
        + (f" under {work_package}" if work_package else "")
        + f"; {summary['changes']} elements change"
    )
    typer.echo("  by target state: " + ", ".join(f"{k} {v}" for k, v in summary["by_target"].items() if v))
    for e in svc.elements(work_package, only_changes=not work_package):
        typer.echo(
            f"  {e.element_id:26s} {e.name[:38]:38s} {state_label(e.current_state, CURRENT_STYLE):18s} -> "
            f"{state_label(e.target_state, TARGET_STYLE):13s} {e.target_note[:50]}"
        )


@branch_app.command("list")
def branch_list(status: str = typer.Option(None, help="open, merged or abandoned")):
    """The branches of the model and how many rows each carries."""
    _, _, svc = _branches()
    rows = svc.list(status)
    if not rows:
        typer.echo("no branches")
    for b in rows:
        typer.echo(
            f"{b.branch_id:32s} {b.status:10s} {b.changes:5d} rows  {b.work_package or '-':20s} {b.created_by} {str(b.created_at)[:16]}  {b.name}"
        )


@branch_app.command("create")
def branch_create(
    name: str,
    description: str = typer.Option("", help="what the branch is for"),
    work_package: str = typer.Option(
        "", "--work-package", "-w", help="the work package element id it belongs to"
    ),
    actor: str = typer.Option("cli"),
):
    """Create a branch from main (its id is derived from the name)."""
    _, _, svc = _branches()
    b = svc.create(name, actor, description, work_package)
    typer.echo(f"branch '{b.branch_id}' created; use --branch {b.branch_id} on other commands to work on it")


@branch_app.command("diff")
def branch_diff(branch_id: str):
    """The branch's change set against main: what was added, changed, deleted, and what conflicts."""
    _, _, svc = _branches()
    cs = svc.diff(branch_id)
    c = cs.counts()
    typer.echo(
        f"branch '{branch_id}' ({cs.branch.status}): {c['added']} added, {c['changed']} changed, {c['deleted']} deleted, {c['conflicts']} conflicts"
    )
    for row in svc.item_rows(cs):
        flag = "  CONFLICT" if row["conflict"] else ""
        fields = f"  [{row['fields']}]" if row["fields"] else ""
        typer.echo(
            f"  {row['change']:8s} {row['kind']:12s} {row['entity_id']:28s} {row['label']}{fields}{flag}"
        )


@branch_app.command("merge")
def branch_merge(
    branch_id: str,
    include: list[str] = typer.Option(
        None, "--include", "-i", help="item key(s) to merge (element:<id> or relationship:<id>); default: all"
    ),
    resolve: list[str] = typer.Option(
        None, "--resolve", "-r", help="conflict resolution as key=branch or key=main"
    ),
    actor: str = typer.Option("cli"),
):
    """Merge the branch into main, item by item; unresolved conflicts and unticked items remain on the branch."""
    _, _, svc = _branches()
    resolutions = {}
    for r in resolve or []:
        k, _, v = r.partition("=")
        resolutions[k] = v
    res = svc.merge(branch_id, actor, set(include) if include else None, resolutions)
    typer.echo(
        f"merged {len(res.applied)} item(s), dropped {len(res.dropped)}, {res.remaining} remaining; branch {'closed' if res.closed else 'still open'}"
    )


@branch_app.command("review")
def branch_review(branch_id: str, actor: str = typer.Option("cli")):
    """Request a review: the branch freezes and the reviewers of every type it touches are named."""
    from ea.services import ReviewService

    backend, registry, svc = _branches()
    reviews = ReviewService(backend, registry, svc)
    reviews.request(branch_id, actor)
    for r in reviews.requirements(branch_id):
        who = ", ".join(r["reviewers"]) if r["reviewers"] else "any reviewer"
        typer.echo(f"  {r['type']:36s} reviewers: {who}")
    typer.echo(f"branch '{branch_id}' is in review")


@branch_app.command("approve")
def branch_approve(
    branch_id: str,
    types: str = typer.Option(
        None, help="comma-separated type ids to approve (default: every type you cover)"
    ),
    comment: str = typer.Option(""),
    actor: str = typer.Option("cli"),
    groups: str = typer.Option("", help="comma-separated groups the actor belongs to"),
):
    """Approve the branch for the types you review; it is approved once every touched type is."""
    from ea.services import ReviewService

    backend, registry, svc = _branches()
    out = ReviewService(backend, registry, svc).approve(
        branch_id, actor, types.split(",") if types else None, comment, [g for g in groups.split(",") if g]
    )
    typer.echo(f"approved {', '.join(out['approved_types'])}; pending {', '.join(out['pending']) or 'none'}")
    if out["complete"]:
        typer.echo(f"branch '{branch_id}' is approved")


@branch_app.command("send-back")
def branch_send_back(
    branch_id: str,
    comment: str = typer.Option(..., help="what must change"),
    actor: str = typer.Option("cli"),
):
    """Send the branch back to its author with a comment; it reopens for editing."""
    from ea.services import ReviewService

    backend, registry, svc = _branches()
    ReviewService(backend, registry, svc).send_back(branch_id, actor, comment)
    typer.echo(f"branch '{branch_id}' sent back")


@branch_app.command("abandon")
def branch_abandon(branch_id: str, actor: str = typer.Option("cli")):
    """Close the branch and discard its rows; main is untouched."""
    _, _, svc = _branches()
    svc.abandon(branch_id, actor)
    typer.echo(f"branch '{branch_id}' abandoned")


reviewers_app = typer.Typer(help="Who reviews which element type.", no_args_is_help=True)
app.add_typer(reviewers_app, name="reviewers")


@reviewers_app.command("list")
def reviewers_list():
    """The reviewer assignments per element type."""
    from ea.services import ReviewService

    backend, registry, svc = _branches()
    rows = ReviewService(backend, registry, svc).assignments()
    if not rows:
        typer.echo("no reviewers assigned: any reviewer may approve any type")
    for type_id, who in rows.items():
        typer.echo(f"{type_id:36s} {', '.join(who)}")


@reviewers_app.command("set")
def reviewers_set(type_id: str, reviewers: str, actor: str = typer.Option("cli")):
    """Assign reviewers (comma-separated users or groups) to an element type; an empty string clears it."""
    from ea.services import ReviewService

    backend, registry, svc = _branches()
    t = registry.resolve_type(type_id)
    ReviewService(backend, registry, svc).set_assignment(t.id if t else type_id, reviewers.split(","), actor)
    typer.echo(f"reviewers of {t.id if t else type_id}: {reviewers or '(any reviewer)'}")


@app.command()
def sql(query: str, limit: int = 100):
    """Read-only SQL over the repository tables."""
    _, backend, *_ = _ctx()
    frame = backend.query(query, limit=limit)
    if frame.empty:
        typer.echo(f"no rows ({len(frame.columns)} column(s): {', '.join(map(str, frame.columns))})")
        return
    typer.echo(frame.to_string(index=False))


@app.command()
def summary(types: str = typer.Option(None, help="comma-separated type ids to restrict the summary")):
    """The metamodel as Markdown (what the agent is told)."""
    _, _, registry, *_ = _ctx()
    typer.echo(registry.summary_markdown(types.split(",") if types else None))


def run() -> None:
    """The entry point.

    What the repository refuses is something a person did — an identifier nothing matches,
    a branch nobody created, a role that may not — and it reaches them as a sentence and a
    failed exit, not as a class name and a stack trace. Everything else still raises.
    """
    try:
        app()
    except (NotFoundError, ValidationError, Forbidden, ConflictError, ValueError) as exc:
        message = "; ".join(str(i) for i in exc.issues) if isinstance(exc, ValidationError) else str(exc)
        typer.echo(message, err=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    run()
