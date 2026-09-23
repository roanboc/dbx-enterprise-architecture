"""Command line: initialise, load packs, import CSVs, ask graph questions, work on branches, organisations and metamodel versions."""

from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

from ea import capacity
from ea.backend.branching import MAIN, set_branch
from ea.config import Settings
from ea.models import (
    BRANCH_STATUSES,
    SORT_ORDERS,
    AttributeFilter,
    ConflictError,
    Element,
    ElementFilter,
    Forbidden,
    NotFoundError,
    Relationship,
    ValidationError,
)
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
        f"database {settings.db_path}: {p.name} version {p.version} loaded "
        f"({len(p.element_types)} element types, {len(p.relationship_types)} relationship types); "
        f"organisation '{default.org_id}' ({default.name}) applies it ({default.pack_ref})"
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
    from ea.metamodel.loader import suspect_split_descriptions
    from ea.services import MetamodelService, OrganisationService

    require("edit_metamodel", what="load a metamodel pack")
    _, backend, *_ = _ctx()
    loaded = load_pack(path)
    p = MetamodelService(backend).save(loaded, "cli")
    typer.echo(f"{p.name} version {p.version} loaded ({p.status}) as {p.ref}")
    for line in suspect_split_descriptions(loaded):
        typer.echo(f"  warning: {line}")
    if apply:
        orgs = OrganisationService(backend)
        org = orgs.current()
        if org.pack_ref == p.ref:
            typer.echo(f"organisation '{org.org_id}' already applies {p.name} {p.version}")
            return
        report = orgs.apply(org.org_id, p.ref, "cli", force=force)
        typer.echo(f"organisation '{org.org_id}' now applies {p.name} {p.version}: {report.summary()}")
        for iss in report.issues[:20]:
            typer.echo("  " + str(iss))


@app.command("export-pack")
def export_pack(
    out: Path,
    pack: str = typer.Option(
        None, "--pack", help="a metamodel by name, or by its identifier (default: the one applied here)"
    ),
    version: str = typer.Option(
        None, "--version", "-v", help="a stored version, as a name or identifier with @version"
    ),
):
    """Write a stored metamodel version back to YAML."""
    from ea.metamodel import dump_pack
    from ea.services import MetamodelService

    _, backend, registry, *_ = _ctx()
    ref = version or pack
    p = None
    if ref:
        # Through the service, not the store: the store takes a canonical identifier and must
        # go on taking one, and resolving a name is the service's job.
        try:
            p = MetamodelService(backend).get(ref)
        except Exception:
            p = None
    else:
        p = registry.pack
    if p is None:
        # Refused before the destination is opened: a pack that cannot be found must not
        # cost the reader the file they were writing over. Held versions are listed by the
        # name a person would type, with the identifier beside it.
        held = ", ".join(f"{v.label} ({v.short_id})" for v in backend.list_pack_versions()) or "none"
        _refuse(f"no metamodel version {ref!r} in this database; it holds: {held}")
    dump_pack(p, out)
    typer.echo(f"{p.name} version {p.version} written to {out}")


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
    issues: int = typer.Option(50, help="how many issues to print; 0 for every one kept"),
):
    """Import elements, relationships and links from CSV files (validated against the metamodel)."""
    from ea.importer import import_directory, load_mapping

    _readable_directory(directory)
    _, backend, registry, *_ = _ctx()
    m = load_mapping(mapping) if mapping else None
    # The text, not the path: a run has to say what the columns meant *then*, and the file it
    # was read from may say something else by the time anybody reads the run.
    said = mapping.read_text(encoding="utf-8") if mapping else ""
    report = import_directory(backend, registry, directory, source, m, actor, dry_run, said)
    typer.echo(report.summary())
    shown = report.issues if issues <= 0 else report.issues[:issues]
    for iss in shown:
        typer.echo("  " + str(iss))
    # A wrong header produces one issue per row, and a terminal scrolled past the summary tells
    # the reader less than the counts do.
    found = sum(report.counts.values())
    if found > len(shown):
        by_code = ", ".join(f"{c} {n}" for c, n in sorted(report.counts.items(), key=lambda kv: -kv[1]))
        typer.echo(f"  … {found - len(shown)} more not shown ({by_code})")
    raise typer.Exit(code=0 if report.ok else 1)


