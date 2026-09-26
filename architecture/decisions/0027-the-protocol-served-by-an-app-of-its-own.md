# 0027 — The Model Context Protocol, served by an app of its own and read with its own library

_[← Decisions](./README.md)_

**Status:** Adopted 2026-09-26, the agent's call (initiative 26), within the Requester's
Understanding. **Touches:** `ACMP16`, `ACMP17`, `TSVC8`, `NODE2`, `ART4`, `ART6`, `GAP7`, `GAP28`.

## Context

Initiative 26 serves the model's read tools to other agents over the Model Context Protocol and
has the assistant read the enterprise's systems over it. The protocol's HTTP transport is an
asynchronous (ASGI) server; the web application is a Dash (Flask, WSGI) process served by
gunicorn, one worker with threads, sized for the 15-second stop Databricks Apps allows. Both
halves need a client and a server that follow a protocol still moving.

## Options considered

| Option | Why not (or why) |
| ------ | ---------------- |
| **Mount the protocol inside the web application** | Needs the web process moved to an ASGI server with the WSGI app wrapped, which changes how the application every reader uses starts and stops, for an endpoint only agents call |
| **Speak the protocol by hand** | JSON-RPC, sessions, streaming and version negotiation written and kept current here, for no gain over the library its authors maintain |
| **The protocol's own Python library, the tool server as an app of its own** (chosen) | One library serves (`ea mcp`, stdio on a laptop, streamable HTTP at `/mcp` on the platform) and reads (the connected systems); the bundle deploys the tool server as a second app on the same store and the same sign-in, and the web application is untouched |

## Decision

The Model Context Protocol's Python library (`mcp` in `pyproject.toml`) serves the tool server
and reads the connected systems. On Databricks the tool server is a second app in the bundle,
`ea-tool-server`, run as `ea mcp --http` with the same database resource and no serving endpoint.

## Consequences

- An agent connects to the tool server's own address, not the web application's; both apps are
  started by `make deploy-run`.
- The library is young and moves fast: its version is pinned in `uv.lock`, and the tests drive
  both halves in-process, so an upgrade that changes its surface fails the suite, not a reader.
- The assistant's loop is synchronous: each read of a connected system runs on its own event
  loop, which a request thread can afford at a handful of reads per answer and would not at
  many.
