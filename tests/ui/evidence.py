"""What a round records: one row per scenario, one file per screenshot.

A scenario is declared once, in the test that performs it, and the recorder keeps
what happened to it. Nothing here knows how to drive a browser; it only knows what
a reviewer needs to see afterwards — the outcome, the checks behind it, and the
images that prove them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# The groups a scenario can belong to, in reading order. The report follows this order,
# so a reviewer walks the application the way a person would rather than alphabetically.
GROUPS: dict[str, str] = {
    "A": "Shell and navigation",
    "B": "Browse",
    "C": "Element",
    "D": "Impact",
    "E": "Target state",
    "F": "Ask",
    "G": "Propose",
    "H": "Import",
    "I": "Branches",
    "J": "Metamodel",
    "K": "Health",
    "L": "Roles and permissions",
    "M": "Command line",
    "N": "Downloads",
    "O": "Negative paths",
    "P": "Screen audit",
}


@dataclass
class Check:
    """One assertion inside a scenario, kept whether it passed or not."""

    name: str
    ok: bool
    detail: str = ""


@dataclass
class Shot:
    """One screenshot, and what the reviewer is meant to see in it."""

    path: Path
    caption: str


@dataclass
class Scenario:
    """One thing the application is asked to do, and what came of it."""

    scenario_id: str
    group: str
    title: str
    expected: str
    role: str = "admin"
    branch: str = "main"
    feature: str = ""
    checks: list[Check] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    outcome: str = "passed"  # passed | failed | skipped
    error: str = ""

    @property
    def failed_checks(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]


@dataclass
class Finding:
    """Something the round found wrong, whether or not a scenario failed for it."""

    finding_id: str
    where: str
    severity: str  # defect | usability | accessibility | consistency
    summary: str
    detail: str = ""
    status: str = "open"  # open | fixed | accepted


def slug(text: str) -> str:
    """A file-safe name for a screenshot, derived from what it shows."""
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return out[:60] or "shot"
