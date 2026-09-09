"""The document a reviewer reads instead of clicking through the application.

One run writes one folder: this report and the screenshots it embeds, side by side,
so every image link resolves where the report is opened. Nothing here is committed —
the scenarios are, in `tests/ui/`, and this is one run of them.
"""

from __future__ import annotations

import html
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from tests.ui.evidence import GROUPS, Finding, Scenario, Shot

MARK = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=10, check=False
        ).stdout.strip()
    except Exception:  # noqa: BLE001 — a report without a commit line is still a report
        return ""


def _rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _cell(text: str) -> str:
    """One table cell: a pipe escaped, and a newline turned into a break.

    A detail read off a screen carries whatever the screen carried — a table's
    rows, a badge above a caption — and a raw newline in a cell ends the row
    early, so the rest of what was measured is lost from the document.
    """
    return text.replace("|", "\\|").replace("\n", " ⏎ ")


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    out.append("")
    return out


def write_report(
    run_dir: Path,
    scenarios: list[Scenario],
    findings: list[Finding],
    context: dict[str, str],
) -> Path:
    """Render one round into `report.md` inside its own run folder."""
    run_dir.mkdir(parents=True, exist_ok=True)
    scenarios = sorted(scenarios, key=lambda s: (list(GROUPS).index(s.group), s.scenario_id))
    passed = [s for s in scenarios if s.outcome == "passed"]
    failed = [s for s in scenarios if s.outcome == "failed"]
    skipped = [s for s in scenarios if s.outcome == "skipped"]
    shots = sum(len(s.shots) for s in scenarios)

    L: list[str] = []
    L.append("# Application test round")
    L.append("")
    L.append(
        f"{len(scenarios)} scenarios across {len({s.group for s in scenarios})} groups, "
        f"{shots} screenshots. **{len(passed)} passed, {len(failed)} failed, "
        f"{len(skipped)} skipped.**"
    )
    L.append("")
    if (run_dir / "key-screens.html").exists():
        L.append(
            "The screenshots a reviewer reads are on one page: [key-screens.html](./key-screens.html) — "
            "every screen wide and at 480 px, and each state the audit reaches, with the rest of the "
            "evidence folded away by group."
        )
        L.append("")
    L += _table(
        ["", ""],
        [
            ["Run", context.get("started", "")],
            ["Commit", context.get("commit", "")],
            ["Branch", context.get("git_branch", "")],
            ["Model under test", context.get("seed", "")],
            ["Agent provider", context.get("provider", "")],
            ["Browser", context.get("browser", "")],
            ["Viewport", context.get("viewport", "")],
            ["Application", context.get("base_url", "")],
        ],
    )

    L.append("## What this round covers")
    L.append("")
    L.append(
        "Every screen the application offers, every control on it, the five roles and "
        "what each may do, branch overlays through to a merge, every download, the "
        "command line, and the paths that are supposed to fail. Each screen is also "
        "read against a fixed usability checklist, so two rounds can be compared."
    )
    L.append("")
    rows = []
    for key, name in GROUPS.items():
        grp = [s for s in scenarios if s.group == key]
        if not grp:
            continue
        bad = len([s for s in grp if s.outcome == "failed"])
        rows.append(
            [
                key,
                name,
                str(len(grp)),
                "all passed" if not bad else f"**{bad} failed**",
                f"[go to](#{key.lower()}-{name.lower().replace(' ', '-')})",
            ]
        )
    L += _table(["", "Group", "Scenarios", "Result", ""], rows)

    if failed:
        L.append("## What failed")
        L.append("")
        L += _table(
            ["Scenario", "Group", "What was expected", "What happened"],
            [
                [f"`{s.scenario_id}` {s.title}", GROUPS[s.group], s.expected, s.error or "see below"]
                for s in failed
            ],
        )

    if findings:
        L.append("## Findings")
        L.append("")
        L.append(
            "What the round found wrong, including everything the screen audit raised. "
            "A finding is here whether or not a scenario failed for it."
        )
        L.append("")
        ordered = sorted(findings, key=lambda f: f.finding_id)
        L += _table(
            ["", "Where", "Kind", "What is wrong", "Status"],
            [[f.finding_id, f.where, f.severity, f.summary, f.status] for f in ordered],
        )
        # The table says what is wrong; the detail says what was measured and what would fix
        # it, which is what a reader needs to act on one.
        for f in ordered:
            if not f.detail:
                continue
            L.append(f"**{f.finding_id} — {f.summary}**")
            L.append("")
            L.append(f.detail)
            L.append("")

    for key, name in GROUPS.items():
        grp = [s for s in scenarios if s.group == key]
        if not grp:
            continue
        L.append(f"## {key} — {name}")
        L.append("")
        for s in grp:
            L.append(f"### `{s.scenario_id}` — {s.title}")
            L.append("")
            meta = [f"**{MARK[s.outcome]}**"]
            if s.feature:
                meta.append(f"Feature: {s.feature}")
            meta.append(f"As: {s.role}")
            if s.branch != "main":
                meta.append(f"On branch: `{s.branch}`")
            L.append(" · ".join(meta))
            L.append("")
            L.append(f"**Expected.** {s.expected}")
            L.append("")
            if s.error:
                L.append("**Failed.**")
                L.append("")
                L.append("```")
                L.append(s.error.strip()[:3000])
                L.append("```")
                L.append("")
            if s.checks:
                L += _table(
                    ["Checked", "", "Detail"],
                    [[c.name, "ok" if c.ok else "**not ok**", c.detail] for c in s.checks],
                )
            for shot in s.shots:
                # An image link is written only for a file that is there. A round that was
                # interrupted still produces a document whose every link resolves, which is
                # what the repository's own link validator walks over.
                if shot.path.exists():
                    L.append(f"![{shot.caption}]({_rel(shot.path, run_dir)})")
                    L.append("")
                    L.append(f"*{shot.caption}*")
                else:
                    L.append(f"_The evidence &ldquo;{shot.caption}&rdquo; was not captured._")
                L.append("")

    out = run_dir / "report.md"
    out.write_text("\n".join(L).rstrip() + "\n", encoding="utf-8")
    return out


