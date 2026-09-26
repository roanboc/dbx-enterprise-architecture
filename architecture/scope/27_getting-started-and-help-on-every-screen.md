# Project Scope — Getting Started and Help on Every Screen

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** branch `claude/user-guide-onboarding-3bx0io`; drafted 2026-09-26,
Understanding granted and built the same day.
**Requester:** the product owner. **Agent:** the coding agent in this
repository. **Reviewer:** the product owner. **Baseline:** initiatives 1 to 26.
**Target plateau:** `PLAT1` The repository running locally, extended.
**Gaps:** `GAP30` **A newcomer has nothing on the screen to learn from**, opened and closed
by this initiative.

The Requester asked for a user guide in the application: *"an intro and help per
main functionality on left panel"*, to ease adoption, *"with diagrams/visuals to
explain why, that and how"*, following good practice for onboarding and *"non
intrusive, so experienced users are not pestered with additional info they don't
need"*. The Guide that [initiative 24](./24_proposals-refined-in-conversation.md)
built explains the repository by role and is, by its own definition, not a manual
of the screens. A person who opens Browse, Branches or Propose for the first time
finds nothing on the screen about why it exists, what it shows or how it is used.

## What changes

**1 — A welcome, once.** The first time a person opens the application in a
browser, a short welcome sits under the title of the screen they land on. It
says what the repository is for, how the navigation's groups follow the work —
find and ask (Discover), change on a branch (Contribute), govern (Manage) — and
where each role starts. It links to Getting started and to the screen's help.
One click closes it, and that browser does not show it again. It never covers
the screen.

**2 — Help on every screen, when asked.** A help button beside each screen's
title opens that screen's help in a side panel:

| Part | What it says |
| ---- | ------------ |
| **Why** | The problem the screen solves, in two or three sentences |
| **What** | What the screen shows and holds: its panels, tabs and main objects |
| **How** | The usual task, in three to six steps, naming the controls as they are labelled |
| **A diagram** | The flow the screen belongs to — for Branches, a branch from main, its changes, the review and the merge |
| **Your role** | What the reader's own role may do on the screen, read from the rule that enforces it |
| **More** | The related screens, and the screen's section of the Guide |

The panel opens only when the button is pressed, or with the `?` key, and
Escape closes it. The screens are every screen in the navigation and the
Element page, which Browse leads to.

**3 — A tip on a screen's first visit.** The first time a person opens a
screen, one line under its title says what the screen is for, with *Show me
how*, which opens the help, and *Turn off tips*. It closes with one click and
does not come back for that screen. *Turn off tips* stops all of them; the
Guide turns them on again and shows the welcome again.

**4 — The Guide gathers it.** The Guide opens with **Getting started**: the
product in one picture, the navigation's four groups, and a first ten minutes
for each role. **The screens** follow, one section each, the same text as the
side panel. **The roles** close it, as today. The Guide draws its diagrams too.

An experienced user sees one small help button beside each title, and nothing
else once the welcome and a screen's tip have been closed.

## The calls made without asking

| Question | Call | What follows from it |
| -------- | ---- | -------------------- |
| **Where is a closed welcome or tip remembered?** | Adopted — in the person's browser, never in the store | Nothing about a person is stored, and nothing is added to the information layer. A second browser, or cleared site data, shows the welcome once more. Remembering it per person needs a store per reader, which initiative 20 left open for saved searches, and the information architect's word |
| **Does the help ever open by itself?** | No | Only the welcome and a screen's one-line tip appear unasked, once each. Neither is a dialog, and neither takes the keyboard's focus |
| **A guided tour that steps through a screen's controls?** | No | A tour interrupts the person who is working, breaks when a screen changes, and repeats what the help says. The help beside the title and the first-visit tip do its job without the interruption |
| **Which screens?** | Adopted — every screen in the navigation and the Element page | The Element page is where an element is read and edited, and every search leads to it |
| **Does the help know the reader's role?** | Yes | The side panel says what the reader's role may do on the screen, read from `allowed()` in `services/roles.py`, the rule that enforces it; a role that may not act is told who can |
| **Principle `P8` and the help's diagrams?** | Adopted — `P8` governs diagrams of the enterprise's model; a help diagram draws how the product is used | A help diagram names no element and is never read as the model. It is written with the help and drawn in the browser by the renderer the application already bundles, so nothing is fetched from the internet |
| **Where is the help written?** | In the repository, as Markdown, one file per screen, generic, beside the guide | One text serves the side panel and the Guide page. It names no organisation and no framework's types; what differs per organisation is read from its metamodel when the help is drawn, as the Guide already does |
| **A new service, or the Guide widened?** | Adopted — the Guide (`ASVC13`) widened, its name kept | The navigation already says Guide, and help on a screen is the Guide met where the work is done |
| **The command line?** | No change | `ea --help` and each command's own help already describe it |
| **Where does the side panel stand?** | Adopted, while building — over the screen with a light veil, not a dark one | It keeps the keyboard inside it until it is closed, as a panel that opens on request should, and the screen it describes stays readable beside it |
| **When is a tip spent?** | Adopted, while building — when it is shown, not when it is closed | Once is the promise: a tip left standing does not come back on the next visit |
| **The Guide's anchors?** | Adopted, while building — each heading's anchor carries its section's name, and `the-boundary` keeps its own | Two role pages both say *How you work*; the page gave two elements one id, which a link reached at random |

