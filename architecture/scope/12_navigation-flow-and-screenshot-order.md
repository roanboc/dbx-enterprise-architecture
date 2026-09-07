# Project Scope — Navigation Flow and Screenshot Order

_[← Scope index](./README.md) · [Model home](../README.md)_

**ArchiMate viewpoint:** Implementation & Migration.
**Delivered as:** the working branch.

This initiative groups the app navigation into a more readable flow — Home, Discover, Contribute and Manage — and orders the README screenshot gallery to match that flow.

## EA alignment (assessed top-down before implementing)

| Layer | Impact |
| ----- | ------ |
| 0_business-design | Not used — this is a Depth 1 application project. |
| 1_strategy | No new strategy element. The change serves `G4` (Goal 4 — Show a working PoC within a month) by making the demo easier to follow. |
| 2_business | No new role, process or service. The menu groups existing services by reader task flow. |
| 3_information | No stored data or exchange format change. |
| 4_application | The shell navigation groups existing pages into Home, Discover, Contribute and Manage; the README screenshot gallery follows the same order. |
| 5_technology | No runtime, build, hosting or storage change. |

## Approvals

| Gate | Approved by | Date | What was approved |
| ---- | ----------- | ---- | ----------------- |
| Gate 0 — Business model | N/A — subject is a single application. | 2026-09-07 | N/A |
| Gate 1 — Strategy | N/A — no new stakeholder, driver, goal, principle or value stream change. | 2026-09-07 | N/A |
| Gate 2 — Business | Requester | 2026-09-07 | This scope document and the no-change verdicts for strategy, business and information; approved in the conversation. |
| Gate 3 — Solution design | N/A — not requested by the Requester. | 2026-09-07 | N/A |

## Plateaus

| Plateau | State |
| ------- | ----- |
| **Baseline** (before) | The menu is a flat page list and the README screenshots are not ordered by the intended task flow. |
| **Target** (delivered) | The menu is grouped by task flow and the README screenshots follow that order. |

## Work packages and deliverables

### WP1 — Navigation and screenshot order

- **Deliverables:** `src/ea/ui/layout.py`, `assets/styles.css`, `README.md`, `architecture/scope/README.md`.
- **Outcome:** A reader can follow the app from discovery through contribution and management, and the screenshots tell the same story.

## In scope / out of scope

| In scope | Out of scope (gaps, candidate future work) |
| -------- | ------------------------------------------- |
| Grouping the existing menu items. | Adding or removing app pages. |
| Reordering the existing README screenshots. | Recapturing every screenshot solely because the menu labels changed. |

## Gap notes

- A future role-specific menu could hide whole groups by permission; this initiative keeps every group visible and leaves enforcement to existing role checks.

## Delivered

Built on 2026-09-07 on the working branch: the navigation grouped into Home, Discover (Browse, Ask, Impact, Target state), Contribute (Propose, Import, Branches) and Manage (Metamodel, Health) with section headings (`src/ea/ui/layout.py`, `assets/styles.css`); the README screenshot gallery grouped and ordered to the same flow, with every screenshot recaptured so the grouped menu is what the images show (`README.md`, `docs/screenshots/`).

## Open questions

- None.
