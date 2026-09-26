# 0028 — An admin grants roles to workspace groups in the application; the deployment's grants stay, read-only

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-26 at the Understanding of initiative 28.
Refines [0008](./0008-roles-from-groups.md) and [0012](./0012-workspace-groups-looked-up.md).
**Touches:** `ROLE1`, `BOBJ2`, `BPROC7`, `DOBJ3.13`, `ACMP12`, `TSVC5`, `ART6`, `GAP31`.

## Context

Decision 0008 derives a role from the signed-in person's workspace groups through
`EA_ROLE_GROUPS`, a variable of the deployment bundle. Giving a team a role
means an engineer changing the bundle and redeploying the application. The
application's own admin can neither grant a role, nor see which groups hold one,
nor tell a person why they are a Reader. The Requester asked for an easy form
where the admin manages which Databricks groups hold which role, and settled
that it is groups only, never named people.

## Decision

- **Grants are kept in the store**, one per workspace group, application-wide:
  a role holds in every organisation, as it does today.
- **A group is picked from the workspace's directory** as its name is typed,
  and kept by the directory's identifier, so a renamed group keeps its role and
  a new group given an old name does not inherit it. The directory is asked
  again for the group by that identifier, and its name is the one kept. Where a
  proxy of the deployment's own passes a person's groups by name alone, a picked
  group is matched by the name it was granted under. Where the directory cannot
  be searched, an exact name may be typed; it is marked as not checked, and is
  matched by name until a later search finds its identifier.
- **The deployment's grants stay.** `EA_ROLE_GROUPS` is read as today, matched
  by name, shown on the screen read-only and never changed by the application,
  so an admin group named there is always the way back in.
- **The highest role wins.** A person's role is the highest that the
  deployment's grants or a grant to one of their groups gives; a person no grant
  reaches is a Reader. Reviewer, Architect and Admin may be granted; Reader is
  everybody's and Agent is the assistant's.
- **An admin cannot take away their own Admin.** A removal or a lowering that
  would leave the acting admin below Admin is refused, and so is one that would
  leave no admin grant anywhere. The workspace's all-users group cannot be
  granted Admin, and an Admin grant never lifts anyone through it, whatever
  wrote it.
- **A change is felt within a minute.** Each process keeps the grants for a
  minute and forgets them at once when it changes one. Who is in a group is
  still read from the directory and kept five minutes (decision 0012).
- **The directory is read as the application's own identity**, for the picker
  and for checking a person, with no new permission asked of the workspace, and
  every such read is an admin's alone.
- **Every change is in the change log**, filed under no organisation, and shown
  to admins on the screen.
- **Locally the debug persona is still the role** (decision 0008). The grants
  are kept and checked there as they would apply on the platform.

## Consequences

- An admin gives a team a role in a minute, without a redeploy and without the
  workspace's administrators, who still decide who is in the team.
- Any admin may grant Admin, including one made an admin by a grant. The
  deployment's own admin groups are the check on that, because nobody can
  remove them from the application.
- The first run on a workspace confirms that the application's identity may
  search the directory; until it does, the typed name is the fallback.

## Alternatives not taken

| Option | Why not |
| ------ | ------- |
| Roles granted to named people | The Requester chose groups only; people drift, and groups are what a workspace already administers (decision 0008) |
| Writing `EA_ROLE_GROUPS` from the application | It is the deployment's value, and changing it needs a redeploy |
| Creating groups or changing who is in them | It needs workspace-administrator rights for the application, which one application should not hold |
| Roles per organisation | Roles are application-wide today; per organisation is a larger change and a gap note |
| Matching a grant by the group's name | A rename would silently lose the role, and a new group given the old name would inherit it |
