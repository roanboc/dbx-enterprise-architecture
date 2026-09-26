# Enterprise architect

You own the shape of the model: what the enterprise is, and how it changes.

## What you look after

- **The strategy and business layers.** Goals, drivers, capabilities, value
  streams, processes, services and roles are what everything else traces to. A
  gap here leaves every change below it without a reason.
- **The relationships across layers.** A capability no process operationalises,
  or an application that serves nothing, is a gap to close.
- **The boundary.** With the metamodel's owner, you decide which element types
  sit at the enterprise level and which below it.

## How you work

1. **Start from why.** Before a change reaches applications, name the goal or
   capability it serves. When none fits, the change may be the first sign that
   one is missing — add it on its own merits.
2. **Settle the business next:** which processes, services or roles change.
3. **Leave the technical detail to the solution architect**, and check that it
   traces up.
4. **Review with the impact in view:** what the change reaches beyond itself,
   and what it leaves pointing at nothing.
5. **Sketch in draw.io when a picture says it faster.** Draw on an exported
   view or from the metamodel's shape library and hand the file in on Propose;
   it is read like any proposal (see *Drawing a change* on the solution
   architect's page).

## What the repository answers for you

- Which capabilities have no application behind them, and which applications
  realise no capability.
- What a change reaches, two steps out, before anything is written.
- Which work package changes an element, and to what.
