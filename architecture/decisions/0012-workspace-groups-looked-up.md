# 0012 — The forwarded user's groups are read from the workspace, once, and kept for a few minutes

_[← Decisions](./README.md)_

**Status:** Accepted 2026-09-09 (initiative 13) — adopted by the agent, for the Requester to confirm or override at the initiative's gate. **Touches:** `ACMP12`, `TSVC5`; refines decision [0008](./0008-roles-from-groups.md).

## Context

Decision 0008 derives the role from workspace groups through `EA_ROLE_GROUPS`,
and the code read those groups from a request header. Databricks Apps forwards
the signed-in user's e-mail, username and, when the app declares the scope, an
access token; it forwards no groups. Left as it was, every user on the platform
would have been a Reader.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Read the groups from the workspace on every request | A page with twenty callbacks is twenty directory calls; the directory becomes the slowest part of every click |
| Read them once per user and keep them for five minutes — **chosen** | One call per user per five minutes; a membership change is felt within that time, which is the platform's own order of propagation |
| A configured list of users per role | What decision 0008 already rejected: usernames drift, groups are what a workspace administers |
| Require the user's token (the on-behalf-of scope) and nothing else | A workspace where the scope is not granted would make every user a Reader again; the app's own principal reading the user's record is the fallback that keeps roles working |

## Decision

`WorkspaceGroups` in `src/ea/services/identity.py` reads the forwarded user's
groups with their own token when one is forwarded (the user reading their own
record, scope `iam.current-user:read`, declared in the bundle) and otherwise as
the app's service principal, and keeps the answer per user for five minutes.
A lookup that fails makes a Reader and is logged, never raised. A groups header
in the request is believed only where `EA_TRUST_GROUPS_HEADER` says a proxy of
the deployment's own sets it — the platform passes a client's headers through,
and a believed header would let a signed-in Reader pick their role; the debug
persona stays local.

## Consequences

- The app's service principal needs to read users in the workspace when the
  scope is not granted; the bundle declares the scope so that the user's own
  token is the ordinary path.
- A membership change takes up to five minutes to reach the app; an admin who
  cannot wait restarts it.
- The roles service is unchanged: `role_from_groups()` still decides, from
  configuration, and remains testable without a workspace.
