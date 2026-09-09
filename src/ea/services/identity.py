"""Who is asking, on the platform: the forwarded identity and the workspace groups behind it.

Databricks Apps forwards the signed-in user's e-mail, username and — when the
app declares the scope — an access token in its request headers; it forwards
no groups. The groups are what the role is derived from (decision 0008), so
they are looked up in the workspace: with the user's own token when one is
forwarded (the user reading their own record), otherwise as the app's service
principal reading the user's record. The answer is kept for a few minutes per
user, so a page with twenty callbacks costs one lookup.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

HEADER_EMAIL = "X-Forwarded-Email"
HEADER_USERNAME = "X-Forwarded-Preferred-Username"
HEADER_TOKEN = "X-Forwarded-Access-Token"  # noqa: S105 — a header name, not a secret
HEADER_GROUPS = "X-Forwarded-Groups"  # honoured when a proxy adds it; the platform itself does not
GROUPS_TTL_SECONDS = 300

Lookup = Callable[[str, str | None], list[str]]


def forwarded_identity(headers: Any) -> tuple[str, list[str] | None, str | None]:
    """(username, groups if a header carried them, the user's token if one was forwarded)."""
    email = (headers.get(HEADER_EMAIL) or headers.get(HEADER_USERNAME) or "").strip()
    raw = headers.get(HEADER_GROUPS)
    groups = [g.strip() for g in raw.split(",") if g.strip()] if raw is not None else None
    return email, groups, (headers.get(HEADER_TOKEN) or None)


def lookup_workspace_groups(username: str, token: str | None) -> list[str]:
    """The display names of the groups the workspace holds the user in, through the Databricks SDK."""
    from databricks.sdk import WorkspaceClient  # the `databricks` extra

    if token:
        me = WorkspaceClient(token=token, auth_type="pat").current_user.me()
        return sorted(g.display for g in (me.groups or []) if g.display)
    client = WorkspaceClient()  # the app's service principal, from the environment
    safe = re.sub(r"[^\w.@+-]", "", username)
    for user in client.users.list(filter=f'userName eq "{safe}"', attributes="userName,groups"):
        return sorted(g.display for g in (user.groups or []) if g.display)
    return []


class WorkspaceGroups:
    """A user's groups, looked up once and kept for `ttl` seconds.

    A lookup that fails leaves the user with no groups — a Reader — and is
    logged, never raised: a page must render for a reader whose directory is
    down, and a role that cannot be established is the smallest one.
    """

    def __init__(
        self,
        lookup: Lookup | None = None,
        ttl: float = GROUPS_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._lookup = lookup or lookup_workspace_groups
        self._ttl = ttl
        self._clock = clock
        self._cache: dict[str, tuple[float, list[str]]] = {}
        self._lock = threading.Lock()

    def groups(self, username: str, token: str | None = None) -> list[str]:
        if not username:
            return []
        now = self._clock()
        with self._lock:
            hit = self._cache.get(username)
            if hit and hit[0] > now:
                return list(hit[1])
        try:
            groups = sorted(set(self._lookup(username, token)))
        except Exception as exc:  # noqa: BLE001 — a directory that is down makes a reader, not an error page
            log.warning("could not read the workspace groups of %s: %s", username, exc)
            groups = []
        with self._lock:
            self._cache[username] = (now + self._ttl, groups)
        return list(groups)

    def forget(self, username: str | None = None) -> None:
        with self._lock:
            if username is None:
                self._cache.clear()
            else:
                self._cache.pop(username, None)
