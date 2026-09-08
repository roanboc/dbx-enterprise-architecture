"""Roles: who may do what, as a property of the request.

Five roles, cumulative from Reader (decision 0008): Reader, Reviewer, Architect,
Admin, and Agent for the assistant. The role is held in a context variable like
the branch: the app sets it per request from the identity headers (or the debug
persona under mock authentication), the command line from `--as`. One function,
`allowed()`, knows what a role may do; every writing path calls `require()`.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager

from ea.models import ROLES, Forbidden

DEFAULT_ROLE = "admin"  # the command line and the local app start as Admin (the owner's choice)
RANK = {"reader": 0, "reviewer": 1, "architect": 2, "admin": 3}
LABELS = {
    "reader": "Reader",
    "reviewer": "Reviewer",
    "architect": "Architect",
    "admin": "Admin",
    "agent": "Agent",
}
# What each action needs. A role listed may; Admin may everything; Agent may only read.
ACTIONS: dict[str, tuple[str, ...]] = {
    "read": ("reader", "reviewer", "architect", "admin", "agent"),
    "ask": ("reader", "reviewer", "architect", "admin", "agent"),
    "download": ("reader", "reviewer", "architect", "admin", "agent"),
    "edit_content": ("architect", "admin"),  # on a branch
    "edit_main": ("admin",),  # directly on main
    "import": ("architect", "admin"),
    "bulk_edit": ("architect", "admin"),
    "create_branch": ("architect", "admin"),
    "abandon_branch": ("architect", "admin"),  # an architect only their own
    "request_review": ("architect", "admin"),  # the author, or an admin
    "review": ("reviewer", "admin"),
    "merge": ("architect", "admin"),  # an architect only an approved branch
    "merge_without_review": ("admin",),
    "propose": ("architect", "admin"),
    "edit_metamodel": ("admin",),
    "assign_reviewers": ("admin",),
}
DESCRIPTIONS = {
    "reader": "Browse, search, analyse, ask and download. Changes nothing.",
    "reviewer": "A reader who approves or sends back branches for the element types assigned to them.",
    "architect": "A reader who drafts on branches, imports, proposes, requests reviews and merges approved branches.",
    "admin": "Everything, including the metamodel, main, reviewer assignments and merging without a review.",
    "agent": "The assistant: reads through tools and drafts what an architect will tick.",
}

_current: contextvars.ContextVar[str] = contextvars.ContextVar("ea_role", default=DEFAULT_ROLE)


def validate_role(role: str | None) -> str:
    role = (role or "").strip().lower() or DEFAULT_ROLE
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; one of {', '.join(ROLES)}")
    return role


def current_role() -> str:
    return _current.get()


def set_role(role: str | None) -> contextvars.Token[str]:
    return _current.set(validate_role(role))


def reset_role(token: contextvars.Token[str]) -> None:
    _current.reset(token)


@contextmanager
def use_role(role: str | None) -> Iterator[str]:
    token = set_role(role)
    try:
        yield current_role()
    finally:
        reset_role(token)


def allowed(action: str, role: str | None = None) -> bool:
    role = role or current_role()
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    return role in ACTIONS[action]


def a_role(label: str) -> str:
    """`a Reader`, `an Architect`: a refusal is a sentence, and reads like one."""
    return f"{'an' if label[:1].upper() in 'AEIOU' else 'a'} {label}"


def require(action: str, role: str | None = None, what: str = "") -> None:
    """Raise Forbidden, naming the role and the action, when the role may not do this."""
    role = role or current_role()
    if not allowed(action, role):
        raise Forbidden(f"{a_role(LABELS.get(role, role))} may not {what or action.replace('_', ' ')}")


def parse_role_groups(text: str) -> dict[str, set[str]]:
    """`admin=ea-admins,platform-admins;architect=ea-architects;reviewer=ea-reviewers` -> {role: {groups}}."""
    out: dict[str, set[str]] = {}
    for part in (text or "").replace("\n", ";").split(";"):
        role, _, groups = part.partition("=")
        role = role.strip().lower()
        if role in ROLES and groups.strip():
            out[role] = {g.strip() for g in groups.split(",") if g.strip()}
    return out


def role_from_groups(groups: list[str], mapping: dict[str, set[str]]) -> str:
    """The highest role any of the user's groups grants; Reader when none does."""
    best = "reader"
    for role, wanted in mapping.items():
        if role in RANK and RANK[role] > RANK[best] and set(groups) & wanted:
            best = role
    return best