## What changes in the model

| Identifier | Element | What moved |
| ---------- | ------- | ---------- |
| `ASVC13` | **Guide** | Widened from the guide by role to the welcome, help on every screen and a tip on a first visit; it stops being "not a manual of the screens" |
| `GAP30` | **A newcomer has nothing on the screen to learn from** | Opened under `PLAT1`; defined in [1_target-state.md](../6_transition/1_target-state.md) |

## EA alignment (assessed top-down before implementing)

**Depth 1 — Application**, as `AGENTS.md` declares.

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | **Aligned — no change.** Serves `G1` **Query the architecture sustainably**, because people get answers without help only if they can work the screens alone, and `G5` **Reusable by any enterprise**, because an adopting organisation (`STK5`) learns the product from the product. `PLAT6`, the current EA tool retired, waits on architects moving over. Stays inside `P5` (the help is generic; types are read from the metamodel) and `P8` (read as the call above says). |
| 2_business | **No change.** No role gains or loses a right, and no process gains a step; a newcomer is any existing role on a first visit. |
| 3_information | **No change.** The help is documentation that ships with the application, and what a person closed stays in their browser, never in the store. |
| 4_application | [1_application-services.md](../4_application/1_application-services.md): `ASVC13` **Guide**, widened. [2_application-components.md](../4_application/2_application-components.md): `ACMP6` draws the help button, the side panel, the welcome, the tips and the Guide's screens. |
| 5_technology | **No new node, service or artifact.** [1_runtime.md](../5_technology/1_runtime.md): `NODE1.3` Browser also keeps what a reader closed; `TSVC3` also draws the help's diagrams and runs its `?` key; `ART5` carries the key's script. |
| Transition | [1_target-state.md](../6_transition/1_target-state.md): `GAP30` opened and closed under `PLAT1`. [2_sequence.md](../6_transition/2_sequence.md): step 1p, built. |

## Approvals

| Gate | Granted | When | What was shown |
| ---- | ------- | ---- | -------------- |
| Understanding | The product owner | 2026-09-26 | This document; `ASVC13` in [1_application-services.md](../4_application/1_application-services.md); `GAP30` and step 1p on the roadmap — each linked on the branch, in the session, together with [initiative 28](./28_users-and-roles.md). The word was *"Yes, implement"* |

## Work packages

| WP | Delivers |
| -- | -------- |
| 1 — The help's content (built) | `docs/guide/0_getting-started.md`, and one page per screen in `docs/guide/screens/` — sixteen, the Users and roles screen of [initiative 28](./28_users-and-roles.md) among them: its tip, why, what, how, a diagram and the related screens; each written from the code and checked against it by a second reader |
| 2 — The side panel (built) | `help_button()` and `help_slot()` beside `page_title()` in `src/ea/ui/components.py`; the side panel in `src/ea/ui/layout.py`; its body, the role line read from `allowed()` and the callbacks in `src/ea/ui/screen_help.py`; the pages read by `GuideService.screen()` in `src/ea/services/guide.py`; the `?` key in `assets/ea-help.js` |
| 3 — The welcome and the tips (built) | `first_visit()` and `after_action()` in `src/ea/ui/screen_help.py`, the record in a local `dcc.Store` (`help-seen`) in the shell |
| 4 — The Guide page (built) | `src/ea/ui/pages/guide.py`: contents under Start here, The screens and By role, with Show the welcome and tips again; Getting started, the screens in the navigation's order and the roles, their diagrams drawn, and each heading's anchor prefixed with its section's, `the-boundary` kept |
| 5 — Tests (built) | `tests/test_help.py` and `tests/test_guide.py`; the browser round's group V (`tests/ui/test_v_help.py`), every other group started as a returning reader (`RETURNING_READER` in `tests/ui/conftest.py`) |

## In scope / out of scope

| In scope | Out of scope |
| -------- | ------------ |
| The welcome and the tips remembered per browser | Remembered per person, across browsers |
| Help for every screen of the navigation and the Element page | Help for each dialog and each field — a field already shows the help text its metamodel gives it |
| Help written once, in English, shipped with the application | An organisation's own additions to the help, and translations |
| Help beside the title and a tip on a first visit | A guided tour through a screen's controls |
| | Measuring which help is read |

## Gap notes

- **Remembered per person.** It needs somewhere per reader to keep a preference,
  keyed by the identity the platform forwards. That is personal data, and a new
  data object the information architect validates; saved searches wait on the
  same store.
- **An organisation's own help.** The help ships generic. An organisation's own
  conventions — which work package to name, who reviews what — would need a
  place in its metamodel or its organisation to live, as its proposal templates
  have.
- **Translations.** The help is Markdown, one file per screen; a second language
  is a second folder and a choice of language per person.
- **Measuring use.** Nothing records which help is opened. `PLAT5` asks for
  questions and feedback to be logged; help usage would join that log.