GALLERY_CSS = """
body{font:14px/1.45 system-ui,sans-serif;margin:0;padding:1.5rem;background:#f6f7f9;color:#1b1f24}
h1{font-size:1.4rem;margin:0 0 .25rem} h2{font-size:1.1rem;margin:2rem 0 .75rem}
p.lead{margin:0 0 1rem;color:#4b5563} .grid{display:grid;gap:1rem;grid-template-columns:repeat(auto-fill,minmax(420px,1fr))}
figure{margin:0;background:#fff;border:1px solid #d9dde3;border-radius:6px;padding:.5rem;display:flex;flex-direction:column}
figure img{max-width:100%;height:auto;max-height:70vh;object-fit:contain;object-position:top;border:1px solid #e5e7eb;background:#fff}
figure a{display:block} figcaption{font-size:.85rem;margin-top:.5rem;color:#374151}
figcaption code{font-size:.8rem;background:#eef0f3;padding:0 .3em;border-radius:3px}
details{margin:.75rem 0} summary{cursor:pointer;font-weight:600;padding:.4rem 0} .fail{color:#b42318;font-weight:600}
"""


def write_gallery(run_dir: Path, scenarios: list[Scenario], context: dict[str, str]) -> Path:
    """One page of the screenshots a reviewer is meant to read, the screen audit's first.

    The audit photographs every screen once wide and once at 480 px, and each state that no
    plain address renders; those are the key screens, and a reviewer reads them in one
    scroll instead of opening files. Every other scenario's evidence is on the same page,
    folded away by group, so nothing is hidden and nothing has to be hunted for.
    """
    scenarios = sorted(scenarios, key=lambda s: (list(GROUPS).index(s.group), s.scenario_id))

    def figure(s: Scenario, shot: Shot) -> str:
        src = html.escape(_rel(shot.path, run_dir))
        cap = html.escape(shot.caption)
        mark = "" if s.outcome == "passed" else f' <span class="fail">{MARK[s.outcome]}</span>'
        return (
            f'<figure><a href="{src}"><img src="{src}" alt="{cap}" loading="lazy"></a>'
            f"<figcaption><code>{html.escape(s.scenario_id)}</code>{mark} {cap}</figcaption></figure>"
        )

    L = ["<!doctype html>", '<html lang="en"><head><meta charset="utf-8">', "<title>Key screens</title>"]
    L.append(f"<style>{GALLERY_CSS}</style></head><body>")
    L.append("<h1>Key screens</h1>")
    L.append(
        f'<p class="lead">Run {html.escape(context.get("started", ""))} · commit '
        f"{html.escape(context.get('commit', ''))} · {html.escape(context.get('viewport', ''))}. "
        'The report is <a href="report.md">report.md</a>.</p>'
    )
    audit = [s for s in scenarios if s.group == "P"]
    others = [s for s in scenarios if s.group != "P"]
    L.append("<h2>Every screen, wide and at 480 px, and each state the audit reaches</h2>")
    L.append('<div class="grid">')
    L += [figure(s, shot) for s in audit for shot in s.shots if shot.path.exists()]
    L.append("</div>")
    L.append("<h2>The rest of the evidence, by group</h2>")
    for key, name in GROUPS.items():
        grp = [s for s in others if s.group == key]
        figs = [figure(s, shot) for s in grp for shot in s.shots if shot.path.exists()]
        if not figs:
            continue
        bad = len([s for s in grp if s.outcome == "failed"])
        L.append(
            f"<details><summary>{key} — {html.escape(name)}: {len(figs)} screenshots"
            + (f', <span class="fail">{bad} scenarios failed</span>' if bad else "")
            + "</summary>"
        )
        L.append('<div class="grid">' + "".join(figs) + "</div></details>")
    L.append("</body></html>")
    out = run_dir / "key-screens.html"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


def run_context(base_url: str, browser: str, viewport: str, provider: str, seed: str) -> dict[str, str]:
    return {
        "started": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "commit": _git("rev-parse", "--short", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "base_url": base_url,
        "browser": browser,
        "viewport": viewport,
        "provider": provider,
        "seed": seed,
    }
