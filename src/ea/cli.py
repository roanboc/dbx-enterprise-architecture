"""Command line: initialise, load packs, import CSVs, ask graph questions, work on branches, organisations and metamodel versions."""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from ea import capacity
from ea.backend.branching import MAIN, set_branch
from ea.config import Settings
from ea.models import BRANCH_STATUSES, ConflictError, Forbidden, NotFoundError, ValidationError
from ea.services.roles import require, set_role

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
    org: str = typer.Option(
        None,
        "--org",
        "-o",
        envvar="EA_ORG",
        help="Work in this organisation instead of the default one (every read and write honours it).",
    ),
):
    set_role(role)
    _scope["org"] = org or ""
    set_branch(branch or MAIN)
    _require_branch_exists(branch)


# The organisation named on the command line, resolved once a store is open (the default one
# is a row of the store, so it cannot be known before).
_scope: dict[str, str] = {"org": ""}


def _enter_org(backend) -> str:
    """Set the organisation the command works in: the one named, else the default; refused when unknown."""
    from ea.backend.organisations import set_org
    from ea.metamodel import load_pack
    from ea.services import OrganisationService

    orgs = OrganisationService(backend)
    if orgs.default() is None:
        orgs.ensure_default(load_pack(Settings.from_env().pack_path))
    wanted = _scope.get("org") or ""
    if wanted:
        if backend.get_organisation(wanted) is None:
            held = ", ".join(o.org_id for o in orgs.list()) or "none"
            _refuse(f"no organisation with id {wanted!r}; the store holds: {held}")
        set_org(wanted)
        return wanted
    default = orgs.default()
    assert default is not None
    set_org(default.org_id)
    return default.org_id


def _require_branch_exists(branch: str | None) -> None:
    """A branch named on the command line has to be one that exists, in the organisation the
    command works in.

    Writing to a branch nobody created used to be accepted: the rows went to an overlay no
    `branch list` mentions and no `branch diff` can read, and reappeared if somebody later
    created a branch with that name.
    """
    if not branch or branch == MAIN:
        return
    from ea.backend import backend_from_settings

    backend = backend_from_settings(Settings.from_env())
    try:
        _enter_org(backend)
        if backend.get_branch(branch) is None:
            _refuse(
                f"no branch with id {branch!r}; `ea branch list` says which there are, "
                f"and `ea branch create` makes one"
            )
    finally:
        backend.close()


def _one_of(value: str, allowed: tuple[str, ...], flag: str = "--fmt") -> str:
    """A value the command does not offer is refused: silently answering in the default
    format hands back a file the reader did not ask for and never says so."""
    if value not in allowed:
        names = (
            f"{', '.join(repr(a) for a in allowed[:-1])} or {allowed[-1]!r}"
            if len(allowed) > 1
            else repr(allowed[0])
        )
        _refuse(f"{flag} is {names}, not {value!r}")
    return value


def _refuse(message: str) -> None:
    """Say what is wrong and stop, the way a failed import stops: a message and exit 1."""
    typer.echo(message, err=True)
    raise typer.Exit(1)


def _ctx(settings: Settings | None = None):
    from ea.backend import backend_from_settings
    from ea.metamodel import Registry
    from ea.services import GraphService, OrganisationService, RepositoryService

    settings = settings or Settings.from_env()
    backend = backend_from_settings(settings)
    org = _enter_org(backend)
    registry = Registry(OrganisationService(backend).applied_pack(org))
    return settings, backend, registry, RepositoryService(backend, registry), GraphService(backend, registry)


def _branches():
    from ea.services import BranchService

    _, backend, registry, *_ = _ctx()
    return backend, registry, BranchService(backend, registry)


@app.command()
def init(
    pack: Path = typer.Option(None, help="metamodel pack to load (default: EA_PACK)"),
    db: Path = typer.Option(None, help="DuckDB file (default: EA_DB_PATH)"),
    org_name: str = typer.Option(
        "", "--org-name", help="what to call the default organisation, when the store is new"
    ),
):
    """Create the database, load a metamodel pack and give the default organisation the version it applies."""
    from ea.metamodel import load_pack
    from ea.services import OrganisationService

    require("edit_metamodel", what="load a metamodel pack")
    settings = Settings.from_env()
    if db:
        settings.db_path = str(db)
    if pack:
        settings.pack_path = str(pack)
    fresh = not Path(settings.db_path).exists()
    backend = None
    try:
        _, backend, registry, *_ = _ctx(settings)
        p = load_pack(settings.pack_path)
        backend.save_pack(p, "cli")
        orgs = OrganisationService(backend)
        default = orgs.default()
        assert default is not None
        if org_name and (fresh or default.name == "Default organisation"):
            orgs.update(default.org_id, "cli", name=org_name)
        if default.pack_ref != p.ref and not default.elements and not backend.count_elements():
            orgs.apply(
                default.org_id, p.ref, "cli", force=True
            )  # an empty organisation takes the file's version
        default = orgs.get(default.org_id)
    except Exception:
        # The store is created before the pack is read, so a pack that cannot be loaded would
        # otherwise leave a database behind that looks like a repository and holds nothing.
        if fresh:
            if backend is not None:
                backend.close()
            Path(settings.db_path).unlink(missing_ok=True)
        raise
    typer.echo(
        f"database {settings.db_path}: pack '{p.id}' version {p.version} loaded "
        f"({len(p.element_types)} element types, {len(p.relationship_types)} relationship types); "
        f"organisation '{default.org_id}' ({default.name}) applies {default.pack_ref}"
    )


