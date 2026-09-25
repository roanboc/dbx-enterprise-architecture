# 0023 — The assistant's model is a Model Serving endpoint, and which model is the workspace's choice

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-24 (initiative 24), at the Requester's word — *"Use Databricks Model Serving"* and *"switch to the vendor-neutral API"*. **Touches:** `ACMP5`, `ACMP10`, `TSVC7`, `ART6`, `GAP25`.

## Context

Ask and Propose reached their model with an API key for one model provider's own API. On
Databricks that means a secret in the app and a call leaving the platform, outside the
workspace's governance: its grants, its audit and its usage limits. The Requester asked for
the model to be one Databricks Model Serving provides — and for the platform, not the
application, to decide which model that is.

A serving endpoint answers the chat completions API whichever model it serves, with tool
calls as functions, and its AI Gateway can put several models behind one endpoint with
traffic splitting and fallbacks.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Keep the provider's own API, with its key as a workspace secret | The call leaves the platform, and the workspace neither grants nor sees it |
| The endpoint's compatible route for one provider's own API | The loop the assistant already had would run unchanged, but only that provider's models answer it, so the application would still choose the vendor |
| A supervisor agent on the platform that routes each request to an agent | It chooses per request, but it moves the assistant's loop — the grounding check, the rule that the architect decides — out of the application. It belongs with the tool server and the platform's agents (`PLAT5`), not here |
| **The chat completions API every served model speaks — chosen** | The application names an endpoint and never a model; the workspace chooses the model, and changes it — or routes across several — without a change to the code |

## Decision

**The assistant's model is a Model Serving endpoint, queried over the chat completions API
every served model speaks and signed by the Databricks SDK:** as the app's own identity on
Databricks, and with the architect's own Databricks credentials on a laptop. The bundle names
no model: the endpoint is the workspace's to choose and to configure, and the app is granted
`CAN_QUERY` on it alone. A provider's own API stays for development without a workspace, and
no model for a laptop without either.

## Consequences

- No model key lives in the app on Databricks; who may query the endpoint is the workspace's
  grant, and every query is the workspace's to see and limit.
- A model is swapped, split or given fallbacks in the workspace, never in the application.
- The model must call tools reliably, and models differ at that: the rules' questions need
  none, and judging a model's answers is `PLAT5`'s evaluation, not this record's.
- The request carries only what every served model accepts — messages, tools, a longest
  reply (`EA_AGENT_MAX_TOKENS`) — so no provider's own options reach it. The SDK signs every
  request anew, so an expired token is renewed rather than reused; the request is proven
  against a stand-in endpoint, and its run on a workspace waits with the rest of `PLAT2`.
