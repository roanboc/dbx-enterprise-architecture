"""The document a reviewer reads instead of clicking through the application.

One run writes one folder: this report and the screenshots it embeds, side by side,
so every image link resolves where the report is opened. Nothing here is committed —
the scenarios are, in `tests/ui/`, and this is one run of them.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from tests.ui.evidence import GROUPS, Finding, Scenario

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