@app.command("export")
def export_cmd(directory: Path):
    """Write the current organisation and branch back out as the CSV contract, ready to re-import."""
    from ea.importer import export_directory

    _, backend, registry, *_ = _ctx()
    counts = export_directory(backend, registry, directory)
    typer.echo(
        f"{directory}: elements {counts['elements']}, relationships {counts['relationships']},"
        f" links {counts['links']}"
    )


@app.command()
def validate(
    directory: Path,
    source: str = typer.Option(""),
    mapping: Path = typer.Option(None),
    issues: int = typer.Option(50, help="how many issues to print; 0 for every one kept"),
):
    """Validate CSV files against the metamodel without loading."""
    import_cmd(directory, source, mapping, True, issues=issues)


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


#: What `--resolve key.field=…` may name. Taken from the rows themselves rather than typed
#: out, so a field added to either dataclass is resolvable the day it exists.
_MERGEABLE_FIELDS = frozenset(
    {f.name for f in fields(Element)} | {f.name for f in fields(Relationship)} | {"links"}
)


def _moment(text: str, what: str) -> datetime | None:
    """An ISO date or date-time a person typed, or a refusal naming the option."""
    if not (text or "").strip():
        return None
    try:
        return datetime.fromisoformat(text.strip())
    except ValueError:
        _refuse(f"{what} must be an ISO date like 2026-01-31, or a date and time")
        return None


def _attribute_filters(pairs: list[str]) -> list[AttributeFilter]:
    """`--attr owner=ana` and `--attr owner` (set to anything) as filters."""
    out = []
    for raw in pairs or []:
        name, _, value = raw.partition("=")
        if not name.strip():
            _refuse(f"--attr {raw!r} names no attribute; write --attr name=value or --attr name")
        out.append(AttributeFilter(name.strip(), value.strip()))
    return out


