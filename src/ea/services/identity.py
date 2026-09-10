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
HEADER_GROUPS = "X-Forwarded-Groups"  # believed only when EA_TRUST_GROUPS_HEADER says a proxy of ours adds it
GROUPS_TTL_SECONDS = 300
CACHE_CEILING = 1000  # entries; past it, the expired ones are dropped on the next write

Lookup = Callable[[str, str | None], list[str]]


def forwarded_identity(
    headers: Any, trust_groups_header: bool = False
) -> tuple[str, list[str] | None, str | None]:
    """(username, groups if a trusted header carried them, the user's token if one was forwarded).

    The platform forwards no groups, and a header the client sends passes through as any
    other: believing it would let a signed-in Reader name their own role. So the groups
    header counts only where the deployment says a proxy of its own sets it.
    """
    email = (headers.get(HEADER_EMAIL) or headers.get(HEADER_USERNAME) or "").strip()
    groups = None
    if trust_groups_header:
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

    One directory call per miss, however many requests arrive together: the
    first caller for a user looks the groups up while the others wait for the
    answer. A lookup that fails leaves the user with no groups — a Reader — and
    is logged, never raised: a page must render for a reader whose directory is
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
        self._inflight: dict[str, threading.Lock] = {}

    def _fresh(self, username: str) -> list[str] | None:
        hit = self._cache.get(username)
        return list(hit[1]) if hit and hit[0] > self._clock() else None

    def groups(self, username: str, token: str | None = None) -> list[str]:
        if not username:
            return []
        with self._lock:
            hit = self._fresh(username)
            if hit is not None:
                return hit
            gate = self._inflight.setdefault(username, threading.Lock())
        with gate:  # the first caller looks up; the rest wait here and then read what it found
            with self._lock:
                hit = self._fresh(username)
                if hit is not None:
                    return hit
            try:
                groups = sorted(set(self._lookup(username, token)))
            except Exception as exc:  # noqa: BLE001 — a directory that is down makes a reader, not an error page
                log.warning("could not read the workspace groups of %s: %s", username, exc)
                groups = []
            with self._lock:
                now = self._clock()
                if len(self._cache) >= CACHE_CEILING:
                    self._cache = {u: v for u, v in self._cache.items() if v[0] > now}
                self._cache[username] = (now + self._ttl, groups)
                self._inflight.pop(username, None)
        return list(groups)

    def forget(self, username: str | None = None) -> None:
        with self._lock:
            if username is None:
                self._cache.clear()
            else:
                self._cache.pop(username, None)