@app.command("load-pack")
def load_pack_cmd(
    path: Path,
    apply: bool = typer.Option(
        True, "--apply/--no-apply", help="apply the loaded version to the organisation the command works in"
    ),
    force: bool = typer.Option(False, help="apply it even when the compatibility check finds errors"),
):
    """Load a metamodel pack from YAML as the version the file names, and apply it here.

    A version the store holds as a draft is replaced; one it holds published is left as it
    is, and a file that differs from it is refused: give the file a new version.
    """
    from ea.metamodel import load_pack
    from ea.services import MetamodelService, OrganisationService

    require("edit_metamodel", what="load a metamodel pack")
    _, backend, *_ = _ctx()
    p = MetamodelService(backend).save(load_pack(path), "cli")
    typer.echo(f"pack '{p.id}' version {p.version} loaded ({p.status})")
    if apply:
        orgs = OrganisationService(backend)
        org = orgs.current()
        if org.pack_ref == p.ref:
            typer.echo(f"organisation '{org.org_id}' already applies {p.ref}")
            return
        report = orgs.apply(org.org_id, p.ref, "cli", force=force)
        typer.echo(f"organisation '{org.org_id}' now applies {p.ref}: {report.summary()}")
        for iss in report.issues[:20]:
            typer.echo("  " + str(iss))


@app.command("export-pack")
def export_pack(
    out: Path,
    pack_id: str = typer.Option(None, help="pack id (default: the version this organisation applies)"),
    version: str = typer.Option(None, "--version", "-v", help="a stored version as pack@version"),
):
    """Write a stored metamodel version back to YAML."""
    from ea.metamodel import dump_pack

    _, backend, registry, *_ = _ctx()
    ref = version or pack_id
    p = backend.load_pack(*_split_ref(ref)) if ref else registry.pack
    if p is None:
        # Refused before the destination is opened: a pack that cannot be found must not
        # cost the reader the file they were writing over.
        held = ", ".join(v.ref for v in backend.list_pack_versions()) or "none"
        _refuse(f"no metamodel version {ref!r} in this database; it holds: {held}")
    dump_pack(p, out)
    typer.echo(f"pack '{p.id}' version {p.version} written to {out}")


def _split_ref(ref: str) -> tuple[str, str | None]:
    from ea.models import split_pack_ref

    pack_id, version = split_pack_ref(ref)
    return pack_id, version or None


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
    hits = SearchService(backend, registry).search(text, t.id if t else None, limit=limit)
    for h in hits:
        e = h.element
        where = f"  [{h.matched_in}: {h.snippet[:60]}]" if h.matched_in and h.matched_in != "name" else ""
        typer.echo(f"{e.element_id:24s} {e.type_id:32s} {e.name}{where}")
    if not hits:
        # Silence reads as a command that did nothing; `branch list` and `reviewers list`
        # both say when they have nothing to show.
        typer.echo(f"no elements{f' of type {t.name}' if t else ''} match {text!r}")


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
    if not attribute and not any(v is not None for v in fields.values()):
        _refuse(
            "nothing to set: give at least one of --status, --lifecycle, --current-state, "
            "--target-state, --work-package, --note or --attr"
        )
    out = repo.bulk_update(element_ids, actor, fields, attribute)
    typer.echo(f"updated {len(out['updated'])}, refused {len(out['refused'])}")
    for r in out["refused"]:
        typer.echo(f"  {r['element_id']}: {r['reason']}")


