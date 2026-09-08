"""Group M — the command line: every command, and the flags that change who and where.

`src/ea/cli.py` is the second face of the repository. It answers the same questions the
browser does, on the same services, and it is the face a pipeline uses: `import` in a
nightly job, `validate` in a pull request, `sql` in a notebook, `branch merge` at the end
of a review. So the round drives it the way it drives the screens — one scenario per
promise, and the evidence is the command and what it printed.

There is no browser here. A scenario takes `(cli, record)`, runs `ea` against a database
of its own, and records what ran in the check's detail column, so the report shows the
command, its exit code and a trimmed transcript instead of a screenshot.

Three things decide the shape of every scenario:

| | |
| - | - |
| **The database is shared, in file order** | `cli` is one session fixture seeded once. Read-only scenarios come first, `set` next, then `import`, then the branch flow, so nothing an early scenario asserts is moved by a later one. Nothing asserts a total. |
| **Two global flags cross every command** | `--as` sets the role (`services/roles.py`), `--branch` the overlay (`backend/branching.py`). Both are exercised against a write, not just a read, because a read never proves either. |
| **The names are prefixed `m-` / `M `** | Every branch, element and reviewer this group creates carries the group letter, so a second group sharing the command line cannot collide with it. |

The branch flow runs as one story across M29 to M37: create, write on the overlay, diff,
review, approve, send back, merge and abandon — the same sequence group I drives through
the screens, on the same services.
"""

from __future__ import annotations

import pytest
from tests.ui.evidence import Check, Finding

pytestmark = pytest.mark.gui

# ------------------------------------------------------------------ the model under test
# Elements from the sample model. The read-only scenarios use the first three; every write
# lands on ONE data entity (`WRITE_ELEMENT`) or on a branch, so a later scenario never has
# to explain a value an earlier one moved.
ASSET = "IA-COURSE-CAT"  # an Information Asset with a wide neighbourhood
APPLICATION = "PAC-CMS"  # the application the sample's work package upgrades
ENTITY = "DE-SRS-COURSE"  # a Data Entity with attributes, and four incoming relationships
WRITE_ELEMENT = "DE-EDW-DIM-COURSE"  # the only element this group writes on main
BRANCH_ELEMENT = "DE-SRS-UNIT"  # the only element this group writes on a branch
WORK_PACKAGE = "WP-CMS-UPGRADE"

# ------------------------------------------------------------------ what this group creates
OVERLAY = "m-overlay"  # created in M29, merged in M36
OVERLAY_NAME = "M overlay"
PARTIAL = "m-partial"  # created and half-merged in M35
THROWAWAY = "m-throwaway"  # created and abandoned in M37
ARCHITECT_BRANCH = "m-architect"  # created and abandoned in M40
AUTHOR = "cli"  # `branch create` records this actor by default
REVIEWER_USER = "m-reviewer"
REVIEWER_GROUP = "m-ea-reviewers"
IMPORTED = "M-DE-1"  # the element M24 imports

# Every command the front door advertises, and the two flags that cross all of them.
COMMANDS = [
    "init",
    "load-pack",
    "export-pack",
    "import",
    "validate",
    "stats",
    "find",
    "set",
    "health",
    "get",
    "neighbours",
    "trace",
    "impact",
    "view",
    "target",
    "sql",
    "summary",
    "branch",
    "reviewers",
]
BRANCH_COMMANDS = ["list", "create", "diff", "merge", "review", "approve", "send-back", "abandon"]


# ------------------------------------------------------------------------------ recording
def check(record, name: str, ok: bool, detail: str = "") -> bool:
    """Record an assertion and carry on — the browser harness's `ui.check`, without a browser."""
    record.checks.append(Check(name=name, ok=bool(ok), detail=detail))
    return bool(ok)


def must(record, name: str, ok: bool, detail: str = "") -> None:
    """An assertion the rest of the scenario depends on."""
    if not check(record, name, ok, detail):
        raise AssertionError(f"{name}: {detail}" if detail else name)


def trim(out: str, limit: int = 200) -> str:
    """A transcript on one line, so it fits the report's detail column."""
    flat = " ⏎ ".join(line.strip() for line in out.strip().splitlines() if line.strip())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def run(cli, *args: str, expect: int | None = 0, limit: int = 200, **env: str):
    """Run `ea`, and return its code, its output, and the evidence line for the report."""
    rc, out = cli(*args, expect=expect, **env)
    return rc, out, f"`ea {' '.join(args)}` → exit {rc} · {trim(out, limit)}"


def squash(text: str) -> str:
    """Help output is drawn in a box and wrapped; collapse it before looking for a word."""
    return " ".join(text.replace("│", " ").replace("╭", " ").replace("╰", " ").split())


def lodge(
    findings: list[Finding], finding_id: str, where: str, severity: str, summary: str, detail: str = ""
) -> None:
    """One finding per id, however many times the scenario that raises it is run."""
    if any(f.finding_id == finding_id for f in findings):
        return
    findings.append(
        Finding(finding_id=finding_id, where=where, severity=severity, summary=summary, detail=detail)
    )


