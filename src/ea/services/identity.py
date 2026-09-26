"""Who is asking, on the platform: the forwarded identity and the workspace groups behind it.

Databricks Apps forwards the signed-in user's e-mail, username and — when the
app declares the scope — an access token in its request headers; it forwards
no groups. The groups are what the role is derived from (decision 0008), so
they are looked up in the workspace: with the user's own token when one is
forwarded (the user reading their own record), otherwise as the app's service
principal reading the user's record. The answer is kept for a few minutes per
user, so a page with twenty callbacks costs one lookup.

A group is carried with the workspace's identifier for it as well as its name
(initiative 28): a role an admin grants is kept by the identifier, so a renamed
group keeps it and a new group given an old name does not inherit it. The
directory an admin picks a group from is read as the application's own identity,
quick to give up when the workspace is slow; locally it is a few sample groups.
"""

from __future__ import annotations

import contextvars
import itertools
import logging
import re
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

from ea.models import GroupRef

log = logging.getLogger(__name__)

# The signed-in person's own platform token for this request, when the platform forwarded one:
# what a connected system that knows people is shown (initiative 26). Set per request, as the
# role is, and never stored.
_token: contextvars.ContextVar[str] = contextvars.ContextVar("ea_reader_token", default="")


def current_token() -> str:
    """The reader's own forwarded token for this request, or empty."""
    return _token.get()


def set_token(token: str | None) -> contextvars.Token[str]:
    return _token.set(token or "")


HEADER_EMAIL = "X-Forwarded-Email"
HEADER_USERNAME = "X-Forwarded-Preferred-Username"
HEADER_TOKEN = "X-Forwarded-Access-Token"  # noqa: S105 — a header name, not a secret
HEADER_GROUPS = "X-Forwarded-Groups"  # believed only when EA_TRUST_GROUPS_HEADER says a proxy of ours adds it
GROUPS_TTL_SECONDS = 300
CACHE_CEILING = 1000  # entries; past it, the expired ones are dropped on the next write

#: A person's groups, looked up: each a GroupRef, or a plain name where only names are known.
Lookup = Callable[[str, str | None], "list[GroupRef] | list[str]"]


def as_group_ref(group: GroupRef | str) -> GroupRef:
    """A group as a GroupRef; a plain string is a name, with no identifier."""
    return group if isinstance(group, GroupRef) else GroupRef(name=str(group))


def _refs_of(groups: Iterable[Any] | None) -> list[GroupRef]:
    """The SDK's ComplexValue groups of a user record (`display`, and the id as `value`)."""
    return sorted({GroupRef(name=g.display, id=g.value or "") for g in (groups or []) if g.display})


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


def _safe_username(username: str) -> str:
    """A username as it may stand inside a directory filter's quotes."""
    return re.sub(r"[^\w.@+-]", "", username or "")


def lookup_workspace_groups(username: str, token: str | None) -> list[GroupRef]:
    """The groups the workspace holds the user in, each with its identifier, through the Databricks SDK."""
    from databricks.sdk import WorkspaceClient  # the `databricks` extra

    if token:
        me = WorkspaceClient(token=token, auth_type="pat").current_user.me()
        return _refs_of(me.groups)
    client = WorkspaceClient()  # the app's service principal, from the environment
    safe = _safe_username(username)
    for user in client.users.list(filter=f'userName eq "{safe}"', attributes="id,userName,groups"):
        return _refs_of(user.groups)
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
        self._cache: dict[str, tuple[float, list[GroupRef]]] = {}
        self._lock = threading.Lock()
        self._inflight: dict[str, threading.Lock] = {}

    def _fresh(self, username: str) -> list[GroupRef] | None:
        hit = self._cache.get(username)
        return list(hit[1]) if hit and hit[0] > self._clock() else None

    def groups(self, username: str, token: str | None = None) -> list[str]:
        """The display names of the user's groups, sorted: what a reviewer assignment names."""
        return sorted({g.name for g in self.refs(username, token)})

    def refs(self, username: str, token: str | None = None) -> list[GroupRef]:
        """The user's groups with the workspace's identifier for each, where the lookup gave one."""
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
                groups = sorted({as_group_ref(g) for g in self._lookup(username, token)})
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