@app.command()
def find(
    text: str = typer.Argument("", help="words that must all match; omit to list by filter alone"),
    type_id: list[str] = typer.Option(None, "--type", help="repeat for several types"),
    status: list[str] = typer.Option(None, "--status", help="draft, approved or retired; repeatable"),
    current_state: list[str] = typer.Option(None, "--current-state", help="repeatable"),
    target_state: list[str] = typer.Option(None, "--target-state", help="repeatable"),
    work_package: list[str] = typer.Option(None, "--work-package", help="repeatable"),
    source: list[str] = typer.Option(None, "--source", help="source system; repeatable"),
    lifecycle: list[str] = typer.Option(None, "--lifecycle", help="lifecycle text; repeatable"),
    attr: list[str] = typer.Option(None, "--attr", help="name=value, or just name; repeatable"),
    updated_since: str = typer.Option("", "--updated-since", help="ISO date or date-time"),
    updated_before: str = typer.Option("", "--updated-before", help="ISO date or date-time"),
    sort: str = typer.Option("relevance", help=f"one of {', '.join(SORT_ORDERS)}"),
    desc: bool = typer.Option(False, "--desc", help="reverse the sort"),
    limit: int = 50,
    offset: int = typer.Option(0, help="skip this many, to read past the first page"),
    as_json: bool = typer.Option(False, "--json", help="one JSON array, for a script"),
    csv_out: bool = typer.Option(False, "--csv", help="comma-separated, with a header row"),
):
    """Search and filter elements. Every word must match; every criterion narrows together."""
    from ea.services import SearchService

    _, backend, registry, *_ = _ctx()
    types = []
    for one in type_id or []:
        t = registry.resolve_type(one)
        if t is None:
            # Ignoring it would answer the unrestricted search and look like a narrow one.
            _refuse(f"no element type {one!r} in this metamodel; `ea summary` lists them")
        types.append(t.id)
    if sort not in SORT_ORDERS:
        _refuse(f"--sort must be one of {', '.join(SORT_ORDERS)}")
    filt = ElementFilter(
        text=text or "",
        type_ids=types,
        statuses=list(status or []),
        current_states=list(current_state or []),
        target_states=list(target_state or []),
        work_packages=list(work_package or []),
        sources=list(source or []),
        lifecycle_statuses=list(lifecycle or []),
        attributes=_attribute_filters(attr),
        updated_since=_moment(updated_since, "--updated-since"),
        updated_before=_moment(updated_before, "--updated-before"),
        sort=sort,
        descending=desc,
    )
    svc = SearchService(backend, registry)
    hits = svc.search(filt, limit=limit, offset=offset)
    total = svc.count(filt)
    if as_json or csv_out:
        rows = SearchService.rows(hits, registry)
        if as_json:
            typer.echo(json.dumps(rows, indent=2, default=str))
        else:
            out = io.StringIO()
            writer = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["element_id"])
            writer.writeheader()
            writer.writerows(rows)
            typer.echo(out.getvalue().rstrip("\n"))
        return
    for h in hits:
        e = h.element
        where = f"  [{h.matched_in}: {h.snippet[:60]}]" if h.matched_in and h.matched_in != "name" else ""
        typer.echo(f"{e.element_id:24s} {e.type_id:32s} {e.name}{where}")
    if not hits:
        # Silence reads as a command that did nothing; `branch list` and `reviewers list`
        # both say when they have nothing to show.
        typer.echo(f"nothing matches{f' {text!r}' if text else ' those filters'}")
    elif total > offset + len(hits):
        # The old command printed a page and stopped, so a cut list read as a whole one.
        typer.echo(f"… {offset + len(hits)} of {total}; --offset {offset + len(hits)} reads on")


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
    clear_attr: bool = typer.Option(False, "--clear-attr", help="remove the --attr attribute instead"),
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
        name, sep, value = attr.partition("=")
        if not sep and not clear_attr:
            _refuse("--attr takes name=value; to empty an attribute add --clear-attr")
        attribute = (name.strip(), value)
    if not attribute and not any(v is not None for v in fields.values()):
        _refuse(
            "nothing to set: give at least one of --status, --lifecycle, --current-state, "
            "--target-state, --work-package, --note or --attr"
        )
    out = repo.bulk_update(element_ids, actor, fields, attribute, clear_attribute=clear_attr)
    typer.echo(f"updated {len(out['updated'])}, refused {len(out['refused'])}")
    for r in out["refused"]:
        typer.echo(f"  {r['element_id']}: {r['reason']}")
    if out["refused"] and not out["updated"]:
        # Every element refused and an exit code of 0 tells a script the edit was applied.
        raise typer.Exit(code=1)


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


def _viewpoint_named(registry, text: str):
    """The viewpoint an id or a name names, whatever its case (decision 0023). A pack that
    declares none offers the layered drawing; a name nothing matches is refused with the
    ids, because drawing the default instead would hand back a diagram nobody asked for."""
    from ea.views import DEFAULT_VIEWPOINT

    declared = registry.viewpoints() or [DEFAULT_VIEWPOINT]
    key = text.strip().lower()
    for v in declared:
        if key in (v.id.lower(), v.name.lower()):
            return v
    _refuse(f"no viewpoint {text!r}; the viewpoints are: {', '.join(v.id for v in declared)}")
    return None


def _layers_named(text: str) -> list[str]:
    """The architecture layers a comma-separated list names; an unknown one is refused."""
    from ea.views.model import LAYER_ORDER

    layers = [part.strip().lower() for part in text.split(",") if part.strip()]
    unknown = [layer for layer in layers if layer not in LAYER_ORDER]
    if unknown:
        _refuse(f"no layer {', '.join(repr(u) for u in unknown)}; the layers are: {', '.join(LAYER_ORDER)}")
    return layers


