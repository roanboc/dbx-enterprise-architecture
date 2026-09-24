# 0023 — The assistant's model is a Model Serving endpoint, reached over its Messages API

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-24 (initiative 24), at the Requester's word — *"Use Databricks Model Serving"*. **Touches:** `ACMP5`, `ACMP10`, `TSVC7`, `ART6`, `GAP25`.

## Context

Ask and Propose reached their model with an API key for the model provider's own
API. On Databricks that means a secret in the app and a call leaving the platform,
outside the workspace's governance: its grants, its audit and its usage limits.
The Requester asked for the model to be one Databricks Model Serving provides.

Model Serving offers an Anthropic-compatible Messages API at
`<workspace>/serving-endpoints/anthropic`: the same request, signed with a
Databricks token, naming the endpoint as the model. The assistant's tool loop is
already written against that API.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| Keep the provider's own API, with its key as a workspace secret | The call leaves the platform, and the workspace neither grants nor sees it |
| The endpoint's OpenAI-compatible chat API | A second tool loop in another dialect, to say what the first already says |
| The MLflow deployments client | A new dependency and a new request shape; it wraps the same endpoint |
| **The endpoint's Anthropic-compatible Messages API — chosen** | One client and one tool loop for both ways; the served way changes only where the request goes and how it is signed |

## Decision

**The assistant's model is a Model Serving endpoint, reached over its
Anthropic-compatible Messages API and signed by the Databricks SDK:** as the
app's own identity on Databricks, and with the architect's own Databricks
credentials on a laptop. The bundle grants the app `CAN_QUERY` on that one
endpoint. The direct API stays for development, and no model for a laptop
without either.

## Consequences

- No model key lives in the app on Databricks; who may query the endpoint is the
  workspace's grant, and every query is the workspace's to see and limit.
- The served request carries the portable part of the API — messages, system
  prompt, tools — and none of the direct API's newer options, since the endpoint's
  model is the workspace's choice. A stronger model is a variable in the bundle.
- The SDK signs every request anew, so a token that expires is renewed rather
  than reused; the request is proven against a stand-in endpoint, and its run on
  a workspace waits with the rest of `PLAT2`.