@app.command()
def health(fmt: str = typer.Option("table", help="table or md")):
    """Freshness per source system and completeness per element type."""
    from ea.services import HealthService

    _, backend, registry, *_ = _ctx()
    _one_of(fmt, ("table", "md"))
    svc = HealthService(backend, registry)
    fresh, comp = svc.freshness(), svc.completeness()
    sep = "| " if fmt == "md" else ""
    size = capacity.headroom(backend.count_elements(), backend.count_relationships())
    typer.echo(
        f"Size: {size['elements']:,} of {size['assessed_elements']:,} elements ({size['elements_pct']}%), "
        f"{size['relationships']:,} of {size['assessed_relationships']:,} relationships "
        f"({size['relationships_pct']}%) the application is assessed for"
    )
    typer.echo("")
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
    if direction not in ("in", "out", "both"):
        _refuse(f"--direction is 'in', 'out' or 'both', not {direction!r}")
    _, _, _, _, graph = _ctx()
    sub = graph.neighbours(element_id, depth, direction)
    # `trace` and `impact` print their rows in depth order; the rings read as rings only
    # when this one does too.
    for n in sorted(sub["nodes"], key=lambda n: (n["depth"], n["name"])):
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
    text = {"mermaid": to_mermaid, "md": to_markdown, "drawio": to_drawio}[
        _one_of(fmt, ("mermaid", "md", "drawio"))
    ](v)
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

    _one_of(fmt, ("table", "md"))
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
    if status:
        # 'no branches' is what the command says when the model really holds none, so a
        # status it does not know must not borrow that answer.
        _one_of(status, tuple(BRANCH_STATUSES), "--status")
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
    if res.remaining and not res.closed:
        # A merge held back by a conflict otherwise reads exactly like one with nothing to do.
        stuck = [r["key"] for r in svc.item_rows(svc.diff(branch_id)) if r["conflict"]]
        if stuck:
            typer.echo(
                f"  {len(stuck)} unresolved conflict(s) held it back: {', '.join(stuck[:5])}"
                + (" …" if len(stuck) > 5 else "")
            )
            typer.echo("  resolve each with --resolve <key>=branch or --resolve <key>=main, then merge again")


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


# ------------------------------------------------------------- metamodel versions
metamodel_app = typer.Typer(
    help="The metamodel in versions: list, draft, publish, retire, compare, check against an organisation.",
    no_args_is_help=True,
)
app.add_typer(metamodel_app, name="metamodel")


def _metamodels():
    from ea.services import MetamodelService, OrganisationService

    _, backend, registry, *_ = _ctx()
    return backend, registry, MetamodelService(backend), OrganisationService(backend)


@metamodel_app.command("versions")
def metamodel_versions(pack_id: str = typer.Option(None, help="one pack only")):
    """Every stored version, newest first, with its state and the organisations that apply it."""
    _, _, svc, _ = _metamodels()
    rows = svc.versions(pack_id)
    if not rows:
        typer.echo("no metamodel versions")
    for v in rows:
        applied = ", ".join(v.applied_by) or "-"
        typer.echo(
            f"{v.ref:40s} {v.status:10s} applied by {applied:24s} {str(v.loaded_at)[:16]}  {v.name}"
            + (f"  (from {v.derived_from})" if v.derived_from else "")
        )


@metamodel_app.command("draft")
def metamodel_draft(
    from_ref: str = typer.Argument(..., help="the version to copy, as pack@version"),
    version: str = typer.Option(
        None, "--version", "-v", help="the new version's name (default: today's date)"
    ),
    notes: str = typer.Option("", help="what the draft tries"),
    actor: str = typer.Option("cli"),
):
    """Start a draft from a stored version; edit it in the app or as YAML, try it, then publish it."""
    _, _, svc, _ = _metamodels()
    p = svc.draft(from_ref, actor, version, notes)
    typer.echo(f"draft {p.ref} created from {p.derived_from}")


@metamodel_app.command("publish")
def metamodel_publish(ref: str, actor: str = typer.Option("cli")):
    """Freeze a draft: its content cannot change from now on."""
    _, _, svc, _ = _metamodels()
    v = svc.publish(ref, actor)
    typer.echo(f"{v.ref} is {v.status}")


@metamodel_app.command("retire")
def metamodel_retire(ref: str, actor: str = typer.Option("cli")):
    """Take a version out of use; refused while an organisation applies it."""
    _, _, svc, _ = _metamodels()
    v = svc.retire(ref, actor)
    typer.echo(f"{v.ref} is {v.status}")


@metamodel_app.command("delete")
def metamodel_delete(ref: str, actor: str = typer.Option("cli")):
    """Remove a draft nobody applies."""
    _, _, svc, _ = _metamodels()
    svc.delete(ref, actor)
    typer.echo(f"{ref} deleted")


@metamodel_app.command("diff")
def metamodel_diff(ref_a: str, ref_b: str):
    """What changes from one version to another: domains, types, relationship types, attributes."""
    _, _, svc, _ = _metamodels()
    d = svc.diff(ref_a, ref_b)
    typer.echo(d.summary())
    for e in d.entries:
        detail = (
            "" if e.change != "changed" else "  " + "; ".join(f"{f}: {b!r} -> {a!r}" for f, b, a in e.fields)
        )
        typer.echo(f"  {e.change:8s} {e.kind:18s} {e.id:48s} {e.label}{detail}")