@app.command()
def view(
    element_id: str,
    depth: int = 1,
    impact: bool = False,
    fmt: str = "mermaid",
    out: str = "",
    viewpoint: str = typer.Option(
        None, help="draw through a viewpoint the metamodel declares, by id or name (`ea viewpoints`)"
    ),
    layers: str = typer.Option(None, help="comma-separated architecture layers to keep; default: all"),
    detail: str = typer.Option(
        "full",
        help="overview (the focus and what it reaches through structural relationships, at most "
        "thirty elements) or full (everything)",
    ),
):
    """An architecture view of an element as Mermaid (default), Markdown or a draw.io file (--fmt md|drawio)."""
    from ea.views import (
        DEFAULT_VIEWPOINT,
        DETAIL_LEVELS,
        apply_viewpoint,
        overview,
        view_from_impact,
        view_from_neighbourhood,
    )
    from ea.views.drawio import to_drawio
    from ea.views.mermaid import to_markdown, to_mermaid

    _one_of(fmt, ("mermaid", "md", "drawio"))
    _one_of(detail, DETAIL_LEVELS)
    _, _, registry, _, graph = _ctx()
    vp = _viewpoint_named(registry, viewpoint) if viewpoint else None
    kept = _layers_named(layers) if layers else None
    if impact:
        v = view_from_impact(registry, graph, graph.impact(element_id, max(depth, 1) if depth != 1 else 3))
    else:
        v = view_from_neighbourhood(registry, graph, element_id, depth)
    if vp is not None or kept:
        # Narrowed in every format, so the Markdown says what the draw.io file draws.
        v = apply_viewpoint(v, vp, registry, kept)
    if detail == "overview":
        v = overview(v, vp or DEFAULT_VIEWPOINT)
    if fmt == "drawio":
        text = to_drawio(v, viewpoint=vp)
    else:
        text = {"mermaid": to_mermaid, "md": to_markdown}[fmt](v)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        typer.echo(f"{out}: {len(v.nodes)} elements, {len(v.edges)} relationships")
    else:
        typer.echo(text)


def _bands_in_words(v) -> str:
    """How a viewpoint bands a drawing, said the way the grammar says it."""
    if v.bands == "layer":
        return "by architecture layer"
    if v.bands == "type":
        return "by element type" + (f" ({', '.join(v.band_order)})" if v.band_order else "")
    via = ", ".join(v.band_relationships) or "any relationship"
    return f"by {v.band_type} via {via}; other: {v.other_band}"