# ------------------------------------------------------------------ the directory (initiative 28)
#: The workspace's groups every person is in. Admin to one of them would make every person in the
#: workspace an admin, so it is never granted (decision 0028). Compared by display name, any case.
ALL_USERS_GROUPS = ("users", "account users")
#: What the screen says, and the command line, when the directory will not answer.
UNSEARCHABLE = "the workspace's groups cannot be searched"
MIN_SEARCH = 2  # letters: one letter matches most of a directory
SEARCH_LIMIT = 20  # groups one search offers; the picker narrows as the admin types
DIRECTORY_TTL_SECONDS = 60
DIRECTORY_TIMEOUT_SECONDS = 5  # a slow workspace gives up quickly: the typed name is the fallback


class DirectoryUnavailable(Exception):
    """The directory could not be asked; the message says why, in words."""


def _directory_client() -> Any:
    """The application's own identity (its service principal on the platform), quick to give up."""
    from databricks.sdk import WorkspaceClient  # the `databricks` extra
    from databricks.sdk.config import Config

    return WorkspaceClient(
        config=Config(
            retry_timeout_seconds=DIRECTORY_TIMEOUT_SECONDS, http_timeout_seconds=DIRECTORY_TIMEOUT_SECONDS
        )
    )


def _search_text(text: str | None) -> str:
    """What was typed, as it may stand inside a directory filter's quotes."""
    return re.sub(r'["\\]', "", text or "").strip()


