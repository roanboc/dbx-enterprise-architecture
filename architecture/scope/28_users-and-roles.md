# Project Scope — Users and Roles

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/user-guide-onboarding-3bx0io`; drafted 2026-09-26,
Understanding granted and built the same day; the search of a real workspace waits
with `PLAT2`'s run.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 26,
with [initiative 27](./27_getting-started-and-help-on-every-screen.md) drafted beside it.
**Target plateau:** `PLAT4` Governed change, its roles; the directory on a
workspace waits with `PLAT2`.
**Gaps:** `GAP31` **Who may do what is set only by the deployment**, opened and
closed by this initiative.

The Requester asked for *"an easy user management form for the admin, where we
manage Databricks groups or users and app roles"*, and then settled *"let's keep
it only for groups"*. Today a role comes from `EA_ROLE_GROUPS`, a value of the
deployment: giving a team a role means an engineer changing it and redeploying.
The application's own admin can neither grant a role, nor see which groups hold
one, nor tell a person why they are a Reader.

## What changes

A **Users and roles** screen under Manage, where an admin decides which
Databricks workspace groups hold which role.

1. **Grant a role to a group.** The admin types part of a group's name, picks
   it from the workspace's groups, picks Reviewer, Architect or Admin, and adds
   a line of why. Granting again replaces the role.
2. **See every grant.** The deployment's own grants come first, read-only. The
   grants made here follow, with who granted each, when and why. The admin
   removes one that no longer holds. A group the workspace no longer has is
   marked.
3. **Check a person.** The admin types someone's e-mail and reads the role they
   get and which group gives it.
4. **Recent changes.** Who granted or removed what, and when.

A person who is not an admin sees, on the same screen, their own role, the group
it comes from, and whom to ask for another.

| Rule | Why |
| ---- | --- |
| A person's role is the highest any of their groups gives; a person in none is a Reader | As today, with the application's grants beside the deployment's |
| The deployment's grants are shown and never changed here | An admin group named in the deployment is always the way back in |
| An admin cannot remove or lower their own Admin, nor remove the last admin grant | Nobody locks the application out by accident |
| The workspace's all-users group cannot be granted Admin | It would make every person in the workspace an admin |
| A grant is felt within a minute; a change to who is in a group within five minutes | Group membership is read as today (decision 0012) |
| Creating a group, changing who is in it, and who may open the application at all stay in Databricks | They need workspace-administrator rights, which the application should not hold |

## The calls made without asking

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **A grant per organisation, or for the whole application?** | Adopted — for the whole application | A role holds in every organisation, as it does today. Roles per organisation are a gap note |
| **Is a group kept by its name or its identifier?** | Adopted — by the workspace's identifier, its name kept as a label | A renamed group keeps its role, and a new group given an old name does not inherit it. The deployment's grants are still matched by name |
| **What if the workspace's groups cannot be searched?** | Adopted — an exact name may be typed, marked *not checked* | The screen stays usable at the first run on a workspace, before the search is proven there. The grant is matched by name until a later search finds the group |
| **Who may grant Admin?** | Adopted — any admin | Admin already may do everything. The deployment's admin groups are the check, because nobody can remove them from the application |
| **Who sees the grants?** | Adopted — admins only; every other person sees their own role and where it comes from | The grants are kept out of a reader's own SQL too. The store's check on that SQL could be stepped around, and is fixed first, directly, as a defect |
| **Whose identity searches the workspace?** | Adopted — the application's own, asking the workspace for no new permission | Only an admin's request may search, so a Reader cannot list the workspace's groups through the application |
| **What happens locally, with no workspace?** | Adopted — the debug persona is still the role, as decision 0008 says | The screen offers sample groups and checks a grant as it would apply on the platform. A local persona cannot write grants into the platform's store |
| **The command line?** | Yes — `ea roles` lists, grants, removes, checks and shows the history | Every Manage screen has its command, and it is an admin's way in without a browser |
| **Reviewers per element type?** | They stay on the Metamodel page's Reviewers tab | The Users and roles screen links to it. Who reviews which type is decided per organisation, not per application |
| **Help for the new screen?** | It has its help like every other screen | [Initiative 27](./27_getting-started-and-help-on-every-screen.md) covers every screen in the navigation, this one included |
| **Are the deployment's group names matched with their case?** | Adopted, while building — without it | A group named `EA-Admins` in the workspace and `ea-admins` in the deployment is one group; before, the deployment's names had to match exactly |
| **What if two processes each remove the other's last admin grant?** | Adopted, while building — the check and the write hold a lock the store's other processes honour | On Lakebase the table is locked for the change, so the second removal sees the first |
| **What does the screen say of a group renamed in the workspace?** | Adopted, while building — *now called …* beside the grant | The grant still holds, by the group's identifier; the label is the name it had when it was granted |
| **What if the platform signs people in but the workspace cannot be read?** | Adopted, while building — the page says the workspace's groups cannot be searched, and offers the exact name typed | Sample groups stand in only where the application does not use the platform's sign-in, so a real deployment is never shown groups it does not have |

## What changes in the model

| Identifier | Element | What moved |
| ---------- | ------- | ---------- |
| `ROLE1` | **Admin** | May grant a role to a workspace group and remove it, and read who holds which role and why. May not take away their own Admin, grant the Agent role, or change who is in a group |
| `BOBJ2` | **Role configuration** | Held in two halves: the deployment's `EA_ROLE_GROUPS`, read-only, and the grants an admin keeps in the store |
| `BPROC7` | **Grant access** | New, under the business service `BSVC2` Governed change |
| `DOBJ3.13` | **Role grant** | New: a role given to a workspace group, application-wide, kept in the table `role_grant` with no organisation |
| decision 0028 | **An admin grants roles to workspace groups in the application; the deployment's grants stay, read-only** | Proposed; refines decisions 0008 and 0012 |
| `GAP31` | **Who may do what is set only by the deployment** | Opened under `PLAT4`; defined in [1_target-state.md](../6_transition/1_target-state.md) |

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **Aligned — no change.** Serves `G5` **Reusable by any enterprise**, because an adopting organisation (`STK5`) runs its own access without changing its deployment, and plateau `PLAT4`, where who may draft, approve and merge is a recorded decision. Stays inside `P3`: the Agent role cannot be granted, and no path of the assistant grants anything. |
| 2_business | [1_actors-and-roles.md](../2_business/1_actors-and-roles.md): `ROLE1`, `BOBJ2`. [2_processes-and-services.md](../2_business/2_processes-and-services.md): `BPROC7` **Grant access**, added; `BSVC2` delivered by it too. |
| 3_information | [1_data-objects.md](../3_information/1_data-objects.md): `DOBJ3.13` **Role grant**, added, with its classification. [2_conceptual-data-model.md](../3_information/2_conceptual-data-model.md): ROLE_GRANT, in no organisation. [3_logical-data-model.md](../3_information/3_logical-data-model.md): the table `role_grant` in `ea_governance`, with no `org_id`. |
| 4_application | [1_application-services.md](../4_application/1_application-services.md): `ASVC17` **Users and roles**, added, realized by `ACMP12` Roles and review and `ACMP6` Web application. [2_application-components.md](../4_application/2_application-components.md): `ACMP12` keeps the grants and searches the workspace's groups; `ACMP6` draws the page; `ACMP7` runs `ea roles`. |
| 5_technology | **No new node, service or permission.** [1_runtime.md](../5_technology/1_runtime.md): `TSVC5` Workspace identity is also searched for a group, as the application's identity; `ART6` describes `role_groups` as the deployment's own grants, and so does `databricks.yml`. |
| Transition | [1_target-state.md](../6_transition/1_target-state.md): `GAP31` opened and closed under `PLAT4`, the search of a real workspace with `PLAT2`. [2_sequence.md](../6_transition/2_sequence.md): step 1q, built. Recorded as [decision 0028](../decisions/0028-roles-granted-to-groups-in-the-application.md). |

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------- |
| Understanding | The product owner | 2026-09-26 | This document; `ROLE1` and `BOBJ2` in [1_actors-and-roles.md](../2_business/1_actors-and-roles.md), `BPROC7` in [2_processes-and-services.md](../2_business/2_processes-and-services.md), `DOBJ3.13` in [1_data-objects.md](../3_information/1_data-objects.md) with the `role_grant` table in [3_logical-data-model.md](../3_information/3_logical-data-model.md), [decision 0028](../decisions/0028-roles-granted-to-groups-in-the-application.md), and `GAP31` and step 1q on the roadmap — each linked on the branch, in the session, together with [initiative 27](./27_getting-started-and-help-on-every-screen.md). The word was *"Yes, implement"* |

## Work packages

| WP | Delivers |
| -- | -------- |
| 1 — The grants in the store (built) | The table `role_grant` in `src/ea/backend/sql.py`, read and written in `src/ea/backend/sql_backend.py` on both engines, answering as empty to a reader's own SQL; its changes in the change log under the organisation `*`, which no organisation can be |
| 2 — The role a request is given (built) | `AccessService` in `src/ea/services/access.py`, and `RoleGrant` and `GroupRef` in `src/ea/models.py`; `user_from_headers()` in `src/ea/ui/context.py` asks it, and so does the tool server through it; the action `grant_roles` in `src/ea/services/roles.py` |
| 3 — The workspace's groups (built) | `WorkspaceDirectory` and the sample directory in `src/ea/services/identity.py`; each forwarded group now carries its identifier |
| 4 — The Users and roles page (built) | `src/ea/ui/pages/users.py`, under Manage between Connected systems and Health, with its help (`docs/guide/screens/users.md`) |
| 5 — The command line (built) | `ea roles list`, `grant`, `revoke`, `check` and `history` in `src/ea/cli.py` |
| 6 — Tests (built) | `tests/test_access.py`, `tests/test_users_page.py`, and additions to `tests/test_identity.py` and `tests/test_cli.py`; command-line scenarios M78 and M79; the browser round's group W (`tests/ui/test_w_users.py`) and the page's screen audit |

## In scope / out of scope

| In scope | Out of scope |
| -------- | ------------ |
| Roles granted to workspace groups | Roles granted to named people — settled: groups only |
| One role per group, for the whole application | Roles per organisation |
| Groups the workspace already has | Creating groups, or changing who is in them |
| Roles inside the application | Who may open the application at all |
| A grant that holds until it is removed | A grant that expires on a date |
| An admin deciding | A person asking for a role themselves |

## Gap notes

- **Roles per organisation.** An admin in one organisation is an admin in all
  of them, as today. Per organisation, a grant would carry the organisation, and
  every `allowed()` check would read the one the request is in.
- **Creating groups and changing who is in them.** It needs the application's
  identity to be a workspace administrator. The workspace's own screens do it
  today, and the Users and roles screen says so.
- **Who may open the application.** That is the application's own permission in
  the workspace, set in Databricks; a person without it never reaches a role.
- **A grant that expires, and a person asking for one.** Both are small once
  grants are data: a date on the grant, and a request an admin approves.