@app.command()
def viewpoints():
    """The viewpoints the applied metamodel version declares: what each admits, how it bands, what it nests and spans."""
    _, _, registry, *_ = _ctx()
    declared = registry.viewpoints()
    if not declared:
        typer.echo("no viewpoints declared; the layered drawing is used")
        return
    for v in declared:
        typer.echo(f"{v.id:28s} {v.name}")
        typer.echo(f"    bands: {_bands_in_words(v)}")
        if v.element_types:
            typer.echo(f"    admits: {', '.join(v.element_types)}")
        if v.relationship_types:
            typer.echo(f"    relationships: {', '.join(v.relationship_types)}")
        if v.nest:
            typer.echo(f"    nests: {', '.join(v.nest)}")
        if v.span:
            typer.echo(f"    spans: {', '.join(v.span)}")
        if v.description:
            typer.echo(f"    {' '.join(v.description.split())}")


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
        # Three states, not two: a row main moved under without disagreeing merges as it is,
        # and calling that CONFLICT sent people looking for a decision nobody has to make.
        if row["conflict"] == "conflict":
            flag = f"  CONFLICT (both changed: {row['disputed']})"
        elif row["conflict"] == "stale":
            flag = "  stale (main moved, no field in dispute)"
        else:
            flag = ""
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
        None,
        "--resolve",
        "-r",
        help="key=branch or key=main for the whole row, or key.field=branch for one field",
    ),
    actor: str = typer.Option("cli"),
):
    """Merge the branch into main, item by item and field by field.

    A row is a conflict only where both sides changed the same field; everything else merges
    over main's current row. Resolve a whole row with `--resolve element:X=main`, or one field
    at a time with `--resolve element:X.description_md=main`.
    """
    _, _, svc = _branches()
    resolutions: dict[str, Any] = {}
    for r in resolve or []:
        k, _, v = r.partition("=")
        if v not in ("branch", "main"):
            _refuse(f"--resolve {r!r} must end in =branch or =main")
        # An element id may hold a dot ('LDC.FIN'), so a trailing '.something' is only read
        # as a field when 'something' is actually a field of the row it names.
        key, dot, field = k.rpartition(".")
        if dot and key.count(":") == 1 and field in _MERGEABLE_FIELDS:
            per_field = resolutions.setdefault(key, {})
            if not isinstance(per_field, dict):
                _refuse(f"--resolve names {key} both as a whole row and field by field")
            per_field[field] = v
        else:
            if isinstance(resolutions.get(k), dict):
                _refuse(f"--resolve names {k} both as a whole row and field by field")
            resolutions[k] = v
    res = svc.merge(branch_id, actor, set(include) if include else None, resolutions)
    typer.echo(
        f"merged {len(res.applied)} item(s), dropped {len(res.dropped)}, {res.remaining} remaining; branch {'closed' if res.closed else 'still open'}"
    )
    if res.remaining and not res.closed:
        # A merge held back by a conflict otherwise reads exactly like one with nothing to do.
        stuck = [r for r in svc.item_rows(svc.diff(branch_id)) if r["conflict"] == "conflict"]
        if stuck:
            named = ", ".join(f"{r['key']} ({r['disputed']})" for r in stuck[:5])
            typer.echo(
                f"  {len(stuck)} unresolved conflict(s) held it back: {named}"
                + (" …" if len(stuck) > 5 else "")
            )
            typer.echo(
                "  resolve each with --resolve <key>=branch, --resolve <key>=main, or one field at a "
                "time with --resolve <key>.<field>=main, then merge again"
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
def metamodel_versions(
    pack: str = typer.Option(None, "--pack", help="one metamodel only, by name or identifier"),
):
    """Every stored version, with its state and the organisations that apply it.

    The listing leads with what the next command takes: the short identifier, which is what a
    person copies, and the name and version, which are what they read.
    """
    _, _, svc, _ = _metamodels()
    pack_id = svc.resolve_pack(pack) if pack else None
    rows = svc.versions(pack_id)
    if not rows:
        typer.echo("no metamodel versions")
    # What a draft was copied from is stored as a canonical reference. Every version is in
    # hand here, so it is shown as the name and version a reader would recognise instead.
    labels = {v.ref: v.label for v in rows}
    # By name, then newest first inside it — here and not in the store, whose order is what
    # `resolve()` reads to answer "the most recent version of this pack".
    for v in sorted(
        rows, key=lambda v: (v.name or v.pack_id, -(v.loaded_at.timestamp() if v.loaded_at else 0))
    ):
        applied = ", ".join(v.applied_by) or "-"
        typer.echo(
            f"{v.short_id:12s} {v.version:20s} {v.status:10s} applied by {applied:24s} "
            f"{str(v.loaded_at)[:16]}  {v.name}"
            + (f"  (from {labels.get(v.derived_from, v.derived_from)})" if v.derived_from else "")
        )


@metamodel_app.command("draft")
def metamodel_draft(
    from_ref: str = typer.Argument(..., help="the version to copy, by name or identifier with @version"),
    version: str = typer.Option(
        None, "--version", "-v", help="the new version's name (default: today's date)"
    ),
    notes: str = typer.Option("", help="what the draft tries"),
    actor: str = typer.Option("cli"),
):
    """Start a draft from a stored version; edit it in the app or as YAML, try it, then publish it."""
    _, _, svc, _ = _metamodels()
    p = svc.draft(from_ref, actor, version, notes)
    source = svc.version(p.derived_from) if p.derived_from else None
    typer.echo(
        f"draft {p.name} {p.version} created from {source.label if source else p.derived_from} ({p.ref})"
    )


@metamodel_app.command("rename")
def metamodel_rename(
    ref: str = typer.Argument(..., help="the version to rename, by name or identifier, with @version"),
    name: str = typer.Argument(..., help="what it should be called"),
    actor: str = typer.Option("cli"),
):
    """Correct what a metamodel version is called, whatever its status.

    A published version is frozen in what it *defines*; its name is a label and nothing keys
    off it, so it is corrected here rather than by copying the definition into a new version
    (decisions 0021 and 0022). The old name goes into the change log.
    """
    _, _, svc, _ = _metamodels()
    was = svc.version(ref)
    v = svc.rename(ref, name, actor)
    if was.name == v.name:
        typer.echo(f"{v.label} is already called that")
        return
    typer.echo(f"{was.name or was.pack_id} {v.version} is now {v.name} ({v.ref})")


@metamodel_app.command("publish")
def metamodel_publish(ref: str, actor: str = typer.Option("cli")):
    """Freeze a draft: its content cannot change from now on."""
    _, _, svc, _ = _metamodels()
    v = svc.publish(ref, actor)
    typer.echo(f"{v.label} is {v.status} ({v.ref})")


@metamodel_app.command("retire")
def metamodel_retire(ref: str, actor: str = typer.Option("cli")):
    """Take a version out of use; refused while an organisation applies it."""
    _, _, svc, _ = _metamodels()
    v = svc.retire(ref, actor)
    typer.echo(f"{v.label} is {v.status} ({v.ref})")


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
        "",
        help="the version it applies, by name or identifier with @version "
        "(default: the copied or the default organisation's)",
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
    ref: str = typer.Argument(..., help="the version to apply, by name or identifier with @version"),
    force: bool = typer.Option(False, help="apply it even when the compatibility check finds errors"),
    actor: str = typer.Option("cli"),
):
    """Make an organisation apply a metamodel version, after checking its content against it."""
    _, _, _, orgs = _metamodels()
    report = orgs.apply(org_id, ref, actor, force=force)
    # The summary already names the metamodel, the version AND the organisation, so this says
    # what happened and lets the summary say what was checked — rather than naming the
    # organisation twice in one sentence.
    typer.echo(f"applied. {report.summary()}")
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


