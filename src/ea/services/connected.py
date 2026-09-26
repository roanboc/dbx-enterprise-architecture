"""The systems of the enterprise the assistant may read over the Model Context Protocol (initiative 26, DOBJ3.12).

A connected system is the organisation's configuration, kept beside its feeds: where the system
is reached, what it speaks for, which of its tools may be called — each one a read — and how a
person is known to it. Connecting one is an admin's decision; which of them a request may use is
read from the role, as everything else is. Reading one is `ea.agent.connected`'s.
"""

from __future__ import annotations

import re

from ea.backend.base import DatabaseBackend
from ea.metamodel.registry import Registry
from ea.models import CONNECTED_AUTH, ROLES, ConnectedSystem, Issue, ValidationError
from ea.services.roles import allowed, current_role, require

ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class ConnectedSystemService:
    def __init__(self, backend: DatabaseBackend, registry: Registry):
        self.backend, self.registry = backend, registry

    def list(self) -> list[ConnectedSystem]:
        return self.backend.list_connected_systems()

    def get(self, system_id: str) -> ConnectedSystem | None:
        return self.backend.get_connected_system(system_id)

    def find(self, name_or_id: str) -> ConnectedSystem | None:
        key = (name_or_id or "").strip().lower()
        return next((s for s in self.list() if key in (s.system_id.lower(), s.name.lower())), None)

    def usable(self, role: str | None = None) -> list[ConnectedSystem]:
        """The systems a request in this role may have read for it: enabled, and — where the
        organisation's own credential is used — only for the roles the admin named."""
        role = role or current_role()
        if not allowed("ask", role):
            return []
        return [
            s for s in self.list() if s.enabled and (s.auth != "credential" or not s.roles or role in s.roles)
        ]

    def save(self, system: ConnectedSystem, actor: str) -> ConnectedSystem:
        require("connect_systems", what="connect a system")
        system.name = (system.name or "").strip()
        system.url = (system.url or "").strip()
        system.tools = [t.strip() for t in system.tools if t.strip()]
        system.link_prefixes = [p.strip() for p in system.link_prefixes if p.strip()]
        system.speaks_for = [self._type(t) for t in system.speaks_for if t.strip()]
        system.page_argument = (system.page_argument or "url").strip()
        problems = []
        if not system.name:
            problems.append("name the system")
        if not re.match(r"^https?://\S+$", system.url):
            problems.append("the address must start with http:// or https://")
        if not system.tools:
            problems.append("list the tools the assistant may call on it; none are called otherwise")
        if system.page_tool and system.page_tool not in system.tools:
            problems.append(f"the page tool {system.page_tool!r} must be one of the tools listed")
        if system.link_prefixes and not system.page_tool:
            problems.append("a system that answers for link addresses names the tool that reads a page")
        if system.auth not in CONNECTED_AUTH:
            problems.append(f"how a person is known to it is one of {', '.join(CONNECTED_AUTH)}")
        if system.auth == "credential" and not ENV_NAME.match(system.credential_env or ""):
            problems.append("a credential is named by the environment variable the platform puts it in")
        if unknown := [r for r in system.roles if r not in ROLES]:
            problems.append(f"unknown role(s): {', '.join(unknown)}")
        if unknown := [t for t in system.speaks_for if t not in self.registry.types]:
            problems.append(f"not element types of the metamodel: {', '.join(unknown)}")
        if problems:
            raise ValidationError([Issue("error", "connected_system", p) for p in problems])
        return self.backend.save_connected_system(system, actor)

    def delete(self, system_id: str, actor: str) -> None:
        require("connect_systems", what="disconnect a system")
        self.backend.delete_connected_system(system_id, actor)

    def _type(self, text: str) -> str:
        t = self.registry.resolve_type(text.strip())
        return t.id if t else text.strip()
