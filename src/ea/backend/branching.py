"""The current branch of the model, as a request- or call-scoped setting.

`main` is the model itself. Any other branch is an overlay the store lays over
`main` when it reads and writes into when it writes. The app sets the branch
per request from the session; the command line sets it from `--branch`.
"""

from __future__ import annotations

import contextvars
import re
from collections.abc import Iterator
from contextlib import contextmanager

MAIN = "main"
BRANCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,79}$")

_current: contextvars.ContextVar[str] = contextvars.ContextVar("ea_branch", default=MAIN)


def current_branch() -> str:
    return _current.get()


def is_main(branch: str | None = None) -> bool:
    return (branch or current_branch()) == MAIN


def set_branch(branch_id: str | None) -> contextvars.Token[str]:
    return _current.set(validate_branch_id(branch_id or MAIN))


def reset_branch(token: contextvars.Token[str]) -> None:
    _current.reset(token)


@contextmanager
def use_branch(branch_id: str | None) -> Iterator[str]:
    token = set_branch(branch_id)
    try:
        yield current_branch()
    finally:
        reset_branch(token)


def validate_branch_id(branch_id: str) -> str:
    if not BRANCH_ID_RE.match(branch_id):
        raise ValueError(
            f"branch id {branch_id!r} must be lowercase letters, digits, '.', '_', '-' or '/', up to 80 characters"
        )
    return branch_id


def branch_id_from_name(name: str) -> str:
    """A branch id from a free-text name: lowercase, hyphens for anything else."""
    slug = re.sub(r"[^a-z0-9._/-]+", "-", (name or "").strip().lower()).strip("-.")[:80]
    if slug == MAIN:
        raise ValueError("a branch needs a name other than 'main'")
    if not slug:
        raise ValueError("a branch name needs a letter or a number in it")
    return validate_branch_id(slug)
