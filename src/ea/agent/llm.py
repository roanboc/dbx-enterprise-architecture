"""The assistant's model: how Ask and Propose reach it (decision 0023).

- `databricks` — a Model Serving endpoint, reached over the platform's Anthropic-compatible
  Messages API at `<workspace>/serving-endpoints/anthropic`. The request is signed as the app's
  own identity on Databricks and with the architect's own Databricks credentials on a laptop:
  the SDK's unified authentication decides which, and refreshes the token as it expires. The
  model named in a request is the endpoint's name.
- `anthropic` — the Messages API directly, with an API key: for development.
- `stub` — no model: the reader of a template's tables, and the rule-based questions.

`auto` picks the served endpoint when one is configured, the direct API when a key is present,
and no model otherwise. Both hosted ways use the same client and the same tool loop; only
where the request goes, how it is signed, and which options it carries differ. The served
request carries the portable part of the Messages API — messages, system, tools — and none of
the direct API's newer options, because the endpoint's model is the workspace's choice.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ea.config import Settings

SERVED_PATH = "/serving-endpoints/anthropic"


class ModelUnavailable(RuntimeError):
    """The configured model cannot be reached: said plainly, so the page or the command line shows it."""


@dataclass
class ModelClient:
    client: Any  # an `anthropic.Anthropic`
    model: str  # the model id, or the serving endpoint's name
    provider: str  # databricks | anthropic
    #: Whether requests may carry the direct API's newer options (adaptive thinking, effort,
    #: beta fallbacks). Not on a served endpoint, whose model the workspace chooses.
    extended: bool


def choice(settings: Settings) -> str:
    """Which way `settings` points at: databricks, anthropic or stub."""
    wanted = (settings.agent_provider or "auto").lower()
    if wanted != "auto":
        return wanted
    if settings.agent_endpoint:
        return "databricks"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    return "stub"


def model_client(settings: Settings) -> ModelClient | None:
    """The client the settings name, or None for no model.

    Under `auto`, a way that cannot be set up (no SDK, no credentials) falls back to no model,
    so the application stays usable; named explicitly, it raises `ModelUnavailable`.
    """
    way = choice(settings)
    explicit = (settings.agent_provider or "auto").lower() != "auto"
    try:
        if way == "databricks":
            return served_client(settings.agent_endpoint, settings.databricks_host)
        if way == "anthropic":
            import anthropic

            return ModelClient(anthropic.Anthropic(), settings.agent_model, "anthropic", True)
    except Exception as exc:  # noqa: BLE001 — missing SDK or credentials
        if explicit:
            raise ModelUnavailable(str(exc)) from exc
    return None


def served_client(
    endpoint: str, host: str = "", authenticate: Callable[[], dict[str, str]] | None = None
) -> ModelClient:
    """A client for a Model Serving endpoint.

    `authenticate` returns the headers that sign one request; by default the Databricks SDK's,
    which reads the app's service principal on the platform and the architect's own profile
    or token on a laptop. `host` defaults to the SDK's.
    """
    import anthropic
    import httpx2  # the SDK's own HTTP library: an auth flow handed to it must be one of its

    if not endpoint:
        raise ModelUnavailable("no serving endpoint is configured: set EA_AGENT_ENDPOINT")
    if authenticate is None or not host:
        try:
            from databricks.sdk.core import Config
        except ImportError as exc:
            raise ModelUnavailable(
                "the Databricks SDK is not installed: run with the databricks extra "
                "(uv run --extra databricks …)"
            ) from exc
        config = Config(host=host) if host else Config()
        authenticate = authenticate or config.authenticate
        host = host or config.host
    base = host.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base

    class PlatformAuth(httpx2.Auth):
        """Signs each request as the platform says, so an expired token is renewed, not reused."""

        def auth_flow(self, request):
            request.headers.pop("x-api-key", None)
            request.headers.update(authenticate())
            yield request

    client = anthropic.Anthropic(
        api_key="unused",  # the platform's token signs the request; the SDK insists on a key
        base_url=base + SERVED_PATH,
        http_client=anthropic.DefaultHttpxClient(auth=PlatformAuth()),
    )
    return ModelClient(client, endpoint, "databricks", False)


def request_options(mc: ModelClient) -> dict[str, Any]:
    """What a request adds beyond messages, system and tools, for this client."""
    if not mc.extended:
        return {}
    return {"thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}}


def failure(mc: ModelClient, exc: Exception) -> str:
    """A model error in the words a person reads, naming where the request went."""
    import anthropic

    where = f"the serving endpoint {mc.model!r}" if mc.provider == "databricks" else "the model API"
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        hint = (
            "check the app may query the endpoint (CAN_QUERY), or your own Databricks sign-in"
            if mc.provider == "databricks"
            else "check ANTHROPIC_API_KEY"
        )
        return f"{where} refused the request ({exc.status_code}); {hint}."
    if isinstance(exc, anthropic.NotFoundError):
        return f"{where} was not found ({exc.status_code}); check EA_AGENT_ENDPOINT names an endpoint of this workspace."
    if isinstance(exc, anthropic.RateLimitError):
        return f"Rate limited by {where} ({exc.status_code}); try again shortly."
    if isinstance(exc, anthropic.APIStatusError):
        return f"{where} answered with error {exc.status_code}: {exc.message}"
    if isinstance(exc, anthropic.APIConnectionError):
        return f"Could not reach {where}: {exc}"
    return f"{where} failed: {exc}"