feed_app = typer.Typer(
    help="Source feeds: the staging tables a source writes to, and running one of them.",
    no_args_is_help=True,
)
app.add_typer(feed_app, name="feed")


@feed_app.command("list")
def feed_list():
    """Every configured feed, with its schedule and when it last ran, in the configured zone."""
    from ea.importer.feeds import in_zone, schedule_in_words

    settings = Settings.from_env()
    _, backend, *_ = _ctx()
    feeds = backend.list_feeds()
    if not feeds:
        typer.echo("No feeds configured. `ea feed save` adds one.")
        return
    for f in feeds:
        where = f.target_branch or "main"
        typer.echo(f"{f.feed_id:22s} {f.name or f.source_system}  -> {where}")
        typer.echo(f"    schedule: {schedule_in_words(f, settings.timezone)}")
        tables = ", ".join(t for t in (f.elements_table, f.relationships_table, f.links_table) if t)
        typer.echo(f"    staging : {tables or 'none named'}")
        if f.last_run_at:
            typer.echo(f"    last run: {in_zone(f.last_run_at, settings.timezone)} — {f.last_run_status}")


@feed_app.command("save")
def feed_save(
    name: str,
    source: str = typer.Option("", help="source system recorded on every row it loads"),
    elements: str = typer.Option("", help="the staging table holding its elements"),
    relationships: str = typer.Option("", help="the staging table holding its relationships"),
    links: str = typer.Option("", help="the staging table holding its links"),
    mapping: Path = typer.Option(None, help="mapping YAML, stored with the feed"),
    branch: str = typer.Option("", help="the branch it writes to; empty writes to main"),
    schedule: str = typer.Option("", help="a cron expression, as whatever triggers it writes them"),
    timezone: str = typer.Option("", help="the zone the schedule is written in; EA_TIMEZONE by default"),
    clear_after: bool = typer.Option(True, help="empty the staging tables once they are loaded"),
    feed_id: str = typer.Option("", help="an existing feed to update; a new one by default"),
):
    """Configure a feed, or update one."""
    from ea.models import SourceFeed

    settings = Settings.from_env()
    _, backend, *_ = _ctx()
    # The page hid the form from a role that may not configure feeds; the command line
    # offered the same write to anybody, so the gate was a suggestion.
    require("manage_feeds", what="configure a feed")
    saved = backend.save_feed(
        SourceFeed(
            feed_id=feed_id,
            name=name,
            source_system=source or name,
            elements_table=elements,
            relationships_table=relationships,
            links_table=links,
            mapping_yaml=mapping.read_text(encoding="utf-8") if mapping else "",
            target_branch=branch,
            clear_after=clear_after,
            schedule=schedule,
            schedule_timezone=timezone or settings.timezone,
        ),
        actor="cli",
    )
    typer.echo(f"{saved.feed_id}  {saved.name}")