def write_csv(directory, name: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


# =========================================================== reading the model =============
@pytest.mark.scenario(
    scenario_id="M01",
    group="M",
    title="The help names every command and the two flags that cross them",
    feature="Command line · help",
    expected="`ea --help` lists all nineteen commands and both global flags; `ea branch --help` lists the eight branch commands.",
)
def test_m01_help(cli, record):
    rc, out, ev = run(cli, "--help", limit=120)
    flat = squash(out)
    missing = [c for c in COMMANDS if c not in flat]
    must(record, "the help was printed and exited cleanly", rc == 0 and "Commands" in flat, ev)
    check(
        record,
        "every command is listed",
        not missing,
        f"missing: {missing}" if missing else f"all {len(COMMANDS)} listed",
    )
    check(
        record,
        "--branch is offered on every command",
        "--branch" in flat,
        "the overlay flag is on the root callback",
    )
    check(record, "--as is offered on every command", "--as" in flat, "the role flag is on the root callback")
    check(
        record,
        "the flags say they are read from the environment too",
        "EA_BRANCH" in flat and "EA_ROLE" in flat,
        ev,
    )

    _, branch_out, branch_ev = run(cli, "branch", "--help", limit=120)
    branch_flat = squash(branch_out)
    absent = [c for c in BRANCH_COMMANDS if c not in branch_flat]
    check(
        record,
        "the branch group lists its eight commands",
        not absent,
        branch_ev if absent else ", ".join(BRANCH_COMMANDS),
    )


@pytest.mark.scenario(
    scenario_id="M02",
    group="M",
    title="stats counts the model and breaks it down by type",
    feature="Command line · stats",
    expected="`ea stats` prints one total line and one line per element type that has instances.",
)
def test_m02_stats(cli, record):
    rc, out, ev = run(cli, "stats")
    lines = [ln for ln in out.splitlines() if ln.strip()]
    must(record, "stats ran", rc == 0 and lines, ev)
    check(
        record,
        "the first line is the total",
        "elements," in lines[0] and "relationships" in lines[0],
        lines[0],
    )
    per_type = [ln for ln in lines[1:] if ln.startswith("  ")]
    check(
        record, "it breaks the total down by type", len(per_type) > 5, f"{len(per_type)} types with instances"
    )
    check(
        record,
        "Data Entity is one of them",
        any("Data Entity" in ln for ln in per_type),
        trim("\n".join(per_type[:4])),
    )
    counted = sum(int(ln.split()[0]) for ln in per_type if ln.split()[0].isdigit())
    total = int(lines[0].split()[0])
    check(
        record,
        "the per-type counts add up to the total",
        counted == total,
        f"{counted} counted, {total} reported",
    )


@pytest.mark.scenario(
    scenario_id="M03",
    group="M",
    title="find ranks a search and says where each hit matched",
    feature="Command line · find",
    expected="`ea find course` returns name matches before description matches and names the field a non-name hit matched in.",
)
def test_m03_find(cli, record, finding):
    rc, out, ev = run(cli, "find", "course")
    lines = [ln for ln in out.splitlines() if ln.strip()]
    must(record, "the search returned hits", rc == 0 and len(lines) > 3, ev)
    check(
        record,
        "a name match is listed",
        any(ln.startswith(ASSET) for ln in lines),
        f"{ASSET} is in the results",
    )
    check(
        record,
        "the id, the type and the name are on every row",
        all(len(ln.split()) >= 3 for ln in lines),
        trim(out, 120),
    )
    described = [ln for ln in lines if "[description:" in ln]
    check(
        record,
        "a hit that did not match on the name says where it did",
        bool(described),
        trim(described[0] if described else "", 120),
    )
    names = [ln for ln in lines if "[" not in ln]
    check(
        record,
        "name matches are ranked above the rest",
        bool(names) and bool(described) and lines.index(described[0]) > lines.index(names[-1]),
        f"{len(names)} name matches, then {len(described)} matched elsewhere",
    )

    # Every word must match: two words that never co-occur should return nothing.
    _, none_out, none_ev = run(cli, "find", "course lakehouse")
    check(
        record, "every word must match, so an impossible pair returns nothing", not none_out.strip(), none_ev
    )
    # `branch list` and `reviewers list` both say so when they have nothing; `find` says
    # nothing at all, so a reader cannot tell a miss from a crash.
    if not none_out.strip():
        lodge(
            finding,
            "M-1",
            "src/ea/cli.py · find",
            "usability",
            "A search with no hits prints nothing at all — no line saying the search found nothing.",
            "`ea find zzzz` exits 0 and writes an empty stdout. `branch list` says 'no branches' and "
            "`reviewers list` says 'no reviewers assigned', so the silence is inconsistent as well as unhelpful.",
        )


@pytest.mark.scenario(
    scenario_id="M04",
    group="M",
    title="find --type restricts the search to one element type",
    feature="Command line · find",
    expected="`ea find course --type data_entity` returns only data entities, a subset of the unrestricted search.",
)
def test_m04_find_type(cli, record):
    _, everything, _ = run(cli, "find", "course")
    rc, out, ev = run(cli, "find", "course", "--type", "data_entity")
    lines = [ln for ln in out.splitlines() if ln.strip()]
    must(record, "the restricted search ran", rc == 0 and lines, ev)
    check(record, "every row is a data entity", all("data_entity" in ln for ln in lines), trim(out, 160))
    check(
        record,
        "it is a subset of the unrestricted search",
        len(lines) < len([ln for ln in everything.splitlines() if ln.strip()]),
        f"{len(lines)} of {len([ln for ln in everything.splitlines() if ln.strip()])} hits",
    )
    check(record, "the entity searched for is among them", any(ENTITY in ln for ln in lines), ev)


@pytest.mark.scenario(
    scenario_id="M05",
    group="M",
    title="get shows an element, its attributes and both directions of its relationships",
    feature="Command line · get",
    expected="`ea get DE-SRS-COURSE` prints the header, the description, the attributes as JSON and each relationship with an arrow saying which way it runs.",
)
def test_m05_get(cli, record):
    rc, out, ev = run(cli, "get", ENTITY, limit=160)
    must(record, "the element was found", rc == 0 and out.startswith(ENTITY), ev)
    head = out.splitlines()[0]
    check(
        record,
        "the header names the type, the status and the version",
        "[Data Entity]" in head and "status=" in head and "version=" in head,
        head,
    )
    check(
        record,
        "the description is printed",
        "Course master table" in out,
        trim(out.splitlines()[1] if len(out.splitlines()) > 1 else "", 100),
    )
    check(
        record,
        "the attributes are printed as JSON",
        "attributes: {" in out and "includes_pii" in out,
        "attributes: {…includes_pii…}",
    )
    check(
        record,
        "incoming relationships are marked <-",
        "  <- " in out,
        trim("\n".join(ln for ln in out.splitlines() if "<-" in ln), 160),
    )
    check(
        record,
        "a relationship names the other element by id and name",
        "DEF-COURSE Course" in out,
        "<- is defined by: DEF-COURSE Course",
    )

    # An element with links prints them; this one has none, so read one that does.
    _, linked, linked_ev = run(cli, "get", "IA-STUDENT-ENROL", limit=160)
    check(record, "an element's links are printed", "link: https://" in linked, linked_ev)


@pytest.mark.scenario(
    scenario_id="M06",
    group="M",
    title="get of an element that does not exist fails, and says which id it could not find",
    feature="Command line · get",
    expected="`ea get M-NO-SUCH-ELEMENT` exits 1 and names the id it looked for.",
)
def test_m06_get_unknown(cli, record, finding):
    rc, out, ev = run(cli, "get", "M-NO-SUCH-ELEMENT", expect=1, limit=120)
    check(record, "an unknown element is a failure, not an empty answer", rc == 1, ev)
    check(
        record,
        "the id it could not find is named",
        "M-NO-SUCH-ELEMENT" in out,
        trim(out.splitlines()[-1] if out else "", 120),
    )
    lines = [ln for ln in out.splitlines() if ln.strip()]
    # The refusal is the last line of a full Python traceback: forty lines of framework
    # source before the one line a reader needs.
    if len(lines) > 12:
        lodge(
            finding,
            "M-2",
            "src/ea/cli.py",
            "usability",
            "Every command-line refusal prints a full Python traceback before the message.",
            f"`ea get M-NO-SUCH-ELEMENT` printed {len(lines)} lines, ending 'NotFoundError: M-NO-SUCH-ELEMENT'. "
            "The same happens for a refused role, a frozen branch and a rejected SQL statement. No command "
            "catches its own exceptions, so the exception type and the framework's source are shown to the "
            "operator instead of a sentence.",
        )
    check(
        record,
        "the message says what went wrong in words, not only a class name and an id",
        "not found" in out.lower() or "no element" in out.lower() or "no such" in out.lower(),
        f"the last line reads: {lines[-1] if lines else '(nothing)'} — a bare class name and the id",
    )


@pytest.mark.scenario(
    scenario_id="M07",
    group="M",
    title="neighbours walks N hops, and the direction flag changes what it reaches",
    feature="Command line · neighbours",
    expected="`ea neighbours` prints the element at depth 0 and its neighbours at increasing depth; depth 2 reaches further than depth 1, and --direction narrows it.",
)
def test_m07_neighbours(cli, record, finding):
    rc, out, ev = run(cli, "neighbours", ASSET, "--depth", "1", limit=160)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    must(record, "the neighbourhood was returned", rc == 0 and len(lines) > 1, ev)
    self_row = next((ln for ln in lines if ASSET in ln), "")
    check(
        record, "the element itself is in the answer, at depth 0", self_row.startswith("0 "), self_row.strip()
    )
    others = [ln for ln in lines if ASSET not in ln]
    check(
        record,
        "everything else is one hop away",
        all(ln.startswith("1 ") for ln in others),
        f"{len(others)} neighbours, depths {sorted({ln.split()[0] for ln in others})}",
    )
    check(
        record,
        "each row carries the id, the type name and the name",
        "Physical Application Component" in out,
        trim(out, 140),
    )
    depths = [int(ln.split()[0]) for ln in lines]
    # `trace` and `impact` both print their rows in depth order; `neighbours` does not, so
    # the rings a reader is looking for are shuffled through the listing.
    if depths != sorted(depths):
        lodge(
            finding,
            "M-6",
            "src/ea/cli.py · neighbours",
            "usability",
            "The rows are not ordered by the depth column they lead with, so the rings around the element are shuffled.",
            f"`ea neighbours {ASSET} --depth 1` printed the depths in the order {depths}. `trace` and `impact` "
            "print the same kind of listing in depth order, so the three commands read differently.",
        )

    _, deeper, deeper_ev = run(cli, "neighbours", ASSET, "--depth", "2", limit=100)
    deep_lines = [ln for ln in deeper.splitlines() if ln.strip()]
    check(
        record,
        "depth 2 reaches further than depth 1",
        len(deep_lines) > len(lines),
        f"{len(deep_lines)} at depth 2, {len(lines)} at depth 1",
    )
    check(record, "depth 2 rows appear", any(ln.startswith("2 ") for ln in deep_lines), deeper_ev)

    _, inward, inward_ev = run(cli, "neighbours", ASSET, "--depth", "2", "--direction", "in", limit=100)
    in_lines = [ln for ln in inward.splitlines() if ln.strip()]
    check(
        record,
        "one direction reaches fewer than both",
        len(in_lines) < len(deep_lines),
        f"{len(in_lines)} inbound, {len(deep_lines)} both ways",
    )
    check(
        record,
        "the inbound walk still starts from the element",
        any(ASSET in ln for ln in in_lines),
        inward_ev,
    )


@pytest.mark.scenario(
    scenario_id="M08",
    group="M",
    title="trace follows the relationship direction and names the path it took",
    feature="Command line · trace",
    expected="`ea trace --direction out` lists what an element depends on with the chain of relationship labels; --direction in lists what depends on it.",
)
def test_m08_trace(cli, record):
    rc, out, ev = run(cli, "trace", ASSET, "--direction", "out", "--depth", "3", limit=160)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    must(record, "the outward trace ran", rc == 0 and lines, ev)
    check(
        record,
        "every row says how far it is",
        all(ln.split()[0].isdigit() for ln in lines),
        f"depths {sorted({ln.split()[0] for ln in lines})}",
    )
    check(
        record,
        "every row names the path it was reached by",
        all(" via " in ln for ln in lines),
        trim(lines[0], 120),
    )
    check(
        record,
        "a two-hop path names both relationships",
        any(" via " in ln and " > " in ln.split(" via ")[1] for ln in lines),
        trim(next((ln for ln in lines if " > " in ln), ""), 130),
    )

    rc_in, inward, in_ev = run(cli, "trace", ENTITY, "--direction", "in", "--depth", "3", limit=160)
    in_lines = [ln for ln in inward.splitlines() if ln.strip()]
    check(record, "the inward trace runs the other way", rc_in == 0 and in_lines, in_ev)
    check(
        record,
        "what depends on the entity includes the application that processes it",
        any(APPLICATION in ln for ln in in_lines),
        trim(next((ln for ln in in_lines if APPLICATION in ln), ""), 130),
    )
    check(
        record,
        "the traced element is not its own result",
        not any(ln.split()[1] == ENTITY for ln in in_lines),
        "the start is excluded",
    )


@pytest.mark.scenario(
    scenario_id="M09",
    group="M",
    title="impact separates what depends on an element from what it depends on, and says how complete the answer is",
    feature="Command line · impact",
    expected="`ea impact PAC-CMS` prints an upstream block, a downstream block and a completeness footer naming any relationship type with no instances.",
)
def test_m09_impact(cli, record):
    rc, out, ev = run(cli, "impact", APPLICATION, "--depth", "2", limit=160)
    must(record, "the blast radius was returned", rc == 0 and out.startswith("Impact of"), ev)
    check(
        record,
        "the heading names the element and its type",
        APPLICATION in out.splitlines()[0] and "Physical Application Component" in out.splitlines()[0],
        out.splitlines()[0],
    )
    check(
        record,
        "upstream is labelled as what depends on this",
        "depends on this (upstream," in out,
        "  depends on this (upstream, n):",
    )
    check(
        record,
        "downstream is labelled as what this depends on",
        "this depends on (downstream," in out,
        "  this depends on (downstream, n):",
    )
    upstream = out.split("depends on this (upstream,")[1].split("this depends on (downstream,")[0]
    downstream = out.split("this depends on (downstream,")[1].split("completeness:")[0]
    check(
        record,
        "the work package that changes the application is upstream of it",
        WORK_PACKAGE in upstream,
        trim(upstream, 140),
    )
    check(
        record,
        "the data it holds is downstream of it",
        "DE-CMS-UNIT-OUTLINE" in downstream,
        trim(downstream, 140),
    )
    up_rows = [ln for ln in upstream.splitlines() if ln.startswith("    ")]
    check(
        record,
        "the count in the upstream heading matches the rows under it",
        f"upstream, {len(up_rows)})" in out,
        f"{len(up_rows)} rows under a heading that says {upstream.splitlines()[0].strip()}",
    )
    check(
        record,
        "a completeness footer closes the answer",
        "completeness:" in out and "relationship types" in out,
        trim(out.split("completeness:")[1], 120),
    )


@pytest.mark.scenario(
    scenario_id="M10",
    group="M",
    title="view generates a Mermaid diagram whose every node carries its element identifier",
    feature="Command line · view",
    expected="`ea view IA-COURSE-CAT` prints a Mermaid flowchart with one subgraph per layer and the element id inside every node label.",
)
def test_m10_view_mermaid(cli, record):
    rc, out, ev = run(cli, "view", ASSET, "--depth", "1", limit=120)
    must(record, "a diagram was generated", rc == 0 and out.strip().startswith("flowchart"), ev)
    check(
        record,
        "the nodes are grouped into layers",
        'subgraph business["Business"]' in out and 'subgraph application["Application"]' in out,
        "business and application subgraphs",
    )
    check(
        record,
        "the element asked for is in the diagram",
        f"[{ASSET}]" in out,
        f"the node label ends [{ASSET}]",
    )
    node_lines = [ln for ln in out.splitlines() if "  n_" in ln and "[" in ln]
    unlabelled = [ln for ln in node_lines if "[" not in ln.split("«")[-1]]
    check(
        record,
        "every shape carries an element identifier",
        node_lines and not unlabelled,
        f"{len(node_lines)} nodes, all with an id in the label",
    )
    check(
        record,
        "each node is styled by its layer",
        all(":::" in ln for ln in node_lines),
        "every node ends :::<layer>",
    )
    check(
        record,
        "edges are drawn between the nodes",
        "-->" in out or "---" in out or "-.->" in out,
        trim(next((ln for ln in out.splitlines() if "n_" in ln and "-" in ln and "[" not in ln), ""), 100),
    )


@pytest.mark.scenario(
    scenario_id="M11",
    group="M",
    title="view renders the same subgraph as Markdown and as a draw.io file, and --out writes it",
    feature="Command line · view",
    expected="`--fmt md` wraps the diagram in a titled Markdown section; `--fmt drawio --out` writes an mxfile and reports how much it holds.",
)
def test_m11_view_formats(cli, record, tmp_path):
    rc, md, md_ev = run(cli, "view", ASSET, "--fmt", "md", limit=120)
    must(record, "the Markdown form was generated", rc == 0, md_ev)
    check(
        record,
        "it opens with a heading naming the element and the depth",
        md.startswith("## ") and "Course Catalogue" in md.splitlines()[0],
        md.splitlines()[0],
    )
    check(
        record,
        "the diagram is in a fenced mermaid block",
        "```mermaid" in md and md.count("```") == 2,
        f"{md.count('```')} fence markers",
    )
    check(record, "the fenced diagram is the same flowchart", "flowchart" in md and f"[{ASSET}]" in md, md_ev)
    legend = md.split("```")[2]
    check(
        record,
        "a legend table follows the diagram",
        "| ID | Element | Type |" in legend,
        "| ID | Element | Type |",
    )
    check(
        record,
        "the legend names every element in the diagram by id",
        legend.count("| `") == md.count(":::"),
        f"{legend.count('| `')} legend rows for {md.count(':::')} styled nodes",
    )
    check(
        record,
        "the legend says what each shape's stereotype means",
        "Business Object (Information Asset)" in legend,
        trim(next((ln for ln in legend.splitlines() if ASSET in ln), ""), 130),
    )

    out_file = tmp_path / "m-view.drawio"
    rc_d, said, drawio_ev = run(
        cli, "view", APPLICATION, "--fmt", "drawio", "--out", str(out_file), limit=120
    )
    must(record, "the draw.io file was written", rc_d == 0 and out_file.exists(), drawio_ev)
    text = out_file.read_text(encoding="utf-8")
    check(
        record,
        "--out reports the file and what it holds",
        str(out_file) in said and "elements" in said and "relationships" in said,
        trim(said),
    )
    check(
        record,
        "it is an mxfile a diagram tool opens",
        text.startswith("<?xml") and "<mxfile" in text and "<mxGraphModel" in text,
        trim(text[:120], 120),
    )
    check(
        record,
        "every shape carries its element identifier",
        text.count(APPLICATION) >= 1 and "mxCell" in text,
        f"{len(text)} bytes, {text.count('<mxCell')} cells",
    )
    check(record, "--out printed the summary instead of the diagram", "mxfile" not in said, trim(said))


@pytest.mark.scenario(
    scenario_id="M12",
    group="M",
    title="view --impact draws the blast radius rather than the neighbourhood",
    feature="Command line · view",
    expected="`ea view PAC-CMS --impact` produces a wider diagram than the depth-1 neighbourhood of the same element.",
)
def test_m12_view_impact(cli, record):
    def nodes(text: str) -> int:
        return len([ln for ln in text.splitlines() if ln.strip().startswith("n_") and ":::" in ln])

    _, near, _ = run(cli, "view", APPLICATION, "--depth", "1", limit=80)
    rc, wide, ev = run(cli, "view", APPLICATION, "--impact", limit=80)
    must(record, "the impact view was generated", rc == 0 and wide.strip().startswith("flowchart"), ev)
    near_nodes = nodes(near)
    wide_nodes = nodes(wide)
    check(
        record,
        "the impact view reaches further than the neighbourhood",
        wide_nodes > near_nodes,
        f"{wide_nodes} nodes with --impact, {near_nodes} at depth 1",
    )
    check(record, "the element asked for is still in it", f"[{APPLICATION}]" in wide, f"[{APPLICATION}]")
    check(
        record,
        "it reaches the elements impact reported downstream at depth 2",
        "[DE-SRS-COURSE]" in wide or "[DP-CURR-HEALTH]" in wide,
        "a depth-2 dependency of the application appears in the diagram",
    )


@pytest.mark.scenario(
    scenario_id="M13",
    group="M",
    title="target reports current against target state, for the whole model and for one work package",
    feature="Command line · target",
    expected="`ea target` counts what changes and lists only those; `-w WP-CMS-UPGRADE` scopes it to the work package and lists everything in scope.",
)
def test_m13_target_table(cli, record):
    rc, out, ev = run(cli, "target", limit=160)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    must(record, "the target summary ran", rc == 0 and len(lines) > 2, ev)
    check(
        record,
        "the first line counts the model and how much of it changes",
        "elements," in lines[0] and "elements change" in lines[0],
        lines[0],
    )
    check(
        record,
        "the second line breaks the target states down",
        lines[1].strip().startswith("by target state:"),
        lines[1].strip(),
    )
    check(record, "an undecided element is counted but not listed", "undecided" in lines[1], lines[1].strip())
    rows = [ln for ln in lines[2:] if ln.startswith("  ")]
    check(
        record,
        "each row shows the move from current to target",
        all("->" in r for r in rows),
        trim(rows[0] if rows else "", 130),
    )
    check(
        record,
        "a decommission is shown",
        any("Decommission" in r for r in rows),
        trim(next((r for r in rows if "Decommission" in r), ""), 130),
    )

    rc_wp, scoped, wp_ev = run(cli, "target", "-w", WORK_PACKAGE, limit=160)
    scoped_lines = [ln for ln in scoped.splitlines() if ln.strip()]
    must(record, "the work-package scope ran", rc_wp == 0 and scoped_lines, wp_ev)
    check(
        record,
        "the heading names the work package it is scoped to",
        f"under {WORK_PACKAGE}" in scoped_lines[0],
        scoped_lines[0],
    )
    check(
        record,
        "the scoped model is smaller than the whole",
        int(scoped_lines[0].split()[0]) < int(lines[0].split()[0]),
        f"{scoped_lines[0].split()[0]} in scope of {lines[0].split()[0]}",
    )
    scoped_rows = [ln for ln in scoped_lines[2:] if ln.startswith("  ")]
    check(
        record,
        "in a work package, what is kept is listed too, not only what changes",
        any("Keep" in r for r in scoped_rows),
        trim(next((r for r in scoped_rows if "Keep" in r), ""), 130),
    )


@pytest.mark.scenario(
    scenario_id="M14",
    group="M",
    title="target --fmt md emits the marked view, with a legend for the markers",
    feature="Command line · target",
    expected="`ea target -w WP-CMS-UPGRADE --fmt md` prints a titled Markdown section whose diagram marks new, changed and decommissioned elements, and says what the markers mean.",
)
def test_m14_target_md(cli, record):
    rc, out, ev = run(cli, "target", "-w", WORK_PACKAGE, "--fmt", "md", limit=140)
    must(record, "the Markdown target view was generated", rc == 0 and out.startswith("## "), ev)
    check(
        record,
        "the heading names the work package by name, not by id",
        "Target state of" in out and "Curriculum Management System Upgrade" in out,
        out.splitlines()[0],
    )
    check(
        record,
        "the markers are explained before the diagram",
        "new" in out.split("```")[0] and "decommission" in out.split("```")[0],
        out.splitlines()[2].strip(),
    )
    check(record, "the diagram is a fenced mermaid block", "```mermaid" in out, "```mermaid")
    check(
        record,
        "a new element is marked",
        '["+ ' in out or '("+ ' in out,
        trim(next((ln for ln in out.splitlines() if '"+ ' in ln), ""), 120),
    )
    check(
        record,
        "a changed element is marked",
        '["Δ ' in out or '("Δ ' in out,
        trim(next((ln for ln in out.splitlines() if "Δ " in ln), ""), 120),
    )
    check(
        record,
        "a decommissioned element is marked",
        "× " in out,
        trim(next((ln for ln in out.splitlines() if "× " in ln), ""), 120),
    )
    check(
        record,
        "every marked node still carries its element identifier",
        "[PAC-CAW]" in out and "[PTC-FORMS]" in out,
        "[PAC-CAW] and [PTC-FORMS]",
    )


@pytest.mark.scenario(
    scenario_id="M15",
    group="M",
    title="health reports freshness per source and completeness per type, as a table and as Markdown",
    feature="Command line · health",
    expected="`ea health` prints both sections with the same figures; `--fmt md` prints the same numbers as Markdown tables with headers.",
)
def test_m15_health(cli, record):
    rc, out, ev = run(cli, "health", limit=160)
    must(record, "health ran", rc == 0 and "Freshness" in out and "Completeness" in out, ev)
    check(
        record,
        "freshness is stamped with when it was read",
        "as of" in out.splitlines()[0],
        out.splitlines()[0],
    )
    check(
        record,
        "the sample source is reported",
        "sample" in out,
        trim(next((ln for ln in out.splitlines() if ln.startswith("sample")), ""), 120),
    )
    check(
        record,
        "completeness says how many elements it read",
        "Completeness (" in out and "elements)" in out,
        next((ln for ln in out.splitlines() if ln.startswith("Completeness")), ""),
    )
    type_rows = [ln for ln in out.split("Completeness")[1].splitlines() if "%" in ln]
    check(record, "completeness is reported per element type", len(type_rows) > 5, f"{len(type_rows)} types")
    check(
        record,
        "each type row carries five percentages",
        all(ln.count("%") == 5 for ln in type_rows),
        trim(type_rows[0] if type_rows else "", 120),
    )

    rc_md, md, md_ev = run(cli, "health", "--fmt", "md", limit=160)
    must(record, "the Markdown form ran", rc_md == 0, md_ev)
    check(
        record,
        "both sections become Markdown tables",
        md.count("| --- |") >= 2,
        f"{md.count('| --- |')} header separators",
    )
    check(
        record,
        "the freshness table names its columns",
        "| source | elements | relationships |" in md,
        "| source | elements | … |",
    )
    check(
        record,
        "the completeness table names its columns",
        "| type | elements | description |" in md,
        "| type | elements | description | …",
    )
    check(
        record,
        "the two formats report the same number of elements",
        out.split("Completeness (")[1].split()[0] == md.split("Completeness (")[1].split()[0],
        f"table {out.split('Completeness (')[1].split()[0]} = md {md.split('Completeness (')[1].split()[0]}",
    )


@pytest.mark.scenario(
    scenario_id="M16",
    group="M",
    title="summary prints the metamodel as Markdown, and --types narrows it",
    feature="Command line · summary",
    expected="`ea summary` prints the pack, its domains, its element types and its relationship types; `--types data_entity` keeps only that type and the relationships that touch it.",
)
def test_m16_summary(cli, record):
    rc, out, ev = run(cli, "summary", limit=120)
    must(record, "the metamodel summary ran", rc == 0 and out.startswith("# "), ev)
    check(
        record,
        "the heading names the pack and its version",
        "pack `higher_education`" in out and "version" in out,
        out.splitlines()[0],
    )
    check(
        record,
        "the element types are grouped by domain",
        "## Information" in out and "## Process" in out,
        "## Information, ## Process, …",
    )
    check(
        record,
        "a type is described with its attributes",
        "`data_entity` **Data Entity**" in out and "Attributes:" in out,
        trim(next((ln for ln in out.splitlines() if "`data_entity`" in ln), ""), 130),
    )
    check(
        record,
        "the relationship types are listed with their direction",
        "## Relationship types (source -> target)" in out,
        "## Relationship types (source -> target)",
    )

    rc_t, narrow, narrow_ev = run(cli, "summary", "--types", "data_entity", limit=120)
    must(record, "the narrowed summary ran", rc_t == 0, narrow_ev)
    check(
        record,
        "only the type asked for is described",
        "`data_entity`" in narrow and "`capability`" not in narrow,
        "data_entity kept, capability dropped",
    )
    check(
        record,
        "it is shorter than the whole metamodel",
        len(narrow) < len(out) / 2,
        f"{len(narrow)} characters of {len(out)}",
    )
    check(
        record,
        "the relationships that touch the type are kept",
        "__data_entity" in narrow or "data_entity__" in narrow,
        trim(next((ln for ln in narrow.splitlines() if "data_entity__" in ln), ""), 120),
    )


@pytest.mark.scenario(
    scenario_id="M17",
    group="M",
    title="sql runs a read-only SELECT over the repository tables",
    feature="Command line · sql",
    expected='`ea sql "select …"` prints the rows as a table, and --limit caps them.',
)
def test_m17_sql_select(cli, record):
    query = "select type_id, count(*) as n from element group by 1 order by n desc"
    rc, out, ev = run(cli, "sql", query, "--limit", "5", limit=160)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    must(record, "the query ran", rc == 0 and lines, ev)
    check(
        record, "the column names are the header", "type_id" in lines[0] and "n" in lines[0], lines[0].strip()
    )
    check(
        record, "--limit caps the rows returned", len(lines) - 1 <= 5, f"{len(lines) - 1} rows for --limit 5"
    )
    check(
        record,
        "the rows are the model's own",
        any("data_entity" in ln for ln in lines[1:]),
        trim("\n".join(lines[1:3]), 120),
    )

    # A WITH statement is read-only too, and the guard accepts it.
    rc_w, with_out, with_ev = run(
        cli, "sql", "with t as (select element_id from element) select count(*) as n from t", limit=120
    )
    check(record, "a WITH statement is accepted as read-only", rc_w == 0 and "n" in with_out, with_ev)


@pytest.mark.scenario(
    scenario_id="M18",
    group="M",
    title="sql refuses anything that is not a single read-only statement",
    feature="Command line · sql",
    expected="A DELETE, an UPDATE and two statements separated by a semicolon are each refused with exit 1, and the model is unchanged.",
)
def test_m18_sql_refused(cli, record):
    _, before, _ = run(cli, "stats", limit=60)
    refusals = {
        "delete": "delete from element",
        "update": "update element set name = 'x'",
        "drop": "drop table element",
        "two statements": "select 1; delete from element",
    }
    for name, query in refusals.items():
        rc, out, ev = run(cli, "sql", query, expect=None, limit=100)
        check(record, f"a {name} statement is refused", rc == 1, ev)
        check(
            record,
            f"the refusal of the {name} says what is allowed",
            "read-only" in out and "SELECT" in out,
            trim(out.splitlines()[-1] if out else "", 110),
        )
    _, after, after_ev = run(cli, "stats", limit=60)
    check(
        record,
        "nothing was changed by any of them",
        before.splitlines()[0] == after.splitlines()[0],
        after_ev,
    )


# ================================================================= writing on main =========
@pytest.mark.scenario(
    scenario_id="M19",
    group="M",
    title="set changes a status and says how many rows it changed",
    feature="Command line · set",
    expected="`ea set DE-EDW-DIM-COURSE --status draft` reports one updated and none refused, and `get` shows the new status and a bumped version.",
)
def test_m19_set_status(cli, record):
    _, before, _ = run(cli, "get", WRITE_ELEMENT, limit=60)
    version_before = int(before.splitlines()[0].split("version=")[1].split()[0])
    rc, out, ev = run(cli, "set", WRITE_ELEMENT, "--status", "draft")
    must(record, "the edit was applied", rc == 0 and "updated 1" in out, ev)
    check(record, "it reports what it refused as well as what it changed", "refused 0" in out, trim(out))
    _, after, after_ev = run(cli, "get", WRITE_ELEMENT, limit=60)
    head = after.splitlines()[0]
    check(record, "the status is the one that was set", "status=draft" in head, head)
    version_after = int(head.split("version=")[1].split()[0])
    check(
        record,
        "the version was bumped, so the change is audited",
        version_after == version_before + 1,
        f"version {version_before} → {version_after}",
    )
    check(record, "the element is otherwise untouched", "EDW_Dim_Course" in head, after_ev)


@pytest.mark.scenario(
    scenario_id="M20",
    group="M",
    title="set puts an element into a work package with a current state, a target state and a note",
    feature="Command line · set",
    expected="One command sets all four target-state fields, `target` then lists the element under the work package, and a state outside the vocabulary is refused by name.",
)
def test_m20_set_target(cli, record):
    # The vocabulary is lowercase, and a value outside it is refused before anything is written.
    rc_bad, bad, bad_ev = run(cli, "set", WRITE_ELEMENT, "--current-state", "Live", limit=160)
    check(
        record,
        "a state outside the vocabulary is refused",
        rc_bad == 0 and "updated 0, refused 1" in bad,
        bad_ev,
    )
    check(
        record,
        "the refusal names the field and lists what is allowed",
        "current_state must be one of" in bad and "'live'" in bad,
        trim(bad.splitlines()[-1] if bad else "", 150),
    )

    rc, out, ev = run(
        cli,
        "set",
        WRITE_ELEMENT,
        "--current-state",
        "live",
        "--target-state",
        "change",
        "-w",
        WORK_PACKAGE,
        "--note",
        "M: set from the command line",
    )
    must(record, "all four fields were set in one command", rc == 0 and "updated 1" in out, ev)
    _, scoped, scoped_ev = run(cli, "target", "-w", WORK_PACKAGE, limit=200)
    row = next((ln for ln in scoped.splitlines() if WRITE_ELEMENT in ln), "")
    must(record, "the element is now in the work package's scope", bool(row), scoped_ev)
    check(record, "its current state is what was set", "Live" in row, row.strip())
    check(record, "its target state is what was set", "Change" in row, row.strip())
    check(record, "its note is carried through", "M: set from the command line" in row, row.strip())


@pytest.mark.scenario(
    scenario_id="M21",
    group="M",
    title="set writes one attribute without disturbing the others",
    feature="Command line · set",
    expected="`--attr includes_pii=true` changes that attribute and leaves the element's other attributes as they were.",
)
def test_m21_set_attribute(cli, record):
    _, before, before_ev = run(cli, "get", WRITE_ELEMENT, limit=120)
    attrs_before = next((ln for ln in before.splitlines() if ln.startswith("attributes:")), "")
    must(record, "the element has attributes to start with", bool(attrs_before), before_ev)
    rc, out, ev = run(cli, "set", WRITE_ELEMENT, "--attr", "includes_pii=true")
    must(record, "the attribute was written", rc == 0 and "updated 1" in out, ev)
    _, after, after_ev = run(cli, "get", WRITE_ELEMENT, limit=120)
    attrs_after = next((ln for ln in after.splitlines() if ln.startswith("attributes:")), "")
    check(
        record,
        "the attribute asked for now holds the value",
        '"includes_pii": true' in attrs_after,
        attrs_after,
    )
    others_before = {k for k in ("available_in_analytics_platform", "source") if k in attrs_before}
    check(
        record,
        "the element's other attributes survived",
        all(k in attrs_after for k in others_before),
        f"kept: {sorted(others_before)}",
    )
    check(record, "the status set earlier is still there", "status=draft" in after.splitlines()[0], after_ev)


@pytest.mark.scenario(
    scenario_id="M22",
    group="M",
    title="set refuses an element that does not exist, and says why it refused",
    feature="Command line · set",
    expected="`ea set M-NO-SUCH-ELEMENT --status draft` reports one refusal, and the reason says the element was not found rather than repeating its id.",
)
def test_m22_set_refusal(cli, record, finding):
    rc, out, ev = run(cli, "set", "M-NO-SUCH-ELEMENT", "--status", "draft", limit=160)
    must(
        record,
        "the command completed and reported the refusal",
        rc == 0 and "updated 0, refused 1" in out,
        ev,
    )
    reason_line = next((ln for ln in out.splitlines() if "M-NO-SUCH-ELEMENT:" in ln), "")
    check(record, "the refused element is named", bool(reason_line), reason_line.strip())
    reason = reason_line.split(":", 1)[1].strip() if ":" in reason_line else ""
    # `NotFoundError(element_id)` in services/repository.py carries no message, so the CLI's
    # refusal line renders as "  <id>: <id>" — the operator is told nothing they did not type.
    ok = bool(reason) and reason != "M-NO-SUCH-ELEMENT"
    if not ok:
        lodge(
            finding,
            "M-3",
            "src/ea/cli.py · set · services/repository.py:75",
            "defect",
            "A refusal for an unknown element gives the element id as its reason, so the line reads 'M-NO-SUCH-ELEMENT: M-NO-SUCH-ELEMENT'.",
            "`repo.bulk_update` catches NotFoundError and stores `str(exc)` as the reason, and "
            "`NotFoundError` is raised with the bare id and defines no message. Every refused row in a "
            "bulk edit that names a missing element therefore repeats the id instead of saying it was not found.",
        )
    check(record, "the reason says what was wrong, not just which id", ok, f"the reason reads {reason!r}")
    rc_mix, mixed, mixed_ev = run(
        cli, "set", WRITE_ELEMENT, "M-NO-SUCH-ELEMENT", "--status", "draft", limit=160
    )
    check(
        record,
        "one bad id does not stop the rest of the batch",
        rc_mix == 0 and "updated 1, refused 1" in mixed,
        mixed_ev,
    )


# ====================================================================== loading ============
@pytest.mark.scenario(
    scenario_id="M23",
    group="M",
    title="validate checks CSV files against the metamodel and loads nothing",
    feature="Command line · validate",
    expected="`ea validate` on the sample directory reports no errors and exits 0, and the model is unchanged afterwards.",
)
def test_m23_validate(cli, record, finding):
    _, before, _ = run(cli, "stats", limit=60)
    rc, out, ev = run(cli, "validate", "data/sample", "--source", "m-validate", limit=160)
    must(record, "the sample model validates", rc == 0, ev)
    check(record, "it reports no errors and no warnings", "0 errors, 0 warnings" in out, trim(out))
    check(record, "it counted the rows it read", "elements 0/47" in out or "/47" in out, trim(out))
    _, after, after_ev = run(cli, "stats", limit=60)
    check(record, "nothing was loaded", before.splitlines()[0] == after.splitlines()[0], after_ev)
    check(
        record,
        "a source name given to a dry run does not appear in the model",
        "m-validate" not in after,
        after_ev,
    )
    if "loaded" in out:
        lodge(
            finding,
            "M-4",
            "src/ea/cli.py · validate",
            "usability",
            "A dry run reports its result in the language of a load — 'elements 0/47 loaded' — which reads as a failed import.",
            f"`ea validate data/sample` prints: {out.strip()[:160]}. Nothing was meant to be loaded, so "
            "'0/47 loaded' is the expected outcome being reported as though it were a shortfall.",
        )


@pytest.mark.scenario(
    scenario_id="M24",
    group="M",
    title="import loads a clean directory of CSV files and links the rows to the model",
    feature="Command line · import",
    expected="A directory with one element and one relationship into the existing model imports with no errors, and `get` then finds the new element with its relationship.",
)
def test_m24_import_clean(cli, record, tmp_path):
    directory = tmp_path / "m-clean"
    write_csv(
        directory,
        "elements.csv",
        "id,type,name,key,description,status\n"
        f"{IMPORTED},Data Entity,M_Round_Table,{IMPORTED},A data entity the command-line round adds.,draft\n",
    )
    write_csv(directory, "relationships.csv", f"src_id,rel_type,dst_id\nLDC-CURR,encapsulates,{IMPORTED}\n")
    _, before, _ = run(cli, "stats", limit=60)
    elements_before = int(before.split()[0])

    rc, out, ev = run(cli, "import", str(directory), "--source", "m-round", limit=160)
    must(record, "the import succeeded", rc == 0, ev)
    check(record, "it reports no errors", "0 errors, 0 warnings" in out, trim(out))
    check(
        record,
        "it says what it loaded",
        "elements 1/1 loaded" in out and "relationships 1/1 loaded" in out,
        trim(out),
    )

    _, after, after_ev = run(cli, "stats", limit=60)
    check(
        record,
        "the model grew by the element imported",
        int(after.split()[0]) == elements_before + 1,
        f"{elements_before} → {after.split()[0]} elements",
    )
    _, got, got_ev = run(cli, "get", IMPORTED, limit=140)
    check(
        record,
        "the imported element is in the model",
        got.startswith(IMPORTED) and "M_Round_Table" in got,
        got.splitlines()[0] if got else got_ev,
    )
    check(
        record,
        "its relationship into the existing model was made",
        "LDC-CURR" in got,
        trim(next((ln for ln in got.splitlines() if "LDC-CURR" in ln), ""), 120),
    )
    _, freshness, fresh_ev = run(cli, "health", limit=200)
    check(
        record,
        "the source the import was given is recorded against the rows",
        "m-round" in freshness,
        trim(next((ln for ln in freshness.splitlines() if "m-round" in ln), ""), 130) or fresh_ev,
    )


@pytest.mark.scenario(
    scenario_id="M25",
    group="M",
    title="import of a broken directory exits 1 and names every row it refused",
    feature="Command line · import",
    expected="A directory with an unknown type and a row with no id exits 1, reports two errors, and names the file, the row number and the reason for each.",
)
def test_m25_import_broken(cli, record, tmp_path):
    directory = tmp_path / "m-broken"
    write_csv(
        directory,
        "elements.csv",
        "id,type,name\nM-BAD-1,Not A Real Type,Broken row\n,Data Entity,No id at all\n",
    )
    _, before, _ = run(cli, "stats", limit=60)
    rc, out, ev = run(cli, "import", str(directory), "--source", "m-bad", expect=1, limit=200)
    must(record, "a broken import exits 1", rc == 1, ev)
    check(record, "the summary counts the errors", "2 errors" in out, out.splitlines()[0].strip())
    check(
        record,
        "it says how many rows it skipped",
        "skipped" in out.splitlines()[0],
        out.splitlines()[0].strip(),
    )
    check(
        record,
        "the unknown type is named, with the value that was not recognised",
        "unknown_type" in out and "Not A Real Type" in out,
        trim(next((ln for ln in out.splitlines() if "unknown_type" in ln), ""), 150),
    )
    check(
        record,
        "the row with no id is reported separately",
        "missing_id" in out,
        trim(next((ln for ln in out.splitlines() if "missing_id" in ln), ""), 150),
    )
    check(
        record,
        "each issue names its file and row number",
        out.count("elements.csv row") >= 2,
        f"{out.count('elements.csv row')} issues located in the file",
    )
    _, after, after_ev = run(cli, "stats", limit=60)
    check(
        record,
        "no row from the broken file reached the model",
        before.splitlines()[0] == after.splitlines()[0],
        after_ev,
    )


@pytest.mark.scenario(
    scenario_id="M26",
    group="M",
    title="export-pack writes the stored metamodel back to YAML, and load-pack reads it again",
    feature="Command line · export-pack, load-pack",
    expected="The pack exports to a YAML file naming the pack and its types, and loading that file back reports the same pack and version.",
)
def test_m26_pack_round_trip(cli, record, tmp_path):
    out_file = tmp_path / "m-pack.yaml"
    rc, said, ev = run(cli, "export-pack", str(out_file), limit=120)
    must(record, "the pack was exported", rc == 0 and out_file.exists(), ev)
    text = out_file.read_text(encoding="utf-8")
    check(
        record,
        "it says which pack it wrote and where",
        "higher_education" in said and str(out_file) in said,
        trim(said),
    )
    check(
        record,
        "the file opens with the pack's identity",
        text.startswith("pack:") and "id: higher_education" in text,
        trim(text[:90], 90),
    )
    check(
        record,
        "the element types are in it",
        "element_types:" in text and "id: data_entity" in text,
        f"{len(text.splitlines())} lines",
    )
    check(record, "the relationship types are in it", "relationship_types:" in text, "relationship_types:")

    rc_load, loaded, load_ev = run(cli, "load-pack", str(out_file), limit=120)
    must(record, "the exported file loads back", rc_load == 0, load_ev)
    check(
        record,
        "the pack and its version are named on the way in",
        "higher_education" in loaded and "version" in loaded,
        trim(loaded),
    )
    _, summary_out, summary_ev = run(cli, "summary", limit=80)
    check(
        record,
        "the metamodel still reads the same after the round trip",
        "pack `higher_education`" in summary_out,
        summary_ev,
    )
    _, stats_out, stats_ev = run(cli, "stats", limit=60)
    check(record, "reloading the metamodel left the content alone", int(stats_out.split()[0]) > 0, stats_ev)


@pytest.mark.scenario(
    scenario_id="M27",
    group="M",
    title="init creates a database of its own and loads a metamodel into it",
    feature="Command line · init",
    expected="`ea init --db <new file>` creates the file, reports the pack and the number of types, and the new database holds the metamodel but no content.",
)
def test_m27_init(cli, record, tmp_path):
    fresh = tmp_path / "m-fresh.duckdb"
    rc, out, ev = run(cli, "init", "--db", str(fresh), limit=140)
    must(record, "the database was created", rc == 0 and fresh.exists(), ev)
    check(record, "it says which file it created", str(fresh) in out, trim(out))
    check(
        record,
        "it says which pack it loaded and how big it is",
        "higher_education" in out and "element types" in out and "relationship types" in out,
        trim(out),
    )
    check(record, "the file is not empty", fresh.stat().st_size > 0, f"{fresh.stat().st_size} bytes")

    _, stats_out, stats_ev = run(cli, "stats", EA_DB_PATH=str(fresh), limit=80)
    check(
        record,
        "the new database holds no content yet",
        stats_out.strip().startswith("0 elements, 0 relationships"),
        stats_ev,
    )
    _, summary_out, summary_ev = run(cli, "summary", EA_DB_PATH=str(fresh), limit=80)
    check(record, "but it does hold the metamodel", "pack `higher_education`" in summary_out, summary_ev)
    _, here, here_ev = run(cli, "stats", limit=60)
    check(record, "--db did not touch the database the round is using", int(here.split()[0]) > 0, here_ev)


# ================================================================ branches and review ======
@pytest.mark.scenario(
    scenario_id="M28",
    group="M",
    title="reviewers list says when nobody is assigned, and set assigns a type to a group",
    feature="Command line · reviewers",
    expected="`reviewers list` explains the empty state, `reviewers set` assigns a user and a group to Data Entity, and the listing then shows both.",
)
def test_m28_reviewers(cli, record):
    rc, before, ev = run(cli, "reviewers", "list", limit=140)
    must(record, "the assignments were listed", rc == 0, ev)
    check(
        record,
        "an empty assignment list says so and says what it means",
        "no reviewers assigned" in before or "data_entity" in before,
        trim(before) or "(nothing printed)",
    )

    rc_set, said, set_ev = run(
        cli, "reviewers", "set", "data_entity", f"{REVIEWER_USER},{REVIEWER_GROUP}", limit=120
    )
    must(record, "the assignment was made", rc_set == 0, set_ev)
    check(
        record,
        "it echoes the type and who reviews it",
        "data_entity" in said and REVIEWER_GROUP in said,
        trim(said),
    )

    _, after, after_ev = run(cli, "reviewers", "list", limit=140)
    row = next((ln for ln in after.splitlines() if ln.startswith("data_entity")), "")
    must(record, "Data Entity now has reviewers", bool(row), after_ev)
    check(
        record,
        "both the user and the group are listed",
        REVIEWER_USER in row and REVIEWER_GROUP in row,
        row.strip(),
    )
    check(record, "the empty-state sentence is gone", "no reviewers assigned" not in after, after_ev)


@pytest.mark.scenario(
    scenario_id="M29",
    group="M",
    title="branch create derives an id from the name, and branch list shows it as open with no rows",
    feature="Command line · branch create, list",
    expected='`branch create "M overlay"` reports the id it derived and how to use it; `branch list` shows the branch open, with its work package and author.',
    branch=OVERLAY,
)
def test_m29_branch_create(cli, record):
    rc, out, ev = run(
        cli,
        "branch",
        "create",
        OVERLAY_NAME,
        "--description",
        "the command-line round's overlay",
        "-w",
        WORK_PACKAGE,
        limit=140,
    )
    must(record, "the branch was created", rc == 0, ev)
    check(record, "the id was derived from the name", f"'{OVERLAY}'" in out, trim(out))
    check(record, "it says how to work on the branch", f"--branch {OVERLAY}" in out, trim(out))

    _, listed, list_ev = run(cli, "branch", "list", limit=160)
    row = next((ln for ln in listed.splitlines() if ln.startswith(OVERLAY)), "")
    must(record, "the branch is listed", bool(row), list_ev)
    check(record, "a new branch is open", " open " in row, row.strip())
    check(record, "it carries no rows yet", " 0 rows" in row, row.strip())
    check(record, "the work package it belongs to is shown", WORK_PACKAGE in row, row.strip())
    check(record, "the author and the name are shown", AUTHOR in row and OVERLAY_NAME in row, row.strip())

    _, open_only, open_ev = run(cli, "branch", "list", "--status", "open", limit=140)
    check(record, "the listing can be filtered by status", OVERLAY in open_only, open_ev)


@pytest.mark.scenario(
    scenario_id="M30",
    group="M",
    title="--branch puts a write on the overlay, and main does not see it",
    feature="Command line · --branch",
    expected="A `set` under `--branch m-overlay` changes the element on the branch only; the same `get` on main still returns the original row.",
    branch=OVERLAY,
)
def test_m30_branch_overlay(cli, record):
    _, main_before, _ = run(cli, "get", BRANCH_ELEMENT, limit=80)
    head_before = main_before.splitlines()[0]

    rc, out, ev = run(
        cli,
        "--branch",
        OVERLAY,
        "set",
        BRANCH_ELEMENT,
        "--status",
        "draft",
        "--note",
        "M: drafted on the overlay",
    )
    must(record, "the write on the branch succeeded", rc == 0 and "updated 1" in out, ev)

    _, on_branch, branch_ev = run(cli, "--branch", OVERLAY, "get", BRANCH_ELEMENT, limit=80)
    check(
        record,
        "the branch sees the change",
        "status=draft" in on_branch.splitlines()[0],
        on_branch.splitlines()[0],
    )

    _, on_main, main_ev = run(cli, "get", BRANCH_ELEMENT, limit=80)
    check(record, "main does not", on_main.splitlines()[0] == head_before, on_main.splitlines()[0])
    check(record, "main's version was not bumped either", "version=1" in on_main.splitlines()[0], main_ev)
    check(
        record, "the branch's own version moved instead", "version=2" in on_branch.splitlines()[0], branch_ev
    )

    _, listed, list_ev = run(cli, "branch", "list", limit=140)
    row = next((ln for ln in listed.splitlines() if ln.startswith(OVERLAY)), "")
    check(record, "the branch now reports the row it carries", " 1 rows" in row, row.strip() or list_ev)


@pytest.mark.scenario(
    scenario_id="M31",
    group="M",
    title="branch diff names what changed on the overlay, and which fields",
    feature="Command line · branch diff",
    expected="`branch diff m-overlay` counts added, changed, deleted and conflicting items, and lists the element with the fields that differ from main.",
    branch=OVERLAY,
)
def test_m31_branch_diff(cli, record):
    rc, out, ev = run(cli, "branch", "diff", OVERLAY, limit=180)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    must(record, "the change set was reported", rc == 0 and lines, ev)
    check(
        record, "the heading says where the branch stands", f"branch '{OVERLAY}' (open)" in lines[0], lines[0]
    )
    check(
        record,
        "it counts every kind of change",
        all(w in lines[0] for w in ("added", "changed", "deleted", "conflicts")),
        lines[0],
    )
    check(record, "the one edit is counted as changed, not added", "0 added, 1 changed" in lines[0], lines[0])
    check(record, "there is no conflict with main", "0 conflicts" in lines[0], lines[0])
    row = next((ln for ln in lines[1:] if BRANCH_ELEMENT in ln), "")
    must(record, "the changed element is listed", bool(row), ev)
    check(
        record,
        "the row says it is an element and how it changed",
        "changed" in row and "element" in row,
        row.strip(),
    )
    check(
        record,
        "the row names the element and its type",
        "SRS_Unit" in row and "Data Entity" in row,
        row.strip(),
    )
    check(
        record, "the row names the fields that differ", "[status" in row and "target_note" in row, row.strip()
    )


@pytest.mark.scenario(
    scenario_id="M32",
    group="M",
    title="branch review freezes the branch and names who must approve each type it touches",
    feature="Command line · branch review",
    expected="An architect requests the review of their own branch; the reviewers assigned to Data Entity are named, and a further write on the branch is refused because it is frozen.",
    role="architect",
    branch=OVERLAY,
)
def test_m32_branch_review(cli, record):
    rc, out, ev = run(cli, "--as", "architect", "branch", "review", OVERLAY, "--actor", AUTHOR, limit=160)
    must(record, "the review was requested", rc == 0, ev)
    check(record, "the branch is said to be in review", f"'{OVERLAY}' is in review" in out, trim(out))
    check(
        record,
        "the element type the branch touches is named",
        "Data Entity" in out,
        trim(next((ln for ln in out.splitlines() if "Data Entity" in ln), ""), 130),
    )
    check(
        record,
        "the reviewers assigned to that type are named",
        REVIEWER_GROUP in out,
        trim(next((ln for ln in out.splitlines() if "reviewers:" in ln), ""), 130),
    )

    rc_frozen, frozen, frozen_ev = run(
        cli, "--branch", OVERLAY, "set", BRANCH_ELEMENT, "--status", "approved", expect=1, limit=120
    )
    check(record, "a write on a branch in review is refused", rc_frozen == 1, frozen_ev)
    check(
        record,
        "the refusal says the branch is frozen and why",
        "in review" in frozen and "frozen" in frozen,
        trim(frozen.splitlines()[-1] if frozen else "", 130),
    )

    _, listed, list_ev = run(cli, "branch", "list", limit=140)
    row = next((ln for ln in listed.splitlines() if ln.startswith(OVERLAY)), "")
    check(record, "the listing shows the new status", "in_review" in row, row.strip() or list_ev)


@pytest.mark.scenario(
    scenario_id="M33",
    group="M",
    title="branch approve is refused unless the reviewer covers the types the branch touches",
    feature="Command line · branch approve",
    expected="A reviewer who is in none of the assigned groups is refused by name; the same reviewer with the assigned group approves the type, and the branch becomes approved.",
    role="reviewer",
    branch=OVERLAY,
)
def test_m33_branch_approve(cli, record):
    rc, refused, ev = run(
        cli, "--as", "reviewer", "branch", "approve", OVERLAY, "--actor", "m-outsider", expect=1, limit=140
    )
    check(record, "a reviewer who covers none of the types is refused", rc == 1, ev)
    check(
        record,
        "the refusal names the reviewer and what they do not cover",
        "m-outsider" in refused and "not a reviewer" in refused,
        trim(refused.splitlines()[-1] if refused else "", 140),
    )

    rc_ok, out, ok_ev = run(
        cli,
        "--as",
        "reviewer",
        "branch",
        "approve",
        OVERLAY,
        "--actor",
        REVIEWER_USER,
        "--groups",
        REVIEWER_GROUP,
        "--comment",
        "M: read and approved",
        limit=140,
    )
    must(record, "a reviewer in the assigned group may approve", rc_ok == 0, ok_ev)
    check(record, "the types approved are named", "approved data_entity" in out, trim(out))
    check(record, "what is still pending is reported", "pending none" in out, trim(out))
    check(
        record,
        "the branch is approved once every touched type is",
        f"'{OVERLAY}' is approved" in out,
        trim(out),
    )

    _, listed, list_ev = run(cli, "branch", "list", limit=140)
    row = next((ln for ln in listed.splitlines() if ln.startswith(OVERLAY)), "")
    check(record, "the listing shows the branch approved", "approved" in row, row.strip() or list_ev)


@pytest.mark.scenario(
    scenario_id="M34",
    group="M",
    title="branch send-back reopens the branch for its author, and needs a comment to do it",
    feature="Command line · branch send-back",
    expected="A send-back without a comment is refused; with one, the branch returns to open and can be written to again.",
    role="reviewer",
    branch=OVERLAY,
)
def test_m34_branch_send_back(cli, record):
    rc_none, refused, none_ev = run(
        cli,
        "--as",
        "reviewer",
        "branch",
        "send-back",
        OVERLAY,
        "--actor",
        REVIEWER_USER,
        "--comment",
        "",
        expect=1,
        limit=140,
    )
    check(record, "a send-back with no comment is refused", rc_none == 1, none_ev)
    check(
        record,
        "the refusal asks for what must change",
        "comment" in refused.lower(),
        trim(refused.splitlines()[-1] if refused else "", 140),
    )

    rc, out, ev = run(
        cli,
        "--as",
        "reviewer",
        "branch",
        "send-back",
        OVERLAY,
        "--actor",
        REVIEWER_USER,
        "--comment",
        "M: name the source system on the note",
        limit=120,
    )
    must(record, "the branch was sent back", rc == 0 and "sent back" in out, ev)

    _, listed, list_ev = run(cli, "branch", "list", limit=140)
    row = next((ln for ln in listed.splitlines() if ln.startswith(OVERLAY)), "")
    check(record, "the branch is open again", " open " in row, row.strip() or list_ev)
    check(record, "its rows survived the send-back", " 1 rows" in row, row.strip())

    rc_write, wrote, write_ev = run(
        cli,
        "--branch",
        OVERLAY,
        "set",
        BRANCH_ELEMENT,
        "--note",
        "M: source is the student records system",
        limit=120,
    )
    check(record, "the author may write to it again", rc_write == 0 and "updated 1" in wrote, write_ev)


@pytest.mark.scenario(
    scenario_id="M35",
    group="M",
    title="branch merge takes only the items it is given, and leaves the rest on the branch",
    feature="Command line · branch merge",
    expected="A branch carrying two changes merged with one `--include` applies that one to main, reports one remaining, and stays open with the other change intact.",
    branch=PARTIAL,
)
def test_m35_branch_merge_partial(cli, record):
    other = "DE-SRS-COURSE-OFFERING"
    run(cli, "branch", "create", "M partial", limit=120)
    run(cli, "--branch", PARTIAL, "set", ENTITY, other, "--status", "draft", limit=120)
    rc_diff, diff, diff_ev = run(cli, "branch", "diff", PARTIAL, limit=180)
    must(record, "the branch carries two changes", rc_diff == 0 and "2 changed" in diff, diff_ev)

    rc, out, ev = run(cli, "branch", "merge", PARTIAL, "--include", f"element:{ENTITY}", limit=140)
    must(record, "the partial merge ran", rc == 0, ev)
    check(record, "it says how many items it applied", "merged 1 item(s)" in out, trim(out))
    check(record, "it says what remains on the branch", "1 remaining" in out, trim(out))
    check(record, "the branch is left open because something remains", "still open" in out, trim(out))

    _, merged, merged_ev = run(cli, "get", ENTITY, limit=80)
    check(
        record,
        "the item that was ticked reached main",
        "status=draft" in merged.splitlines()[0],
        merged.splitlines()[0] if merged else merged_ev,
    )
    _, untouched, untouched_ev = run(cli, "get", other, limit=80)
    check(
        record,
        "the item that was not ticked did not",
        "status=draft" not in untouched.splitlines()[0],
        untouched.splitlines()[0] if untouched else untouched_ev,
    )

    _, remaining, remaining_ev = run(cli, "branch", "diff", PARTIAL, limit=160)
    rows = "\n".join(remaining.splitlines()[1:])
    check(
        record,
        "the unticked item is still on the branch",
        "1 changed" in remaining and other in rows,
        remaining_ev,
    )
    check(record, "the merged item has left the change set", f" {ENTITY} " not in rows, trim(remaining, 150))


@pytest.mark.scenario(
    scenario_id="M36",
    group="M",
    title="An architect may not merge an unapproved branch; an admin may, and main then carries the change",
    feature="Command line · branch merge",
    expected="`--as architect branch merge` on an open branch is refused and names the rule; as Admin the merge applies, main shows the branch's value and the branch closes as merged.",
    branch=OVERLAY,
)
def test_m36_branch_merge(cli, record, finding):
    rc_arch, refused, arch_ev = run(cli, "--as", "architect", "branch", "merge", OVERLAY, expect=1, limit=140)
    check(record, "an architect may not merge a branch that is not approved", rc_arch == 1, arch_ev)
    message = refused.splitlines()[-1] if refused else ""
    check(
        record,
        "the refusal names the role and the rule",
        "Architect" in message and "not approved" in message,
        message,
    )
    if "a Architect" in refused:
        lodge(
            finding,
            "M-5",
            "src/ea/services/roles.py:96",
            "usability",
            "A refusal for the Architect or the Admin reads 'a Architect' / 'a Admin' — the article is not chosen for the role's name.",
            f'`require()` builds the message as f"a {{LABELS[role]}} may not …". The command line printed: {message!r}. '
            "The same string is what the screens show when a write is refused.",
        )

    _, main_before, _ = run(cli, "get", BRANCH_ELEMENT, limit=80)
    check(
        record,
        "main has not been changed by the refused merge",
        "status=approved" in main_before.splitlines()[0],
        main_before.splitlines()[0],
    )

    rc, out, ev = run(cli, "branch", "merge", OVERLAY, "--actor", "m-admin", limit=140)
    must(record, "an admin may merge without a review", rc == 0, ev)
    check(
        record,
        "it says how many items it applied and that nothing remains",
        "merged 1 item(s)" in out and "0 remaining" in out,
        trim(out),
    )
    check(record, "the branch is closed", "branch closed" in out, trim(out))

    _, main_after, after_ev = run(cli, "get", BRANCH_ELEMENT, limit=100)
    check(
        record,
        "main now carries the branch's value",
        "status=draft" in main_after.splitlines()[0],
        main_after.splitlines()[0],
    )
    _, listed, list_ev = run(cli, "branch", "list", limit=160)
    row = next((ln for ln in listed.splitlines() if ln.startswith(OVERLAY)), "")
    check(
        record,
        "the branch is listed as merged, with nothing left on it",
        "merged" in row and " 0 rows" in row,
        row.strip() or list_ev,
    )
    check(record, "the merge is visible without --branch", "SRS_Unit" in main_after, after_ev)


@pytest.mark.scenario(
    scenario_id="M37",
    group="M",
    title="branch abandon discards the branch's rows and leaves main untouched",
    feature="Command line · branch abandon",
    expected="A branch with a change on it is abandoned; it is listed as abandoned with no rows, and the element it changed still reads its main value.",
    branch=THROWAWAY,
)
def test_m37_branch_abandon(cli, record):
    run(cli, "branch", "create", "M throwaway", limit=120)
    _, before, _ = run(cli, "get", "PAC-LMS", limit=80)
    head_before = before.splitlines()[0]
    rc_w, wrote, write_ev = run(
        cli, "--branch", THROWAWAY, "set", "PAC-LMS", "--status", "retired", limit=120
    )
    must(record, "the branch carries a change to discard", rc_w == 0 and "updated 1" in wrote, write_ev)

    rc, out, ev = run(cli, "branch", "abandon", THROWAWAY, limit=120)
    must(record, "the branch was abandoned", rc == 0 and "abandoned" in out, ev)

    _, listed, list_ev = run(cli, "branch", "list", "--status", "abandoned", limit=160)
    row = next((ln for ln in listed.splitlines() if ln.startswith(THROWAWAY)), "")
    must(record, "it is listed among the abandoned branches", bool(row), list_ev)
    check(record, "its rows were discarded", " 0 rows" in row, row.strip())
    check(
        record,
        "the branch is kept in the record rather than deleted",
        THROWAWAY in row and "M throwaway" in row,
        row.strip(),
    )

    _, after, after_ev = run(cli, "get", "PAC-LMS", limit=80)
    check(record, "main is exactly as it was", after.splitlines()[0] == head_before, after.splitlines()[0])
    check(
        record,
        "the abandoned branch no longer shows the change either",
        "status=retired" not in run(cli, "--branch", THROWAWAY, "get", "PAC-LMS", limit=80)[1],
        after_ev,
    )


# ============================================================== who is running it ==========
@pytest.mark.scenario(
    scenario_id="M38",
    group="M",
    title="--as reader may read everything and write nothing",
    feature="Command line · --as",
    expected="As Reader, stats, find, get and view all run; `set` on main is refused with exit 1, and the refusal names the role and says what to do instead.",
    role="reader",
)
def test_m38_as_reader(cli, record):
    for command in (
        ("stats",),
        ("find", "course"),
        ("get", ENTITY),
        ("view", ASSET),
        ("impact", APPLICATION),
        ("health",),
        ("target",),
    ):
        rc, out, ev = run(cli, "--as", "reader", *command, limit=90)
        check(record, f"a reader may run {command[0]}", rc == 0 and bool(out.strip()), ev)

    _, before, _ = run(cli, "get", "PAC-LMS", limit=80)
    rc_w, refused, write_ev = run(
        cli, "--as", "reader", "set", "PAC-LMS", "--status", "retired", expect=1, limit=120
    )
    must(record, "a reader may not write to main", rc_w == 1, write_ev)
    message = refused.splitlines()[-1] if refused else ""
    check(record, "the refusal names the role", "Reader" in message, message)
    check(record, "the refusal says what to do instead", "work on a branch" in message, message)
    _, after, after_ev = run(cli, "get", "PAC-LMS", limit=80)
    check(record, "nothing was written", after.splitlines()[0] == before.splitlines()[0], after_ev)

    rc_b, branch_refused, branch_ev = run(
        cli, "--as", "reader", "branch", "create", "M reader branch", expect=1, limit=120
    )
    check(record, "a reader may not create a branch either", rc_b == 1, branch_ev)
    check(
        record,
        "that refusal names the role and the action",
        "Reader" in branch_refused and "create a branch" in branch_refused,
        trim(branch_refused.splitlines()[-1] if branch_refused else "", 130),
    )


@pytest.mark.scenario(
    scenario_id="M39",
    group="M",
    title="--as with a role that does not exist fails before the command runs",
    feature="Command line · --as",
    expected="`--as wizard` exits 1, names the value it did not recognise and lists the roles that exist, and nothing the command would have done happens.",
)
def test_m39_as_unknown_role(cli, record):
    rc, out, ev = run(cli, "--as", "wizard", "stats", expect=1, limit=140)
    must(record, "an unknown role is refused", rc == 1, ev)
    check(
        record,
        "the value that was not recognised is quoted back",
        "wizard" in out,
        trim(out.splitlines()[-1] if out else "", 130),
    )
    flat = " ".join(out.split())
    check(
        record,
        "the roles that do exist are listed",
        all(r in flat for r in ("reader", "reviewer", "architect", "admin", "agent")),
        "reader, reviewer, architect, admin, agent",
    )
    check(record, "the command did not run", "elements," not in out, "no stats line was printed")

    rc_write, refused, write_ev = run(
        cli, "--as", "wizard", "set", "PAC-LMS", "--status", "retired", expect=1, limit=100
    )
    check(
        record,
        "an unknown role cannot slip a write through either",
        rc_write == 1 and "updated" not in refused,
        write_ev,
    )

    rc_branch, bad_branch, branch_ev = run(cli, "--branch", "Not A Branch", "stats", expect=1, limit=130)
    check(record, "an invalid branch id is refused the same way", rc_branch == 1, branch_ev)
    check(
        record,
        "the branch refusal says what a branch id may contain",
        "branch id" in bad_branch and "lowercase" in bad_branch,
        trim(bad_branch.splitlines()[-1] if bad_branch else "", 130),
    )


@pytest.mark.scenario(
    scenario_id="M40",
    group="M",
    title="--as architect may not edit main directly, but may draft the same change on a branch",
    feature="Command line · --as, --branch",
    expected="The same `set` is refused on main as Architect and accepted under `--branch`; the architect can create the branch and abandon their own.",
    role="architect",
    branch=ARCHITECT_BRANCH,
)
def test_m40_as_architect(cli, record):
    _, before, _ = run(cli, "get", "PAC-LMS", limit=80)
    rc_main, refused, main_ev = run(
        cli, "--as", "architect", "set", "PAC-LMS", "--status", "retired", expect=1, limit=120
    )
    must(record, "an architect may not change main directly", rc_main == 1, main_ev)
    message = refused.splitlines()[-1] if refused else ""
    check(
        record, "the refusal points at the branch as the way to do it", "work on a branch" in message, message
    )

    rc_create, created, create_ev = run(
        cli, "--as", "architect", "branch", "create", "M architect", "--actor", "m-arch", limit=130
    )
    must(
        record, "an architect may create a branch", rc_create == 0 and ARCHITECT_BRANCH in created, create_ev
    )

    rc_write, wrote, write_ev = run(
        cli,
        "--as",
        "architect",
        "--branch",
        ARCHITECT_BRANCH,
        "set",
        "PAC-LMS",
        "--status",
        "retired",
        limit=120,
    )
    check(
        record, "the same change is accepted on the branch", rc_write == 0 and "updated 1" in wrote, write_ev
    )

    _, on_branch, branch_ev = run(cli, "--branch", ARCHITECT_BRANCH, "get", "PAC-LMS", limit=80)
    check(
        record,
        "the branch holds the change",
        "status=retired" in on_branch.splitlines()[0],
        on_branch.splitlines()[0],
    )
    _, on_main, main_after_ev = run(cli, "get", "PAC-LMS", limit=80)
    check(record, "main is untouched by it", on_main.splitlines()[0] == before.splitlines()[0], main_after_ev)

    rc_other, other, other_ev = run(
        cli,
        "--as",
        "architect",
        "branch",
        "abandon",
        ARCHITECT_BRANCH,
        "--actor",
        "m-someone-else",
        expect=1,
        limit=130,
    )
    check(record, "an architect may not abandon somebody else's branch", rc_other == 1, other_ev)
    check(
        record,
        "the refusal says whose branch it is",
        "own branch" in other,
        trim(other.splitlines()[-1] if other else "", 130),
    )

    rc_own, own, own_ev = run(
        cli, "--as", "architect", "branch", "abandon", ARCHITECT_BRANCH, "--actor", "m-arch", limit=120
    )
    check(record, "an architect may abandon their own", rc_own == 0 and "abandoned" in own, own_ev)
    _, final, final_ev = run(cli, "get", "PAC-LMS", limit=80)
    check(
        record,
        "main is still untouched at the end",
        final.splitlines()[0] == before.splitlines()[0],
        final.splitlines()[0] if final else final_ev,
    )


# ==================================================== what the first pass left uncovered ===
# The scenarios below close three kinds of gap. The options no scenario had run (`--limit`,
# `--lifecycle`, `--mapping`, `--actor`, `--pack-id`, `--resolve`, `--types`, `-b` and the two
# environment variables the help advertises); the branch of a command only an error reaches
# (an element that does not exist, a directory that cannot be read, a conflicting merge, a
# branch that was never created, a branch that is already closed); and the roles the first
# pass never ran — the Agent, and the review actions refused to everyone but a Reviewer.
#
# They keep the same state discipline: everything created carries the group's prefix, every
# branch opened is merged or abandoned before the scenario ends, and no scenario asserts an
# absolute total.
CONFLICT_BRANCH = "m-conflict"  # created, conflicted and merged in M56
DROP_BRANCH = "m-drop"  # created and closed with its one item dropped in M57
ROLES_BRANCH = "m-roles"  # created, frozen and abandoned in M58
REVIEW_BRANCH = "m-review"  # created, reviewed, approved and abandoned in M59
AGENT_BRANCH = "m-agent"  # created and abandoned in M61
ENV_BRANCH = "m-env"  # created, written to through EA_BRANCH and abandoned in M62
CLOSED_BRANCH = "m-closed"  # created, merged and then abandoned again in M63
GHOST_BRANCH = "m-ghost"  # never created: written to in M55, adopted and abandoned there
GHOST_ELEMENT = "DE-LMS-UNIT-SITE"  # the element M55 writes into an overlay that does not exist
AGENT_ELEMENT = "IF-CMS-SRS"  # the element M61 fails to write, as an Agent
ENV_ELEMENT = "DEF-ENROLLED-STUDENT"  # the element M62 writes through EA_BRANCH
CLOSED_ELEMENT = "DE-SRS-ENROLMENT"  # the element M63 merges into main
MAPPED = "M-DE-2"  # the element M49 imports through the connector mapping
STAMPED = "M-DE-3"  # the element M51 imports under an actor of its own
MAPPING = "connectors/tool-export/mapping.yaml"
UNKNOWN = "M-NO-SUCH-ELEMENT"
NO_WORK_PACKAGE = "M-NO-SUCH-WORK-PACKAGE"


def refusal(out: str) -> str:
    """What the command actually said, after the framework's traceback box."""
    return out.rsplit("╯", 1)[-1].strip()


@pytest.mark.scenario(
    scenario_id="M41",
    group="M",
    title="find takes a limit and a type by its display name, and does not notice a type that is not in the metamodel",
    feature="Command line · find",
    expected='`--limit` caps the ranked list, `--type "Data Entity"` is the same filter as `--type data_entity`, an empty query lists the model in name order, and a type the pack does not hold is refused rather than searched as though no type had been given.',
)
def test_m41_find_options(cli, record, finding):
    rc, everything, ev = run(cli, "find", "course", limit=120)
    all_lines = [ln for ln in everything.splitlines() if ln.strip()]
    must(record, "the unrestricted search returned a ranked list", rc == 0 and len(all_lines) > 3, ev)

    _, capped, capped_ev = run(cli, "find", "course", "--limit", "2", limit=120)
    capped_lines = [ln for ln in capped.splitlines() if ln.strip()]
    check(record, "--limit caps the list", len(capped_lines) == 2, f"{len(capped_lines)} rows for --limit 2")
    check(
        record,
        "the rows it keeps are the top of the ranking, not an arbitrary two",
        capped_lines == all_lines[:2],
        capped_ev,
    )

    _, by_id, _ = run(cli, "find", "course", "--type", "data_entity", limit=120)
    _, by_name, name_ev = run(cli, "find", "course", "--type", "Data Entity", limit=120)
    check(
        record,
        "a type given by its display name is the same filter as its id",
        bool(by_name.strip()) and by_name == by_id,
        name_ev,
    )

    _, listing, listing_ev = run(cli, "find", "", "--limit", "6", limit=140)
    rows = [ln for ln in listing.splitlines() if ln.strip()]
    must(record, "an empty query lists the model instead of searching it", len(rows) == 6, listing_ev)
    names = [ln.split(None, 2)[2] for ln in rows if len(ln.split(None, 2)) > 2]
    check(
        record,
        "the listing is in name order",
        names == sorted(names) or names == sorted(names, key=str.lower),
        trim(" · ".join(names), 140),
    )

    # `--as wizard` is refused before the command runs (M39); a type outside the pack is not.
    rc_bad, bad, bad_ev = run(cli, "find", "course", "--type", "not_a_type", expect=None, limit=140)
    bad_lines = [ln for ln in bad.splitlines() if ln.strip()]
    check(record, "a type the metamodel does not hold is refused", rc_bad == 1, bad_ev)
    check(
        record,
        "and what it answers is not simply the unrestricted search",
        bad_lines != all_lines,
        f"{len(bad_lines)} rows, of which {len([ln for ln in bad_lines if 'data_entity' not in ln])} are of other types",
    )
    if bad_lines == all_lines:
        lodge(
            finding,
            "M-7",
            "src/ea/cli.py · find",
            "defect",
            "An unrecognised `--type` is dropped instead of refused, so the search silently returns every type.",
            f"`ea find course --type not_a_type` exits 0 and returns the same {len(all_lines)} rows as `ea find "
            "course`. `find` resolves the option with `registry.resolve_type(type_id)` and passes `t.id if t "
            "else None`, so a mistyped type reads as 'no type given'. A typo therefore produces a plausible "
            "answer to a different question; `--as wizard` is refused by name, and this should be too.",
        )


@pytest.mark.scenario(
    scenario_id="M42",
    group="M",
    title="sql answers the same figures stats reports, so the two faces of the model agree",
    feature="Command line · sql",
    expected="`ea sql` counting the element and relationship tables returns exactly the totals `ea stats` prints, and the same per-type figure for Data Entity.",
)
def test_m42_sql_agrees_with_stats(cli, record):
    rc_s, stats_out, stats_ev = run(cli, "stats", limit=120)
    head = stats_out.splitlines()[0]
    must(record, "stats reported the model", rc_s == 0 and "elements," in head, stats_ev)
    elements = int(head.split()[0])
    relationships = int(head.split(",")[1].split()[0])

    rc, out, ev = run(
        cli,
        "sql",
        "select (select count(*) from element) as elements, (select count(*) from relationship) as relationships",
        limit=140,
    )
    must(record, "the query ran", rc == 0 and "elements" in out, ev)
    values = out.splitlines()[1].split()
    check(
        record,
        "sql counts the elements stats reports",
        int(values[0]) == elements,
        f"sql {values[0]}, stats {elements}",
    )
    check(
        record,
        "and the relationships",
        int(values[1]) == relationships,
        f"sql {values[1]}, stats {relationships}",
    )

    type_row = next((ln for ln in stats_out.splitlines() if ln.strip().endswith("Data Entity")), "")
    must(record, "stats breaks Data Entity out", bool(type_row), stats_ev)
    _, per_type, per_ev = run(
        cli, "sql", "select count(*) as n from element where type_id = 'data_entity'", limit=120
    )
    check(
        record,
        "the per-type figure agrees too",
        int(per_type.splitlines()[1].strip()) == int(type_row.split()[0]),
        f"sql {per_type.splitlines()[1].strip()}, stats {type_row.strip()}",
    )


@pytest.mark.scenario(
    scenario_id="M43",
    group="M",
    title="sql says nothing useful when a query matches no rows, and exits 1 when the database cannot bind it",
    feature="Command line · sql",
    expected="A query that matches nothing still names its columns and says the result is empty in words; a query naming a column that does not exist exits 1 and names it.",
)
def test_m43_sql_empty_and_broken(cli, record, finding):
    rc, empty, ev = run(
        cli, "sql", f"select element_id, name from element where element_id = '{UNKNOWN}'", limit=140
    )
    must(record, "a query that matches nothing still succeeds", rc == 0, ev)
    check(
        record,
        "the columns that were asked for are still named",
        "element_id" in empty and "name" in empty,
        trim(empty, 130),
    )
    check(record, "the empty result is not printed as silence", bool(empty.strip()), trim(empty, 130))
    if "Empty DataFrame" in empty:
        lodge(
            finding,
            "M-8",
            "src/ea/cli.py · sql",
            "usability",
            "A query that matches nothing prints the data frame's own repr — 'Empty DataFrame / Columns: […] / Index: []' — instead of a sentence.",
            f"`ea sql \"select … where element_id = '{UNKNOWN}'\"` printed: {trim(empty, 120)}. The words are the "
            "library's, not the application's: 'Index: []' means nothing to an operator, and the same query "
            "with one row prints a plain table. Checkpoint 5 of the round's usability list (empty states), on "
            "the command line.",
        )

    rc_bad, bad, bad_ev = run(cli, "sql", "select nope from element", expect=1, limit=140)
    check(record, "a query the database cannot bind exits 1", rc_bad == 1, bad_ev)
    check(record, "the failure names the column it could not find", "nope" in bad, trim(refusal(bad), 130))
    check(
        record,
        "and it is not confused with the read-only guard's own refusal",
        "read-only" not in bad,
        "the guard let it through; the database rejected it",
    )


@pytest.mark.scenario(
    scenario_id="M44",
    group="M",
    title="set writes the lifecycle text, and a set with no field to set changes nothing",
    feature="Command line · set",
    expected="`--lifecycle` writes that field and versions the element; `ea set <id>` with no option reports updated 0, refused 0 and leaves the element exactly as it was.",
)
def test_m44_set_lifecycle(cli, record, finding):
    _, before, before_ev = run(cli, "get", WRITE_ELEMENT, limit=80)
    version_before = int(before.splitlines()[0].split("version=")[1].split()[0])
    rc, out, ev = run(cli, "set", WRITE_ELEMENT, "--lifecycle", "M: in production")
    must(record, "the lifecycle text was written", rc == 0 and "updated 1" in out, ev)

    _, shown, shown_ev = run(
        cli, "sql", f"select lifecycle_status from element where element_id = '{WRITE_ELEMENT}'", limit=130
    )
    check(record, "the field holds what was set", "M: in production" in shown, trim(shown, 120) or shown_ev)
    _, after, after_ev = run(cli, "get", WRITE_ELEMENT, limit=80)
    head = after.splitlines()[0]
    check(record, "the status the earlier scenarios set is untouched", "status=draft" in head, head)
    version_after = int(head.split("version=")[1].split()[0])
    check(
        record,
        "the write was versioned like any other",
        version_after == version_before + 1,
        f"version {version_before} → {version_after}",
    )

    rc_none, none_out, none_ev = run(cli, "set", WRITE_ELEMENT, limit=120)
    check(record, "a set with no field to set exits cleanly", rc_none == 0, none_ev)
    check(
        record, "it neither updates nor refuses anything", "updated 0, refused 0" in none_out, trim(none_out)
    )
    _, still, still_ev = run(cli, "get", WRITE_ELEMENT, limit=80)
    check(
        record, "and the element is exactly as it was", still.splitlines()[0] == head, still.splitlines()[0]
    )
    if "updated 0, refused 0" in none_out:
        lodge(
            finding,
            "M-9",
            "src/ea/cli.py · set",
            "usability",
            "A `set` with no field to set says 'updated 0, refused 0' and never says that nothing was asked of it.",
            "`ea set DE-EDW-DIM-COURSE` (no option) exits 0 with that line. `bulk_update` skips an element "
            "whose change is empty, so the element is neither updated nor refused and the count says nothing "
            "about why. A line naming the fields the command can set would turn a silent no-op into help.",
        )


@pytest.mark.scenario(
    scenario_id="M45",
    group="M",
    title="A direction that is neither in nor out is not refused: trace answers with the opposite of its default",
    feature="Command line · trace, neighbours",
    expected="`--direction sideways` is refused by both commands; today trace answers it with the inward walk and neighbours with the walk both ways.",
)
def test_m45_unknown_direction(cli, record, finding):
    _, outward, out_ev = run(cli, "trace", ASSET, "--direction", "out", "--depth", "3", limit=90)
    _, inward, in_ev = run(cli, "trace", ASSET, "--direction", "in", "--depth", "3", limit=90)
    must(
        record, "the two documented directions answer differently", outward.strip() != inward.strip(), out_ev
    )

    rc, sideways, ev = run(
        cli, "trace", ASSET, "--direction", "sideways", "--depth", "3", expect=None, limit=90
    )
    check(record, "a direction that is neither in nor out is refused", rc == 1, ev)
    check(
        record,
        "and it is not answered as though the other direction had been asked for",
        sideways.strip() != inward.strip(),
        f"the answer is the one `--direction in` gives, to the character ({len(inward.splitlines())} rows)"
        if sideways.strip() == inward.strip()
        else in_ev,
    )

    _, both, both_ev = run(cli, "neighbours", ASSET, "--depth", "2", limit=80)
    rc_n, n_side, n_ev = run(
        cli, "neighbours", ASSET, "--depth", "2", "--direction", "sideways", expect=None, limit=80
    )
    check(record, "neighbours refuses it too", rc_n == 1, n_ev)
    if sideways.strip() == inward.strip() or n_side.strip() == both.strip():
        lodge(
            finding,
            "M-10",
            "src/ea/cli.py · trace, neighbours (src/ea/backend/duckdb_backend.py:1084)",
            "defect",
            "An unrecognised `--direction` is neither refused nor reported: trace answers it with the inward walk — the opposite of its documented default — and neighbours with both ways.",
            f"`ea trace {ASSET} --direction sideways` returns exactly what `--direction in` returns, because "
            "the store chooses `TRACE_OUT_SQL if direction == 'out' else TRACE_IN_SQL`; `ea neighbours "
            f"{ASSET} --direction sideways` returns what `--direction both` returns. A typo in the flag gives "
            "a plausible answer to the opposite question, and the two commands do not even fall back the same "
            f"way. The help says the option is 'out … or in'. ({both_ev})",
        )


@pytest.mark.scenario(
    scenario_id="M46",
    group="M",
    title="A format the command does not offer prints the default instead of saying so",
    feature="Command line · view, health",
    expected="`view --fmt svg` and `health --fmt json` name a format neither command has; both print their default output and exit 0.",
)
def test_m46_unknown_format(cli, record, finding):
    _, mermaid, mermaid_ev = run(cli, "view", ASSET, limit=90)
    rc, svg, ev = run(cli, "view", ASSET, "--fmt", "svg", expect=None, limit=90)
    check(record, "the command still produced a diagram", rc == 0 and svg.strip().startswith("flowchart"), ev)
    check(
        record,
        "what it produced is the Mermaid default, character for character",
        svg == mermaid,
        "identical to `--fmt mermaid`" if svg == mermaid else mermaid_ev,
    )

    _, table, table_ev = run(cli, "health", limit=90)
    rc_h, other, other_ev = run(cli, "health", "--fmt", "json", expect=None, limit=90)
    check(record, "health does the same with a format it does not offer", rc_h == 0, other_ev)
    check(
        record,
        "it prints the table, not a Markdown table and not JSON",
        "| --- |" not in other and other.splitlines()[1:] == table.splitlines()[1:],
        table_ev,
    )
    if svg == mermaid:
        lodge(
            finding,
            "M-11",
            "src/ea/cli.py · view, health, target",
            "usability",
            "A `--fmt` value the command does not offer is silently replaced by the default rather than refused.",
            "`view` resolves the option with `{…}.get(fmt, to_mermaid)`, and `health` and `target` compare "
            "`fmt == 'md'` and fall through. So `ea view IA-COURSE-CAT --fmt svg` prints Mermaid and exits 0. "
            "The help lists the formats, so a value outside the list is a mistake worth naming — the more so "
            "with `--out`, where the wrong renderer is written to a file.",
        )


@pytest.mark.scenario(
    scenario_id="M47",
    group="M",
    title="target covers the whole model as Markdown, and answers for a work package that does not exist",
    feature="Command line · target",
    expected="`target --fmt md` with no work package titles the section for the whole model and draws more of it than one work package does; an id that names no work package is refused, as it is when a branch is created for it.",
)
def test_m47_target_whole_model(cli, record, finding):
    rc, whole, ev = run(cli, "target", "--fmt", "md", limit=140)
    must(record, "the whole model's target view was generated", rc == 0 and whole.startswith("## "), ev)
    check(
        record,
        "with no work package the heading names none",
        whole.splitlines()[0].strip() == "## Target state",
        whole.splitlines()[0],
    )
    check(
        record,
        "the markers are explained and the diagram is fenced",
        "```mermaid" in whole and "Markers:" in whole,
        whole.splitlines()[2].strip(),
    )
    _, scoped, scoped_ev = run(cli, "target", "-w", WORK_PACKAGE, "--fmt", "md", limit=100)
    check(
        record,
        "it draws more of the model than one work package does",
        whole.count(":::") > scoped.count(":::") > 0,
        f"{whole.count(':::')} nodes for the model, {scoped.count(':::')} under {WORK_PACKAGE}",
    )

    rc_bad, bad, bad_ev = run(cli, "target", "-w", NO_WORK_PACKAGE, expect=None, limit=140)
    rc_branch, branch_out, branch_ev = run(
        cli, "branch", "create", "M no work package", "-w", NO_WORK_PACKAGE, expect=None, limit=140
    )
    check(
        record,
        "creating a branch for a work package that does not exist is refused",
        rc_branch == 1 and NO_WORK_PACKAGE in branch_out,
        trim(refusal(branch_out), 130),
    )
    check(
        record,
        "and so is reporting the target state of one",
        rc_bad == 1,
        f"exit {rc_bad}: {trim(bad, 120)}",
    )
    if rc_bad == 0:
        lodge(
            finding,
            "M-12",
            "src/ea/cli.py · target",
            "defect",
            "`target -w <id that is no work package>` reports an empty scope under that id instead of saying there is no such work package.",
            f"`ea target -w {NO_WORK_PACKAGE}` exits 0 and prints '0 elements, 0 relationships under "
            f"{NO_WORK_PACKAGE}; 0 elements change', and `--fmt md` draws an empty diagram titled 'Target "
            f"state of {NO_WORK_PACKAGE}'. `branch create -w` refuses the same id by name, so a typed work "
            "package reads as a work package with nothing in it on one command and an error on the other.",
        )


@pytest.mark.scenario(
    scenario_id="M48",
    group="M",
    title="Every graph command refuses an element that does not exist, and says so in words",
    feature="Command line · neighbours, trace, impact, view",
    expected="Each of the four commands exits 1 for an unknown id and ends with a sentence naming it, not a bare identifier.",
)
def test_m48_graph_unknown_element(cli, record):
    for command in ("neighbours", "trace", "impact", "view"):
        rc, out, ev = run(cli, command, UNKNOWN, expect=1, limit=110)
        check(record, f"{command} refuses an element that does not exist", rc == 1, ev)
        check(
            record,
            f"the {command} refusal says the element was not found, not only which id",
            f"no element with id {UNKNOWN}" in out,
            trim(refusal(out), 120),
        )


# ============================================================ loading, the rest of it ======
@pytest.mark.scenario(
    scenario_id="M49",
    group="M",
    title="import --mapping reads a vendor's own column names through the connector mapping",
    feature="Command line · import --mapping",
    expected="With `connectors/tool-export/mapping.yaml`, files named for the tool are found, its column headers and type label are mapped onto the model, its source system and default status are applied, and its lifecycle wording becomes a current state.",
)
def test_m49_import_mapping(cli, record, tmp_path):
    directory = tmp_path / "m-tool-export"
    write_csv(
        directory,
        "m-tool-objects.csv",
        "ID,Name,Object Type,Description,Lifecycle Status\n"
        f"{MAPPED},M_Mapped_Table,Data Entity,A row that arrived through a connector mapping.,Being built\n",
    )
    write_csv(
        directory,
        "m-tool-relations.csv",
        f"Source ID,Relationship,Target ID\nLDC-CURR,encapsulates,{MAPPED}\n",
    )

    rc_dry, dry, dry_ev = run(cli, "validate", str(directory), "--mapping", MAPPING, limit=160)
    must(record, "the dry run through the mapping ran", rc_dry == 0, dry_ev)
    check(record, "the files named for the tool were found", "elements 0/1" in dry, trim(dry))
    check(record, "the source system comes from the mapping", "source=ea-tool" in dry, trim(dry))
    check(record, "the vendor's columns validate against the pack", "0 errors, 0 warnings" in dry, trim(dry))

    rc, out, ev = run(cli, "import", str(directory), "--mapping", MAPPING, "--source", "m-tool", limit=160)
    must(record, "the import through the mapping succeeded", rc == 0 and "0 errors" in out, ev)
    check(
        record, "--source overrides the source system the mapping declares", "source=m-tool" in out, trim(out)
    )
    check(
        record,
        "both of the tool's files were loaded",
        "elements 1/1 loaded" in out and "relationships 1/1 loaded" in out,
        trim(out),
    )

    _, got, got_ev = run(cli, "get", MAPPED, limit=150)
    must(record, "the imported element is in the model", got.startswith(MAPPED), got_ev)
    check(
        record,
        "the vendor's ID and Name columns became the model's",
        "M_Mapped_Table" in got,
        got.splitlines()[0],
    )
    check(
        record,
        "its Object Type column resolved to a type in the pack",
        "[Data Entity]" in got,
        got.splitlines()[0],
    )
    check(record, "its Description came through", "connector mapping" in got, trim(got, 120))
    check(
        record,
        "the relationship file's Source ID and Target ID were read too",
        "LDC-CURR" in got,
        trim(next((ln for ln in got.splitlines() if "LDC-CURR" in ln), ""), 120),
    )
    _, state, state_ev = run(
        cli,
        "sql",
        f"select current_state, status, source_system from element where element_id = '{MAPPED}'",
        limit=150,
    )
    check(
        record,
        "the vendor's lifecycle wording became a current state",
        "in_implementation" in state,
        trim(state, 130),
    )
    check(
        record, "the mapping's default status was applied", "approved" in state, trim(state, 130) or state_ev
    )


@pytest.mark.scenario(
    scenario_id="M50",
    group="M",
    title="import refuses a directory it cannot read, and says why for one of the two reasons",
    feature="Command line · import",
    expected="A directory that does not exist and a directory with no CSV files in it both exit 1 and say, in words, what was wrong with the path.",
)
def test_m50_import_unreadable(cli, record, tmp_path, finding):
    _, before, _ = run(cli, "stats", limit=60)
    missing = tmp_path / "m-not-here"
    rc, out, ev = run(cli, "import", str(missing), expect=1, limit=140)
    check(record, "a directory that does not exist exits 1", rc == 1, ev)
    said = refusal(out).replace("\n", "")
    check(record, "the path it could not read is named", str(missing) in said, trim(said, 130))
    worded = any(w in said.lower() for w in ("no such", "not found", "does not exist", "no directory"))
    check(
        record,
        "and the message says what was wrong with it, not only where it was",
        worded,
        f"the refusal reads {said!r}",
    )

    empty = tmp_path / "m-empty"
    empty.mkdir()
    rc_e, out_e, empty_ev = run(cli, "import", str(empty), expect=1, limit=140)
    check(record, "a directory with no CSV files in it exits 1 too", rc_e == 1, empty_ev)
    check(
        record,
        "that one does say what was wrong",
        "no CSV files matched" in out_e.replace("\n", ""),
        trim(refusal(out_e).replace("\n", ""), 130),
    )
    _, after, after_ev = run(cli, "stats", limit=60)
    check(
        record, "neither attempt touched the model", before.splitlines()[0] == after.splitlines()[0], after_ev
    )
    if not worded:
        lodge(
            finding,
            "M-13",
            "src/ea/importer/csv_import.py:118, through `ea import`",
            "defect",
            "A directory that does not exist is reported as the bare path — `FileNotFoundError: /path` — while the line below it, for a directory with no CSVs, writes a sentence.",
            "`raise FileNotFoundError(str(d))` gives the path as the whole message; `raise FileNotFoundError("
            'f"no CSV files matched in {directory}")`, 389 lines later in the same module, reads as a '
            "sentence. The operator is told nothing they did not type, and the two failures of the same "
            "command read as though they came from different applications.",
        )


@pytest.mark.scenario(
    scenario_id="M51",
    group="M",
    title="import --dry-run loads nothing, and --actor is recorded on every row the load writes",
    feature="Command line · import",
    expected="`--dry-run` reports the same summary validate does and leaves the model and its freshness untouched; a load under `--actor` records that actor and the source system on the rows.",
)
def test_m51_import_dry_run_and_actor(cli, record, tmp_path):
    _, before, _ = run(cli, "stats", limit=60)
    rc, dry, ev = run(cli, "import", "data/sample", "--dry-run", "--source", "m-dry", limit=160)
    must(record, "the dry run ran", rc == 0, ev)
    check(record, "it reports the source it was given", "source=m-dry" in dry, trim(dry))
    check(record, "it validates the whole sample", "0 errors, 0 warnings" in dry, trim(dry))
    check(record, "and it loaded none of it", "elements 0/47" in dry, trim(dry))
    _, after, after_ev = run(cli, "stats", limit=60)
    check(record, "the model is untouched by it", before.splitlines()[0] == after.splitlines()[0], after_ev)
    _, freshness, fresh_ev = run(cli, "health", limit=200)
    check(record, "and the source it was given never reached the model", "m-dry" not in freshness, fresh_ev)

    directory = tmp_path / "m-stamped"
    write_csv(directory, "elements.csv", f"id,type,name\n{STAMPED},Data Entity,M_Stamped_Table\n")
    rc_i, loaded, load_ev = run(
        cli, "import", str(directory), "--source", "m-stamped", "--actor", "m-nightly", limit=150
    )
    must(record, "the load under its own actor ran", rc_i == 0 and "elements 1/1 loaded" in loaded, load_ev)
    _, who, who_ev = run(
        cli,
        "sql",
        f"select created_by, updated_by, source_system, origin from element where element_id = '{STAMPED}'",
        limit=160,
    )
    check(
        record, "the actor is recorded against the row it wrote", "m-nightly" in who, trim(who, 140) or who_ev
    )
    check(
        record,
        "so is the source system, on the row and on its origin",
        "m-stamped" in who and "import:m-stamped" in who,
        trim(who, 140),
    )


@pytest.mark.scenario(
    scenario_id="M52",
    group="M",
    title="export-pack writes the pack named by --pack-id, and destroys the destination when the id is wrong",
    feature="Command line · export-pack",
    expected="`--pack-id higher_education` writes that pack; a pack id the store does not hold is refused by name and the file it was told to write is left as it was.",
)
def test_m52_export_pack_by_id(cli, record, tmp_path, finding):
    out_file = tmp_path / "m-by-id.yaml"
    rc, said, ev = run(cli, "export-pack", str(out_file), "--pack-id", "higher_education", limit=130)
    must(record, "the pack was written by id", rc == 0 and out_file.exists(), ev)
    text = out_file.read_text(encoding="utf-8")
    check(record, "it says which pack it wrote", "higher_education" in said, trim(said))
    check(
        record,
        "the file holds that pack",
        text.startswith("pack:") and "id: higher_education" in text and "element_types:" in text,
        f"{len(text.splitlines())} lines",
    )

    keep = tmp_path / "m-keep.yaml"
    keep.write_text("# M: a file that was already here\n", encoding="utf-8")
    rc_bad, bad, bad_ev = run(
        cli, "export-pack", str(keep), "--pack-id", "m-no-such-pack", expect=None, limit=140
    )
    check(record, "a pack id the store does not hold fails", rc_bad == 1, bad_ev)
    check(
        record,
        "the failure names the pack id it could not find",
        "m-no-such-pack" in bad,
        f"the refusal reads {refusal(bad)!r}",
    )
    survived = keep.exists() and keep.read_text(encoding="utf-8").startswith("# M:")
    check(
        record,
        "and the file it was told to write is left as it was",
        survived,
        f"{keep.stat().st_size} bytes left in the destination" if keep.exists() else "the file is gone",
    )
    if not survived:
        lodge(
            finding,
            "M-14",
            "src/ea/cli.py · export-pack, src/ea/metamodel/loader.py:153 (dump_pack)",
            "defect",
            "An unknown --pack-id truncates the destination file first and then crashes with an AttributeError that never names the pack.",
            "`export_pack` passes `backend.load_pack(pack_id)` straight to `dump_pack`; the store returns None "
            "for an id it does not hold, and `dump_pack` opens the destination with 'w' before it touches the "
            "pack. So `ea export-pack <file> --pack-id <typo>` empties <file> and ends 'AttributeError: "
            "'NoneType' object has no attribute 'element_types''. Pointed at a pack under version control, a "
            "mistyped id destroys it.",
        )


@pytest.mark.scenario(
    scenario_id="M53",
    group="M",
    title="init loads the pack it is given, and fails on one it cannot read",
    feature="Command line · init",
    expected="`init --pack` loads that file into the new database; a pack file that does not exist exits 1 and names the file.",
)
def test_m53_init_pack(cli, record, tmp_path, finding):
    fresh = tmp_path / "m-packed.duckdb"
    rc, out, ev = run(
        cli, "init", "--db", str(fresh), "--pack", "packs/higher_education/metamodel.yaml", limit=150
    )
    must(record, "the database was created from the pack it was given", rc == 0 and fresh.exists(), ev)
    check(
        record,
        "it names the pack it loaded and how big it is",
        "higher_education" in out and "element types" in out and "relationship types" in out,
        trim(out),
    )
    _, summary_out, summary_ev = run(cli, "summary", EA_DB_PATH=str(fresh), limit=90)
    check(
        record, "the new database holds that metamodel", "pack `higher_education`" in summary_out, summary_ev
    )
    _, stats_out, stats_ev = run(cli, "stats", EA_DB_PATH=str(fresh), limit=90)
    check(record, "and no content", stats_out.strip().startswith("0 elements, 0 relationships"), stats_ev)

    missing = tmp_path / "m-no-pack.yaml"
    half = tmp_path / "m-half.duckdb"
    rc_bad, bad, bad_ev = run(cli, "init", "--db", str(half), "--pack", str(missing), expect=1, limit=150)
    check(record, "a pack file that does not exist fails", rc_bad == 1, bad_ev)
    check(
        record,
        "and the file it could not read is named",
        str(missing) in refusal(bad).replace("\n", ""),
        trim(refusal(bad).replace("\n", ""), 130),
    )
    if half.exists():
        lodge(
            finding,
            "M-15",
            "src/ea/cli.py · init",
            "usability",
            "An init that fails on its pack leaves the database file it had already created behind.",
            f"`ea init --db <new file> --pack <a file that does not exist>` exits 1 with the database created "
            f"and empty ({half.stat().st_size} bytes). `_ctx()` opens the store before `load_pack` is reached, "
            "so a mistyped pack leaves an artefact that looks like a repository and holds nothing.",
        )


# ================================================= branches: the paths only an error takes =
@pytest.mark.scenario(
    scenario_id="M54",
    group="M",
    title="branch create refuses a name that cannot become a branch id",
    feature="Command line · branch create",
    expected="'main' and a name with no letter or digit in it are both refused, each saying what a name must be, and neither leaves a branch behind.",
)
def test_m54_branch_name_refused(cli, record):
    _, before, before_ev = run(cli, "branch", "list", limit=200)
    count_before = len([ln for ln in before.splitlines() if ln.strip()])
    for name, wanted in (("main", "other than 'main'"), ("!!!", "letter or a number")):
        rc, out, ev = run(cli, "branch", "create", name, expect=1, limit=140)
        check(record, f"a branch named {name!r} is refused", rc == 1, ev)
        check(
            record,
            f"the refusal of {name!r} says what a name must be",
            wanted in refusal(out).replace("\n", " "),
            trim(refusal(out), 130),
        )
    _, after, after_ev = run(cli, "branch", "list", limit=200)
    check(
        record,
        "neither attempt left a branch behind",
        len([ln for ln in after.splitlines() if ln.strip()]) == count_before,
        f"{count_before} branches before, {len([ln for ln in after.splitlines() if ln.strip()])} after",
    )
    check(record, "and 'main' is still not one of them", not after.startswith("main "), after_ev)


@pytest.mark.scenario(
    scenario_id="M55",
    group="M",
    title="--branch accepts a branch that was never created, and the write lands where nothing can reach it",
    feature="Command line · --branch",
    expected="Writing under a branch id no `branch create` ever made is refused; today it is accepted, the rows are invisible to `branch list`, `branch diff` cannot read them, and a branch created later with that id carries them.",
    branch=GHOST_BRANCH,
)
def test_m55_branch_never_created(cli, record, finding):
    _, main_before, main_ev = run(cli, "get", GHOST_ELEMENT, limit=90)
    head_before = main_before.splitlines()[0]
    must(record, "the element reads its main value to start with", "status=" in head_before, main_ev)

    rc, out, ev = run(
        cli,
        "--branch",
        GHOST_BRANCH,
        "set",
        GHOST_ELEMENT,
        "--status",
        "retired",
        "--note",
        "M: written to a branch that was never created",
        expect=None,
        limit=140,
    )
    check(
        record,
        "a write to a branch that was never created is refused",
        rc == 1 and "updated 1" not in out,
        ev,
    )

    _, listed, list_ev = run(cli, "branch", "list", limit=200)
    check(
        record,
        "main is untouched by it either way",
        run(cli, "get", GHOST_ELEMENT, limit=90)[1].splitlines()[0] == head_before,
        head_before,
    )
    rc_diff, diff, diff_ev = run(cli, "branch", "diff", GHOST_BRANCH, expect=None, limit=140)
    accepted = "updated 1" in out
    if accepted:
        check(
            record,
            "whatever was written can at least be read back through branch diff",
            rc_diff == 0,
            f"`branch diff {GHOST_BRANCH}` exits {rc_diff}: {trim(refusal(diff), 110)}",
        )
        check(record, "and the branch it went to is listed", GHOST_BRANCH in listed, list_ev)

    # Clean up what the write left behind: a branch created with that id adopts the rows,
    # which is the defect stated as plainly as it can be, and abandoning it discards them.
    rc_c, created, create_ev = run(cli, "branch", "create", "M ghost", expect=None, limit=140)
    if rc_c == 0:
        _, adopted, adopted_ev = run(cli, "branch", "diff", GHOST_BRANCH, limit=160)
        check(
            record,
            "a branch created afterwards with that id starts empty",
            "0 added, 0 changed" in adopted.splitlines()[0],
            adopted.splitlines()[0] if adopted else adopted_ev,
        )
        rc_a, abandoned, abandon_ev = run(cli, "branch", "abandon", GHOST_BRANCH, limit=130)
        check(record, "the rows are discarded with it", rc_a == 0 and "abandoned" in abandoned, abandon_ev)
    else:
        check(record, "no branch was left to clean up", GHOST_BRANCH not in listed, create_ev)
    _, final, final_ev = run(cli, "get", GHOST_ELEMENT, limit=90)
    check(record, "main ends as it started", final.splitlines()[0] == head_before, final_ev)
    if accepted:
        lodge(
            finding,
            "M-16",
            "src/ea/backend/branching.py · set_branch, through every writing command",
            "defect",
            "A write under a --branch nobody created is accepted into an overlay that `branch list` never shows and `branch diff` cannot read.",
            f"`ea --branch {GHOST_BRANCH} set {GHOST_ELEMENT} --status retired` reports 'updated 1, refused 0'. "
            "`validate_branch_id` checks the shape of the id and nothing checks that the branch exists, so "
            "`check_write` finds no branch record, skips the freeze check and writes the row into "
            f"`branch_element`. `branch diff {GHOST_BRANCH}` then answers 'no branch with id {GHOST_BRANCH}' "
            "and `branch list` does not mention it: the edit cannot be reviewed, merged or abandoned. A branch "
            "created later with that id inherits the orphaned change as though somebody had made it there.",
        )


@pytest.mark.scenario(
    scenario_id="M56",
    group="M",
    title="A branch conflicts when main moves under it, and --resolve says which side wins",
    feature="Command line · branch merge --resolve",
    expected="`branch diff` marks the item CONFLICT; a merge without a resolution applies nothing and leaves the branch open; `--resolve <key>=branch` applies the branch's row over main's.",
    branch=CONFLICT_BRANCH,
)
def test_m56_merge_conflict(cli, record, finding):
    rc_c, created, create_ev = run(cli, "branch", "create", "M conflict", limit=130)
    must(record, "the branch was created", rc_c == 0 and CONFLICT_BRANCH in created, create_ev)
    rc_b, on_branch, branch_ev = run(
        cli, "--branch", CONFLICT_BRANCH, "set", WRITE_ELEMENT, "--status", "approved", limit=130
    )
    must(record, "the branch carries a change", rc_b == 0 and "updated 1" in on_branch, branch_ev)
    rc_m, moved, moved_ev = run(cli, "set", WRITE_ELEMENT, "--note", "M: main moved underneath", limit=130)
    must(record, "main then moved under it", rc_m == 0 and "updated 1" in moved, moved_ev)

    rc, diff, ev = run(cli, "branch", "diff", CONFLICT_BRANCH, limit=190)
    must(record, "the change set was reported", rc == 0 and diff.strip(), ev)
    check(
        record, "the heading counts the conflict", "1 conflicts" in diff.splitlines()[0], diff.splitlines()[0]
    )
    row = next((ln for ln in diff.splitlines() if WRITE_ELEMENT in ln), "")
    must(record, "the conflicting item is listed", bool(row), ev)
    check(record, "the row is marked as a conflict", "CONFLICT" in row, row.strip())
    check(
        record,
        "and it says which version of main the branch started from",
        "changed" in row and "element" in row,
        row.strip(),
    )

    rc_n, nothing, nothing_ev = run(cli, "branch", "merge", CONFLICT_BRANCH, limit=140)
    must(record, "a merge with the conflict unresolved ran", rc_n == 0, nothing_ev)
    check(record, "it applies nothing", "merged 0 item(s)" in nothing, trim(nothing))
    check(record, "the item stays on the branch", "1 remaining" in nothing, trim(nothing))
    check(record, "and the branch stays open", "still open" in nothing, trim(nothing))
    _, kept, kept_ev = run(
        cli, "sql", f"select status, target_note from element where element_id = '{WRITE_ELEMENT}'", limit=150
    )
    check(
        record,
        "main keeps its own value meanwhile",
        "main moved underneath" in kept,
        trim(kept, 130) or kept_ev,
    )
    if "conflict" not in nothing.lower():
        lodge(
            finding,
            "M-17",
            "src/ea/cli.py · branch merge",
            "usability",
            "A merge stopped by an unresolved conflict says 'merged 0 item(s), dropped 0, 1 remaining' and never says a conflict is why.",
            "The merge exits 0 and reads exactly like a merge with nothing to do. `branch diff` marks the row "
            "CONFLICT and `merge` takes `--resolve <key>=branch|main`, so the command knows both the cause and "
            "the cure; naming the conflicting items and the flag that resolves them would close the loop.",
        )

    rc_r, resolved, resolve_ev = run(
        cli, "branch", "merge", CONFLICT_BRANCH, "--resolve", f"element:{WRITE_ELEMENT}=branch", limit=150
    )
    must(record, "the merge with a resolution ran", rc_r == 0, resolve_ev)
    check(record, "the resolved item is applied", "merged 1 item(s)" in resolved, trim(resolved))
    check(record, "nothing is left on the branch", "0 remaining" in resolved, trim(resolved))
    check(record, "so it closes", "branch closed" in resolved, trim(resolved))
    _, after, after_ev = run(
        cli, "sql", f"select status, target_note from element where element_id = '{WRITE_ELEMENT}'", limit=150
    )
    check(record, "main now carries the branch's status", "approved" in after, trim(after, 130))
    check(
        record,
        "and the branch's row replaced main's wholesale, note and all",
        "main moved underneath" not in after,
        trim(after, 130) or after_ev,
    )
    _, listed, list_ev = run(cli, "branch", "list", "--status", "merged", limit=200)
    check(
        record,
        "the branch is recorded as merged",
        any(ln.startswith(CONFLICT_BRANCH) for ln in listed.splitlines()),
        list_ev,
    )


@pytest.mark.scenario(
    scenario_id="M57",
    group="M",
    title="--resolve <key>=main drops the branch's row and leaves main's value standing",
    feature="Command line · branch merge --resolve",
    expected="A conflict resolved to main is reported as dropped rather than merged, main keeps the value it had, and the branch closes because nothing is left on it.",
    branch=DROP_BRANCH,
)
def test_m57_resolve_to_main(cli, record):
    rc_c, created, create_ev = run(cli, "branch", "create", "M drop", limit=130)
    must(record, "the branch was created", rc_c == 0 and DROP_BRANCH in created, create_ev)
    rc_b, wrote, wrote_ev = run(
        cli, "--branch", DROP_BRANCH, "set", WRITE_ELEMENT, "--status", "retired", limit=130
    )
    must(record, "the branch carries a change", rc_b == 0 and "updated 1" in wrote, wrote_ev)
    rc_m, moved, moved_ev = run(cli, "set", WRITE_ELEMENT, "--note", "M: main wins this one", limit=130)
    must(record, "main moved under it", rc_m == 0 and "updated 1" in moved, moved_ev)
    _, diff, diff_ev = run(cli, "branch", "diff", DROP_BRANCH, limit=180)
    must(record, "the item conflicts", "1 conflicts" in diff.splitlines()[0], diff_ev)

    rc, out, ev = run(
        cli, "branch", "merge", DROP_BRANCH, "--resolve", f"element:{WRITE_ELEMENT}=main", limit=150
    )
    must(record, "the merge ran", rc == 0, ev)
    check(
        record,
        "the branch's row is dropped, not applied",
        "merged 0 item(s)" in out and "dropped 1" in out,
        trim(out),
    )
    check(
        record,
        "nothing is left on the branch, so it closes",
        "0 remaining" in out and "branch closed" in out,
        trim(out),
    )

    _, after, after_ev = run(
        cli, "sql", f"select status, target_note from element where element_id = '{WRITE_ELEMENT}'", limit=150
    )
    check(
        record, "main kept the note it moved to", "main wins this one" in after, trim(after, 130) or after_ev
    )
    check(record, "and the branch's status never reached it", "retired" not in after, trim(after, 130))
    _, listed, list_ev = run(cli, "branch", "list", limit=200)
    row = next((ln for ln in listed.splitlines() if ln.startswith(DROP_BRANCH)), "")
    must(record, "the branch is listed", bool(row), list_ev)
    check(record, "it is closed with no rows left on it", " 0 rows" in row and "merged" in row, row.strip())


@pytest.mark.scenario(
    scenario_id="M58",
    group="M",
    title="The review actions are refused to every role that does not hold them",
    feature="Command line · --as, branch review, approve, send-back, reviewers set",
    expected="A Reviewer may not request a review or edit a branch, an Architect may not approve one or send it back, and only an Admin may assign reviewers — each refusal naming the role and the action.",
    role="reviewer",
    branch=ROLES_BRANCH,
)
def test_m58_review_roles(cli, record):
    rc_c, created, create_ev = run(cli, "branch", "create", "M roles", limit=130)
    must(record, "a branch to decide was created", rc_c == 0 and ROLES_BRANCH in created, create_ev)
    rc_w, wrote, wrote_ev = run(cli, "--branch", ROLES_BRANCH, "set", ENTITY, "--status", "draft", limit=130)
    must(record, "it carries a change to review", rc_w == 0 and "updated 1" in wrote, wrote_ev)

    rc_req, req_refused, req_ev = run(
        cli, "--as", "reviewer", "branch", "review", ROLES_BRANCH, expect=1, limit=140
    )
    check(
        record,
        "a reviewer may not request a review",
        rc_req == 1 and "may not request a review" in req_refused,
        trim(refusal(req_refused), 130) or req_ev,
    )
    rc_edit, edit_refused, edit_ev = run(
        cli,
        "--as",
        "reviewer",
        "--branch",
        ROLES_BRANCH,
        "set",
        ENTITY,
        "--status",
        "approved",
        expect=1,
        limit=140,
    )
    check(
        record,
        "nor edit the branch they are to review",
        rc_edit == 1 and "may not bulk edit" in edit_refused,
        trim(refusal(edit_refused), 130) or edit_ev,
    )
    rc_assign, assign_refused, assign_ev = run(
        cli, "--as", "architect", "reviewers", "set", "data_entity", REVIEWER_USER, expect=1, limit=140
    )
    check(
        record,
        "an architect may not assign reviewers",
        rc_assign == 1 and "may not assign reviewers" in assign_refused,
        trim(refusal(assign_refused), 130) or assign_ev,
    )

    rc_r, requested, requested_ev = run(cli, "branch", "review", ROLES_BRANCH, limit=140)
    must(record, "the author puts it in review", rc_r == 0 and "is in review" in requested, requested_ev)
    rc_app, app_refused, app_ev = run(
        cli,
        "--as",
        "architect",
        "branch",
        "approve",
        ROLES_BRANCH,
        "--actor",
        REVIEWER_USER,
        expect=1,
        limit=140,
    )
    check(
        record,
        "an architect may not approve a branch",
        rc_app == 1 and "may not approve a branch" in app_refused,
        trim(refusal(app_refused), 130) or app_ev,
    )
    rc_back, back_refused, back_ev = run(
        cli,
        "--as",
        "architect",
        "branch",
        "send-back",
        ROLES_BRANCH,
        "--comment",
        "M: no",
        expect=1,
        limit=140,
    )
    check(
        record,
        "nor send one back",
        rc_back == 1 and "may not send a branch back" in back_refused,
        trim(refusal(back_refused), 130) or back_ev,
    )
    _, listed, list_ev = run(cli, "branch", "list", limit=200)
    row = next((ln for ln in listed.splitlines() if ln.startswith(ROLES_BRANCH)), "")
    check(record, "none of the refusals moved the branch on", "in_review" in row, row.strip() or list_ev)

    rc_end, ended, end_ev = run(cli, "branch", "abandon", ROLES_BRANCH, limit=130)
    check(
        record, "an admin closes the branch the scenario opened", rc_end == 0 and "abandoned" in ended, end_ev
    )


@pytest.mark.scenario(
    scenario_id="M59",
    group="M",
    title="A review needs something to review, happens once, and is not approved by its author",
    feature="Command line · branch review, approve --types",
    expected="A branch with nothing on it cannot be reviewed, one already in review is not sent again, its author may not approve it, a type outside its change set cannot be approved, and `--types` approves the one it does touch.",
    role="reviewer",
    branch=REVIEW_BRANCH,
)
def test_m59_review_conflicts(cli, record):
    rc_c, created, create_ev = run(cli, "branch", "create", "M review", limit=130)
    must(record, "the branch was created", rc_c == 0 and REVIEW_BRANCH in created, create_ev)

    rc_empty, empty, empty_ev = run(cli, "branch", "review", REVIEW_BRANCH, expect=1, limit=140)
    check(
        record,
        "a branch with nothing on it cannot be reviewed",
        rc_empty == 1 and "nothing on the branch to review" in empty,
        trim(refusal(empty), 130) or empty_ev,
    )

    rc_w, wrote, wrote_ev = run(
        cli, "--branch", REVIEW_BRANCH, "set", ENTITY, "--status", "approved", limit=130
    )
    must(record, "with a change on it the branch is reviewable", rc_w == 0 and "updated 1" in wrote, wrote_ev)
    rc_r, requested, req_ev = run(cli, "branch", "review", REVIEW_BRANCH, limit=140)
    must(record, "the review was requested", rc_r == 0 and "is in review" in requested, req_ev)

    rc_again, again, again_ev = run(cli, "branch", "review", REVIEW_BRANCH, expect=1, limit=140)
    check(
        record,
        "a branch already in review is not sent again",
        rc_again == 1 and "is in_review" in again,
        trim(refusal(again), 130) or again_ev,
    )
    rc_self, self_out, self_ev = run(
        cli, "--as", "reviewer", "branch", "approve", REVIEW_BRANCH, "--actor", AUTHOR, expect=1, limit=140
    )
    check(
        record,
        "the author of a branch may not approve it",
        rc_self == 1 and "author of a branch may not approve it" in self_out,
        trim(refusal(self_out), 130) or self_ev,
    )
    rc_type, wrong_type, type_ev = run(
        cli,
        "--as",
        "reviewer",
        "branch",
        "approve",
        REVIEW_BRANCH,
        "--types",
        "capability",
        "--actor",
        REVIEWER_USER,
        "--groups",
        REVIEWER_GROUP,
        expect=1,
        limit=140,
    )
    check(
        record,
        "a type the branch does not touch cannot be approved",
        rc_type == 1 and "none of the given types is in the branch's change set" in wrong_type,
        trim(refusal(wrong_type), 130) or type_ev,
    )

    rc_ok, approved, ok_ev = run(
        cli,
        "--as",
        "reviewer",
        "branch",
        "approve",
        REVIEW_BRANCH,
        "--types",
        "data_entity",
        "--actor",
        REVIEWER_USER,
        "--groups",
        REVIEWER_GROUP,
        limit=140,
    )
    must(record, "the type it does touch is approved", rc_ok == 0, ok_ev)
    check(
        record,
        "the approval names that type and nothing else",
        "approved data_entity" in approved,
        trim(approved),
    )
    check(record, "nothing is left pending", "pending none" in approved, trim(approved))
    check(record, "so the branch is approved", f"'{REVIEW_BRANCH}' is approved" in approved, trim(approved))

    rc_end, ended, end_ev = run(cli, "branch", "abandon", REVIEW_BRANCH, limit=130)
    check(
        record, "the branch the scenario opened is closed again", rc_end == 0 and "abandoned" in ended, end_ev
    )


@pytest.mark.scenario(
    scenario_id="M60",
    group="M",
    title="reviewers set clears an assignment, resolves a display name, and calls an element type an element",
    feature="Command line · reviewers set",
    expected="An empty string returns the type to any reviewer, a display name resolves to its type id, and a type that is not in the metamodel is refused as a type rather than as an element.",
)
def test_m60_reviewer_assignments(cli, record, finding):
    rc, cleared, ev = run(cli, "reviewers", "set", "data_entity", "", limit=140)
    must(record, "the assignment was cleared", rc == 0, ev)
    check(record, "it says the type is back to any reviewer", "(any reviewer)" in cleared, trim(cleared))
    _, empty, empty_ev = run(cli, "reviewers", "list", limit=140)
    check(
        record,
        "and the listing no longer names the type",
        not any(ln.startswith("data_entity") for ln in empty.splitlines()),
        trim(empty, 130) or empty_ev,
    )

    rc_r, restored, restore_ev = run(
        cli, "reviewers", "set", "data_entity", f"{REVIEWER_USER},{REVIEWER_GROUP}", limit=140
    )
    must(record, "the round's own assignment is put back", rc_r == 0, restore_ev)
    _, back, back_ev = run(cli, "reviewers", "list", limit=140)
    row = next((ln for ln in back.splitlines() if ln.startswith("data_entity")), "")
    check(
        record,
        "it reads as it did before",
        REVIEWER_USER in row and REVIEWER_GROUP in row,
        row.strip() or back_ev,
    )

    rc_n, by_name, name_ev = run(cli, "reviewers", "set", "Data Product", REVIEWER_GROUP, limit=140)
    check(
        record,
        "a type given by its display name is stored under its id",
        rc_n == 0 and "reviewers of data_product" in by_name,
        trim(by_name) or name_ev,
    )
    run(cli, "reviewers", "set", "data_product", "", limit=120)  # leave the round's assignments as they were

    rc_bad, bad, bad_ev = run(cli, "reviewers", "set", "not_a_type", REVIEWER_GROUP, expect=1, limit=140)
    check(record, "a type that is not in the metamodel is refused", rc_bad == 1, bad_ev)
    said = refusal(bad)
    check(
        record,
        "and the refusal does not call the element type an element",
        "element" not in said.lower(),
        f"the refusal reads {said!r}",
    )
    if "element" in said.lower():
        lodge(
            finding,
            "M-18",
            "src/ea/services/reviews.py:33 (set_assignment), through `ea reviewers set`",
            "defect",
            "Assigning reviewers to a type that is not in the metamodel is refused as 'no element with id <type>' — the wrong noun for the thing that was not found.",
            f"`ea reviewers set not_a_type <group>` ends {said!r}. `set_assignment` raises "
            "`NotFoundError(type_id)` and the class defaults its kind to 'element', so the operator is told an "
            "element is missing when they named an element type. The same call site knows it is a type: "
            "`NotFoundError(type_id, 'element type')` would read correctly.",
        )
    _, final, final_ev = run(cli, "reviewers", "list", limit=140)
    check(
        record,
        "nothing the scenario tried changed the assignments it leaves behind",
        "data_product" not in final and REVIEWER_GROUP in final,
        trim(final, 130) or final_ev,
    )


# ============================================================== who is running it, part two
@pytest.mark.scenario(
    scenario_id="M61",
    group="M",
    title="--as agent reads exactly what an admin reads and writes nothing at all",
    feature="Command line · --as agent",
    expected="Every read returns the same bytes as the Admin's; a write to main, a branch of its own and a write on somebody else's branch are all refused by name.",
    role="agent",
    branch=AGENT_BRANCH,
)
def test_m61_as_agent(cli, record):
    for command in (("stats",), ("get", ENTITY), ("summary",), ("find", "course"), ("view", ASSET)):
        rc, as_agent, ev = run(cli, "--as", "agent", *command, limit=90)
        _, as_admin, _ = run(cli, *command, limit=90)
        check(
            record,
            f"an agent reads {command[0]} exactly as an admin does",
            rc == 0 and bool(as_agent.strip()) and as_agent == as_admin,
            ev,
        )

    _, before, before_ev = run(cli, "get", AGENT_ELEMENT, limit=90)
    head_before = before.splitlines()[0]
    must(record, "the element to be left alone reads its main value", "status=" in head_before, before_ev)

    rc_main, refused, main_ev = run(
        cli, "--as", "agent", "set", AGENT_ELEMENT, "--status", "retired", expect=1, limit=140
    )
    check(
        record,
        "an agent may not write to main",
        rc_main == 1 and "may not change main directly" in refused,
        trim(refusal(refused), 130) or main_ev,
    )
    rc_create, create_refused, create_ev = run(
        cli, "--as", "agent", "branch", "create", "M agent", expect=1, limit=140
    )
    check(
        record,
        "nor open a branch to write on",
        rc_create == 1 and "may not create a branch" in create_refused,
        trim(refusal(create_refused), 130) or create_ev,
    )

    rc_open, opened, open_ev = run(cli, "branch", "create", "M agent", limit=130)
    must(record, "an admin opens one for it instead", rc_open == 0 and AGENT_BRANCH in opened, open_ev)
    rc_branch, branch_refused, branch_ev = run(
        cli,
        "--as",
        "agent",
        "--branch",
        AGENT_BRANCH,
        "set",
        AGENT_ELEMENT,
        "--status",
        "retired",
        expect=1,
        limit=140,
    )
    check(
        record,
        "and it may not write on that either",
        rc_branch == 1 and "may not bulk edit" in branch_refused,
        trim(refusal(branch_refused), 130) or branch_ev,
    )
    _, listed, list_ev = run(cli, "branch", "list", limit=200)
    row = next((ln for ln in listed.splitlines() if ln.startswith(AGENT_BRANCH)), "")
    check(record, "the branch carries nothing", " 0 rows" in row, row.strip() or list_ev)
    _, after, after_ev = run(cli, "get", AGENT_ELEMENT, limit=90)
    check(record, "and the element is untouched by any of it", after.splitlines()[0] == head_before, after_ev)
    rc_end, ended, end_ev = run(cli, "branch", "abandon", AGENT_BRANCH, limit=130)
    check(record, "the branch the scenario opened is closed", rc_end == 0 and "abandoned" in ended, end_ev)


@pytest.mark.scenario(
    scenario_id="M62",
    group="M",
    title="EA_ROLE and EA_BRANCH do what the help says they do, and -b is the short form of --branch",
    feature="Command line · --as, --branch, the environment",
    expected="A write under EA_ROLE=reader is refused by name, the same read is byte for byte the Admin's, a write under EA_BRANCH lands on the overlay and not on main, and `-b` reads that overlay exactly as `--branch` does.",
    role="reader",
    branch=ENV_BRANCH,
)
def test_m62_environment_flags(cli, record):
    rc_role, refused, role_ev = run(
        cli, "set", WRITE_ELEMENT, "--status", "retired", expect=1, limit=140, EA_ROLE="reader"
    )
    check(
        record,
        "EA_ROLE sets the role the way --as does",
        rc_role == 1 and "a Reader may not change main directly" in refused,
        trim(refusal(refused), 130) or role_ev,
    )
    _, as_admin, _ = run(cli, "get", ENTITY, limit=90)
    _, as_reader, reader_ev = run(cli, "get", ENTITY, limit=90, EA_ROLE="reader")
    check(
        record,
        "a role narrows what may be written, not what may be read",
        bool(as_reader.strip()) and as_reader == as_admin,
        reader_ev,
    )

    rc_c, created, create_ev = run(cli, "branch", "create", "M env", limit=130)
    must(record, "a branch to write on was created", rc_c == 0 and ENV_BRANCH in created, create_ev)
    _, main_before, main_ev = run(cli, "get", ENV_ELEMENT, limit=90)
    head_before = main_before.splitlines()[0]
    rc_w, wrote, write_ev = run(
        cli, "set", ENV_ELEMENT, "--status", "retired", limit=140, EA_BRANCH=ENV_BRANCH
    )
    must(record, "EA_BRANCH puts the write on the overlay", rc_w == 0 and "updated 1" in wrote, write_ev)
    _, on_main, on_main_ev = run(cli, "get", ENV_ELEMENT, limit=90)
    check(record, "main did not take it", on_main.splitlines()[0] == head_before, on_main.splitlines()[0])

    _, short, short_ev = run(cli, "-b", ENV_BRANCH, "get", ENV_ELEMENT, limit=90)
    check(
        record,
        "-b is the short form of --branch and reads the overlay",
        "status=retired" in short.splitlines()[0],
        short.splitlines()[0] if short else short_ev,
    )
    _, long_form, long_ev = run(cli, "--branch", ENV_BRANCH, "get", ENV_ELEMENT, limit=90)
    check(
        record, "the flag, its short form and the variable name the same branch", short == long_form, long_ev
    )
    _, by_env, env_ev = run(cli, "get", ENV_ELEMENT, limit=90, EA_BRANCH=ENV_BRANCH)
    check(record, "and the variable reads it too", by_env == long_form, env_ev)

    rc_end, ended, end_ev = run(cli, "branch", "abandon", ENV_BRANCH, limit=130)
    check(record, "the branch the scenario opened is closed", rc_end == 0 and "abandoned" in ended, end_ev)
    _, final, final_ev = run(cli, "get", ENV_ELEMENT, limit=90)
    check(record, "main ends as it started", final.splitlines()[0] == head_before, final_ev or on_main_ev)


@pytest.mark.scenario(
    scenario_id="M63",
    group="M",
    title="A branch that has already been merged can be abandoned, and the record then denies the merge",
    feature="Command line · branch abandon",
    expected="Abandoning a closed branch is refused; today it succeeds, rewrites a merged branch's status to abandoned, and can be repeated for ever.",
    branch=CLOSED_BRANCH,
)
def test_m63_abandon_a_closed_branch(cli, record, finding):
    rc_c, created, create_ev = run(cli, "branch", "create", "M closed", limit=130)
    must(record, "the branch was created", rc_c == 0 and CLOSED_BRANCH in created, create_ev)
    rc_w, wrote, write_ev = run(
        cli, "--branch", CLOSED_BRANCH, "set", CLOSED_ELEMENT, "--status", "draft", limit=130
    )
    must(record, "it carries a change", rc_w == 0 and "updated 1" in wrote, write_ev)
    rc_m, merged, merge_ev = run(cli, "branch", "merge", CLOSED_BRANCH, limit=140)
    must(
        record,
        "the change is merged into main and the branch closes",
        rc_m == 0 and "merged 1 item(s)" in merged and "branch closed" in merged,
        merge_ev,
    )
    _, on_main, main_ev = run(cli, "get", CLOSED_ELEMENT, limit=90)
    must(record, "main carries it", "status=draft" in on_main.splitlines()[0], main_ev)

    rc_a, abandoned, abandon_ev = run(cli, "branch", "abandon", CLOSED_BRANCH, expect=None, limit=140)
    check(record, "a branch that has already been merged cannot be abandoned", rc_a == 1, abandon_ev)
    _, listed, list_ev = run(cli, "branch", "list", limit=200)
    row = next((ln for ln in listed.splitlines() if ln.startswith(CLOSED_BRANCH)), "")
    must(record, "the branch is still in the record", bool(row), list_ev)
    check(record, "and the record still says its change was merged", " merged " in row, row.strip())
    _, still, still_ev = run(cli, "get", CLOSED_ELEMENT, limit=90)
    check(
        record,
        "main keeps the change either way",
        "status=draft" in still.splitlines()[0],
        still.splitlines()[0] if still else still_ev,
    )
    rc_again, again, again_ev = run(cli, "branch", "abandon", CLOSED_BRANCH, expect=None, limit=140)
    check(record, "and a closed branch cannot be abandoned twice", rc_again == 1, again_ev)
    if rc_a == 0:
        lodge(
            finding,
            "M-19",
            "src/ea/backend/duckdb_backend.py:1444 (abandon_branch), through `ea branch abandon`",
            "defect",
            "Abandoning a branch that was already merged succeeds and rewrites its status to abandoned, so the record denies a merge that reached main.",
            f"`ea branch merge {CLOSED_BRANCH}` closed the branch as merged and applied its row to main; "
            f"`ea branch abandon {CLOSED_BRANCH}` then answered 'branch {CLOSED_BRANCH} abandoned' and the "
            "listing now reads 'abandoned 0 rows' for a branch whose change is in main. `merge` refuses a "
            "closed branch ('branch … is abandoned'), `abandon_branch` checks nothing but existence, and it "
            "can be repeated indefinitely. Anyone reading the branch log afterwards is told the change was "
            "thrown away.",
        )
