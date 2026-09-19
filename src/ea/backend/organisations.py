"""The current organisation, as a request- or call-scoped setting.

An organisation is the enterprise whose architecture a body of content describes
(decision 0014). Every element, relationship, link, branch, review and proposal
belongs to one, and every read and write of the store honours the current one,
the way it honours the current branch: the app sets it per request from the
session, the command line from `--org`. The default organisation is what the
application opens; another one is where a metamodel version is tried on a copy
of the content before it is applied to the default.
"""

from __future__ import annotations

import contextvars
import re
from collections.abc import Iterator
from contextlib import contextmanager

DEFAULT_ORG = "default"
ORG_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

_current: contextvars.ContextVar[str] = contextvars.ContextVar("ea_org", default=DEFAULT_ORG)


def current_org() -> str:
    return _current.get()


def set_org(org_id: str | None) -> contextvars.Token[str]:
    return _current.set(validate_org_id(org_id or DEFAULT_ORG))


def reset_org(token: contextvars.Token[str]) -> None:
    _current.reset(token)


@contextmanager
def use_org(org_id: str | None) -> Iterator[str]:
    token = set_org(org_id)
    try:
        yield current_org()
    finally:
        reset_org(token)


def validate_org_id(org_id: str) -> str:
    if not ORG_ID_RE.match(org_id or ""):
        raise ValueError(
            f"organisation id {org_id!r} must be lowercase letters, digits, '_' or '-', up to 40 characters"
        )
    return org_id


def org_id_from_name(name: str) -> str:
    """An organisation id from a free-text name: lowercase, hyphens for anything else."""
    slug = re.sub(r"[^a-z0-9_-]+", "-", (name or "").strip().lower()).strip("-")[:40]
    if not slug:
        raise ValueError("an organisation name needs a letter or a number in it")
    return validate_org_id(slug)