@feed_app.command("run")
def feed_run(
    feed_id: str,
    dry_run: bool = typer.Option(False, help="read and validate, load nothing"),
    issues: int = typer.Option(50, help="how many issues to print; 0 for every one kept"),
):
    """Run one configured feed now, on the branch it names."""
    from ea.importer.feeds import run_configured_feed

    _, backend, registry, *_ = _ctx()
    report = run_configured_feed(backend, registry, feed_id, actor="cli", dry_run=dry_run)
    typer.echo(report.summary())
    shown = report.issues if issues <= 0 else report.issues[:issues]
    for iss in shown:
        typer.echo("  " + str(iss))
    found = sum(report.counts.values())
    if found > len(shown):
        by_code = ", ".join(f"{c} {n}" for c, n in sorted(report.counts.items(), key=lambda kv: -kv[1]))
        typer.echo(f"  … {found - len(shown)} more not shown ({by_code})")
    raise typer.Exit(code=0 if report.ok else 1)


@feed_app.command("delete")
def feed_delete(feed_id: str):
    """Forget a feed's configuration. Nothing it loaded is touched."""
    _, backend, *_ = _ctx()
    require("manage_feeds", what="delete a feed")
    backend.delete_feed(feed_id, actor="cli")
    typer.echo(f"{feed_id} deleted")


runs_app = typer.Typer(
    help="Import history: every run, what it read, what it did and how it went.",
    no_args_is_help=True,
)
app.add_typer(runs_app, name="runs")


