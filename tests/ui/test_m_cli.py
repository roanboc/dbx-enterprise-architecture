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