class WorkspaceDirectory:
    """The workspace's groups and a person's memberships, read as the application's own identity.

    Only an admin's request reaches it (the service requires `grant_roles` first), so a Reader
    cannot list the workspace's groups through the application, and it asks the workspace for no
    permission the application does not already hold. A search is kept for a minute. Anything
    that goes wrong reaches the caller as `DirectoryUnavailable`, in words, never as the SDK's
    own error.
    """

    sample = False
    label = "the workspace"

    def __init__(
        self,
        client: Callable[[], Any] | None = None,
        ttl: float = DIRECTORY_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._make = client or _directory_client
        self._client: Any = None
        self._ttl, self._clock = ttl, clock
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def _workspace(self) -> Any:
        if self._client is None:
            try:
                self._client = self._make()
            except ImportError as exc:
                raise DirectoryUnavailable("the Databricks SDK is not installed here") from exc
            except Exception as exc:  # noqa: BLE001 — no workspace is a reason, not a failure
                log.info("no workspace to search the groups of: %s", type(exc).__name__)
                raise DirectoryUnavailable("no Databricks workspace is configured here") from exc
        return self._client

    def _asked(self, key: str, ask: Callable[[Any], Any]) -> Any:
        now = self._clock()
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > now:
                return hit[1]
        client = self._workspace()
        try:
            answer = ask(client)
        except DirectoryUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — the SDK's own errors are the reason, in words
            log.warning("the workspace's directory did not answer: %s", type(exc).__name__)
            raise DirectoryUnavailable(f"the workspace did not answer ({type(exc).__name__})") from exc
        with self._lock:
            if len(self._cache) >= CACHE_CEILING:
                self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
            self._cache[key] = (now + self._ttl, answer)
        return answer

    def search_groups(self, text: str) -> list[GroupRef]:
        """The groups whose name holds the text, at most SEARCH_LIMIT of them, by name."""
        text = _search_text(text)
        if len(text) < MIN_SEARCH:
            return []

        def ask(client: Any) -> list[GroupRef]:
            found = client.groups.list(
                filter=f'displayName co "{text}"', attributes="id,displayName", count=SEARCH_LIMIT
            )
            return sorted(
                GroupRef(name=g.display_name, id=g.id)
                for g in itertools.islice(found, SEARCH_LIMIT)
                if g.id and g.display_name
            )

        return list(self._asked(f"search:{text.casefold()}", ask))

    def groups_by_id(self, ids: Iterable[str]) -> dict[str, str]:
        """The groups the workspace still holds among these identifiers, with their names now."""
        wanted = sorted({str(i) for i in ids if i})
        out: dict[str, str] = {}
        for start in range(0, len(wanted), SEARCH_LIMIT):
            chunk = [_search_text(i) for i in wanted[start : start + SEARCH_LIMIT]]

            def ask(client: Any, chunk: list[str] = chunk) -> dict[str, str]:
                found = client.groups.list(
                    filter=" or ".join(f'id eq "{i}"' for i in chunk),
                    attributes="id,displayName",
                    count=len(chunk),
                )
                return {g.id: g.display_name for g in itertools.islice(found, len(chunk)) if g.id}

            out.update(self._asked("ids:" + ",".join(chunk), ask))
        return out

    def person_groups(self, email: str) -> list[GroupRef] | None:
        """The groups the person signing in as this e-mail is in; None when nobody signs in so."""
        safe = _safe_username((email or "").strip())
        if not safe:
            return None
        client = self._workspace()
        try:
            users = list(
                itertools.islice(
                    client.users.list(filter=f'userName eq "{safe}"', attributes="id,userName,groups"), 1
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("the workspace's directory did not answer: %s", type(exc).__name__)
            raise DirectoryUnavailable(f"the workspace did not answer ({type(exc).__name__})") from exc
        return _refs_of(users[0].groups) if users else None


#: The groups a local run offers (decision 0008: locally the debug persona is the role), and the
#: debug personas' memberships, so the screen, the check and the tests work without a workspace.
SAMPLE_GROUPS = (
    GroupRef("data-team", "sample-data-team"),
    GroupRef("ea-admins", "sample-ea-admins"),
    GroupRef("ea-architects", "sample-ea-architects"),
    GroupRef("ea-reviewers", "sample-ea-reviewers"),
    GroupRef("solution-architects", "sample-solution-architects"),
    GroupRef("users", "sample-users"),
)
SAMPLE_MEMBERS = {
    "admin@example.edu": ("ea-admins", "users"),
    "architect@example.edu": ("ea-architects", "solution-architects", "users"),
    "reviewer@example.edu": ("ea-reviewers", "users"),
    "reader@example.edu": ("data-team", "users"),
}


class SampleDirectory:
    """A few generic groups and the debug personas' memberships, for a run with no workspace."""

    sample = True
    label = "the sample groups"

    def __init__(
        self,
        groups: Iterable[GroupRef] = SAMPLE_GROUPS,
        members: dict[str, Iterable[str]] | None = None,
    ):
        self.groups = sorted(groups)
        self.members = {
            k.lower(): tuple(v) for k, v in (SAMPLE_MEMBERS if members is None else members).items()
        }

    def search_groups(self, text: str) -> list[GroupRef]:
        text = _search_text(text).casefold()
        if len(text) < MIN_SEARCH:
            return []
        return [g for g in self.groups if text in g.name.casefold()][:SEARCH_LIMIT]

    def groups_by_id(self, ids: Iterable[str]) -> dict[str, str]:
        wanted = set(ids)
        return {g.id: g.name for g in self.groups if g.id in wanted}

    def person_groups(self, email: str) -> list[GroupRef] | None:
        names = self.members.get((email or "").strip().lower())
        if names is None:
            return None
        by_name = {g.name: g for g in self.groups}
        return sorted(by_name.get(n, GroupRef(n)) for n in names)


Directory = WorkspaceDirectory | SampleDirectory


def directory_for(settings: Any) -> Directory:
    """The workspace's directory where the platform signs people in; the sample groups locally,
    where the debug persona is the role (decision 0008) and there is no workspace to ask."""
    return WorkspaceDirectory() if settings.auth == "databricks" else SampleDirectory()