@runs_app.command("list")
def runs_list(
    feed: str = typer.Option("", help="only this feed's runs; every run by default"),
    limit: int = typer.Option(20, help="how many to show"),
    offset: int = typer.Option(0, help="skip this many, for the page after"),
):
    """Every import run, newest first, in the configured zone. The history is read a page at a time."""
    from ea import capacity
    from ea.importer.feeds import in_zone
    from ea.importer.runs import counts_in_words, describe_inputs

    settings = Settings.from_env()
    _, backend, *_ = _ctx()
    asked = max(1, int(limit))
    # One request reads one page here as it does on the screen (decision 0019). A history is
    # unbounded in a way the model is not — it only grows — so `--limit 1000000` is answered
    # with a page and the offset to ask for the next, rather than with the whole table.
    limit = min(asked, capacity.READ_CHUNK)
    total = backend.count_runs(feed)
    runs = backend.runs(limit, offset, feed)
    if not runs:
        # Three different silences, and they mean different things: nothing has ever run, this
        # feed has never run, or the reader has paged past the end of a history that does exist.
        if total:
            typer.echo(f"No runs on this page. There are {total}; try --offset 0.")
        elif feed:
            typer.echo(f"No runs recorded for feed {feed!r}.")
        else:
            typer.echo("No imports have been recorded yet.")
        return
    for r in runs:
        where = r.branch_id or "main"
        typer.echo(f"{r.run_id:20s} {in_zone(r.started_at, settings.timezone)}  {r.status:7s} -> {where}")
        typer.echo(
            f"    source  : {r.source_system or '—'} ({r.trigger}{f', {r.feed_name}' if r.feed_name else ''})"
        )
        typer.echo(f"    read    : {describe_inputs(r)}")
        typer.echo(f"    did     : {counts_in_words(r) if r.status != 'failed' else r.message}")
        if r.error_count or r.warning_count:
            typer.echo(f"    issues  : {r.error_count} errors, {r.warning_count} warnings")
    if asked > limit:
        typer.echo(f"… --limit is held to {limit} a request; ask for the next page with --offset")
    shown = offset + len(runs)
    if shown < total:
        typer.echo(f"… {total - shown} older not shown (--offset {shown})")


@runs_app.command("show")
def runs_show(
    run_id: str,
    issues: int = typer.Option(50, help="how many issues to print; 0 for every one kept"),
):
    """One run in full: what it read, what it wrote, and the issues it kept."""
    from ea.importer.feeds import in_zone
    from ea.importer.runs import counts_in_words

    settings = Settings.from_env()
    _, backend, *_ = _ctx()
    r = backend.get_run(run_id)
    if r is None:
        typer.echo(f"no run {run_id!r} in this organisation", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"{r.run_id}  {r.status}")
    typer.echo(f"  started : {in_zone(r.started_at, settings.timezone)}")
    typer.echo(f"  finished: {in_zone(r.finished_at, settings.timezone)}")
    typer.echo(f"  source  : {r.source_system or '—'}   trigger: {r.trigger}   actor: {r.actor or '—'}")
    if r.feed_id:
        typer.echo(f"  feed    : {r.feed_name or r.feed_id} ({r.feed_id})")
    typer.echo(f"  branch  : {r.branch_id or 'main'}")
    typer.echo(f"  read    : {', '.join(r.inputs) or 'nothing named'}")
    typer.echo(f"  did     : {counts_in_words(r)}")
    if r.summary:
        typer.echo(f"  said    : {r.summary}")
    if r.message:
        typer.echo(f"  stopped : {r.message}")
    if r.mapping_yaml:
        typer.echo("  mapping : " + r.mapping_yaml.strip().replace("\n", "\n            "))
    shown = r.issues if issues <= 0 else r.issues[:issues]
    for iss in shown:
        typer.echo("  " + str(iss))
    found = sum(r.issue_counts.values())
    if found > len(shown):
        by_code = ", ".join(f"{c} {n}" for c, n in sorted(r.issue_counts.items(), key=lambda kv: -kv[1]))
        # Three numbers, and conflating any two of them misleads: what the run found, what it
        # kept (a sample, most serious first), and what this printed.
        held = len(r.issues)
        if len(shown) < held:
            typer.echo(f"  … the run kept {held} of the {found} issues it found; {len(shown)} printed")
        else:
            typer.echo(f"  … the run kept {held} of the {found} issues it found ({by_code})")


# Last in the file on purpose: `python -m ea.cli` executes the module top to bottom, so a
# command group registered after this line would not exist by the time `run()` reads the
# arguments. Everything the application offers has to be declared above it.
if __name__ == "__main__":
    run()