@metamodel_app.command("check")
def metamodel_check(
    ref: str,
    org: str = typer.Option(
        None, help="the organisation whose content is checked (default: the current one)"
    ),
    limit: int = typer.Option(50, help="how many findings to print"),
):
    """What an organisation's content would say under a version, without applying it."""
    _, _, _, orgs = _metamodels()
    report = orgs.check(org or orgs.current().org_id, ref)
    typer.echo(report.summary())
    for code, n in report.by_code().items():
        typer.echo(f"  {n:6d}  {code}")
    for iss in report.issues[:limit]:
        typer.echo("  " + str(iss))
    raise typer.Exit(code=0 if report.ok else 1)


# ------------------------------------------------------------------ organisations
org_app = typer.Typer(
    help="The organisations the store holds: which is the default, which metamodel version each applies.",
    no_args_is_help=True,
)
app.add_typer(org_app, name="org")


@org_app.command("list")
def org_list():
    """Every organisation, the default first, with its content and the version it applies."""
    _, _, _, orgs = _metamodels()
    for o in orgs.list():
        typer.echo(
            f"{o.org_id:24s} {'default' if o.is_default else '':8s} {o.pack_ref:40s} "
            f"{o.elements:6d} elements {o.relationships:6d} relationships {o.branches:3d} open branches  {o.name}"
        )


@org_app.command("create")
def org_create(
    name: str,
    description: str = typer.Option("", help="what the organisation is for"),
    metamodel: str = typer.Option(
        "", help="the version it applies, as pack@version (default: the copied or the default organisation's)"
    ),
    copy_from: str = typer.Option(
        None, "--copy-from", help="an organisation whose main content is copied in"
    ),
    org_id: str = typer.Option(None, "--id", help="the identifier (default: derived from the name)"),
    actor: str = typer.Option("cli"),
):
    """A new organisation: a sandbox copied from the default to try a metamodel version, or an enterprise of its own."""
    _, _, _, orgs = _metamodels()
    o = orgs.create(name, actor, description, metamodel, copy_from, org_id)
    typer.echo(
        f"organisation '{o.org_id}' created, applying {o.pack_ref}; "
        f"{o.elements} elements and {o.relationships} relationships"
        + (f" copied from {o.copied_from}" if o.copied_from else "")
        + f"; use --org {o.org_id} on other commands to work in it"
    )


@org_app.command("rename")
def org_rename(
    org_id: str, name: str, description: str = typer.Option(None), actor: str = typer.Option("cli")
):
    """Change an organisation's name or description."""
    _, _, _, orgs = _metamodels()
    o = orgs.update(org_id, actor, name, description)
    typer.echo(f"organisation '{o.org_id}' is now {o.name!r}")


@org_app.command("default")
def org_default(org_id: str, actor: str = typer.Option("cli")):
    """Name the organisation the application opens."""
    _, _, _, orgs = _metamodels()
    o = orgs.set_default(org_id, actor)
    typer.echo(f"organisation '{o.org_id}' is the default")


@org_app.command("apply")
def org_apply(
    org_id: str,
    ref: str = typer.Argument(..., help="the version to apply, as pack@version"),
    force: bool = typer.Option(False, help="apply it even when the compatibility check finds errors"),
    actor: str = typer.Option("cli"),
):
    """Make an organisation apply a metamodel version, after checking its content against it."""
    _, _, _, orgs = _metamodels()
    report = orgs.apply(org_id, ref, actor, force=force)
    typer.echo(f"organisation '{org_id}' now applies {ref}: {report.summary()}")
    for iss in report.issues[:20]:
        typer.echo("  " + str(iss))


@org_app.command("delete")
def org_delete(org_id: str, actor: str = typer.Option("cli")):
    """Remove an organisation and everything in it; the default one stays."""
    _, _, _, orgs = _metamodels()
    orgs.delete(org_id, actor)
    typer.echo(f"organisation '{org_id}' deleted")


def run() -> None:
    """The entry point.

    What the repository refuses is something a person did — an identifier nothing matches,
    a branch nobody created, a role that may not, a file that is not there — and it reaches
    them as a sentence and a failed exit, not as a class name and a stack trace. Everything
    else still raises.
    """
    try:
        app()
    except (NotFoundError, ValidationError, Forbidden, ConflictError, ValueError, OSError) as exc:
        message = (
            "; ".join(str(i) for i in exc.issues)
            if isinstance(exc, ValidationError)
            else f"{exc.filename}: {exc.strerror.lower()}"
            if isinstance(exc, OSError) and exc.filename
            else str(exc)
        )
        typer.echo(message, err=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    run()
