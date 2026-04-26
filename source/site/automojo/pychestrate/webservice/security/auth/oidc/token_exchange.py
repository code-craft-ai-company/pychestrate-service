"""
.. module:: security.auth.oidc.token_exchange
    :synopsis: Authorization-code → token-set exchange.

The IdP returns a one-shot authorization ``code`` that the
backend redeems against the token endpoint for an
``id_token`` (and usually an ``access_token`` and
``refresh_token``). This module ships the orchestration of
that swap; the actual HTTP call is pluggable so production
uses ``urllib`` and tests hand in a deterministic stub.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from automojo.pychestrate.webservice.security.auth.tracing import (
    SPAN_OIDC_TOKEN_EXCHANGE,
    start_span,
)


@dataclass(frozen=True)
class TokenExchangeRequest:
    """
        Inputs the token-exchange caller assembles for the
        IdP's token endpoint.

        :param token_endpoint: IdP's token endpoint URL
                               (from discovery).
        :param client_id: OIDC client id.
        :param client_secret: Optional client secret. PKCE
                              flows can omit when the IdP
                              supports public clients.
        :param redirect_uri: Same redirect_uri the begin
                             flow used; the IdP echoes it
                             back to confirm.
        :param code: Authorization code from the IdP
                     redirect.
        :param pkce_verifier: PKCE verifier recovered from
                              the consumed
                              ``auth_oidc_state`` row.
    """
    token_endpoint: str
    client_id: str
    redirect_uri: str
    code: str
    pkce_verifier: str
    client_secret: Optional[str] = None


@dataclass(frozen=True)
class TokenExchangeResponse:
    """
        Subset of the IdP's token-endpoint response we care
        about.

        :param id_token: Compact JWS the validator consumes.
        :param access_token: Optional bearer token for
                             downstream API calls.
        :param refresh_token: Optional refresh token for
                              session refresh.
        :param token_type: Almost always ``"Bearer"``.
        :param expires_in_seconds: Lifetime hint of the
                                   access token.
        :param raw: Original JSON payload preserved for
                    callers that need extra fields.
    """
    id_token: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in_seconds: Optional[int] = None
    raw: Mapping[str, Any] = field(default_factory=dict)


TokenExchangeFetcher = Callable[
    [TokenExchangeRequest], "TokenExchangeRawResponse",
]


@dataclass(frozen=True)
class TokenExchangeRawResponse:
    """
        Caller-side response shape: the raw JSON dict the
        IdP returned plus the HTTP status. The orchestrator
        validates fields and packages a
        :class:`TokenExchangeResponse` after.
    """
    status_code: int
    payload: Mapping[str, Any] = field(default_factory=dict)


class TokenExchangeError(Exception):
    """
        Raised when the token-exchange call fails. The
        ``reason`` token is stable so callers can branch.

        Reasons:

        * ``http_error`` — non-2xx HTTP status.
        * ``payload_invalid`` — missing ``id_token`` or
          malformed JSON.
        * ``provider_rejected`` — IdP returned a ``"error"``
          field per RFC 6749.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason if len(detail) == 0 else "{}: {}".format(reason, detail))
        self.reason: str = reason
        self.detail: str = detail
        return


def exchange_code_for_tokens(
        *,
        request: TokenExchangeRequest,
        fetcher: TokenExchangeFetcher
    ) -> TokenExchangeResponse:
    """
        Run the authorization-code → token swap.

        :param request: :class:`TokenExchangeRequest`.
        :param fetcher: Pluggable callable that performs the
                        HTTP POST to ``request.token_endpoint``.
                        Production uses ``urllib`` + form
                        encoding; tests hand in a
                        deterministic stub.

        :returns: :class:`TokenExchangeResponse`.
        :raises: TokenExchangeError on any failure.
    """
    if request is None:
        err_lines = ["exchange_code_for_tokens requires a request."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if fetcher is None:
        err_lines = ["exchange_code_for_tokens requires a fetcher."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    with start_span(
        name=SPAN_OIDC_TOKEN_EXCHANGE,
        attributes={"client_id": request.client_id},
    ) as span:
        raw = fetcher(request)
        if raw is None:
            raise TokenExchangeError(
                "payload_invalid", "fetcher returned None",
            ) from None
        span.set_attribute(key="status_code", value=raw.status_code)
        if raw.status_code < 200 or raw.status_code >= 300:
            provider_error = ""
            if isinstance(raw.payload, dict):
                provider_error = str(raw.payload.get("error", ""))
            raise TokenExchangeError(
                "http_error",
                "status={} provider_error={!r}".format(
                    raw.status_code, provider_error,
                ),
            ) from None
        if not isinstance(raw.payload, dict):
            raise TokenExchangeError(
                "payload_invalid", "payload is not an object",
            ) from None
        if "error" in raw.payload:
            raise TokenExchangeError(
                "provider_rejected",
                "{}: {}".format(
                    raw.payload.get("error"),
                    raw.payload.get("error_description", ""),
                ),
            ) from None
        id_token = raw.payload.get("id_token")
        if id_token is None or not isinstance(id_token, str) or len(id_token) == 0:
            raise TokenExchangeError(
                "payload_invalid", "id_token missing or non-string",
            ) from None
        access_token = raw.payload.get("access_token")
        if access_token is not None and not isinstance(access_token, str):
            raise TokenExchangeError(
                "payload_invalid", "access_token must be a string",
            ) from None
        refresh_token = raw.payload.get("refresh_token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise TokenExchangeError(
                "payload_invalid", "refresh_token must be a string",
            ) from None
        expires_in = raw.payload.get("expires_in")
        expires_in_seconds: Optional[int] = None
        if expires_in is not None:
            try:
                expires_in_seconds = int(expires_in)
            except (TypeError, ValueError):
                raise TokenExchangeError(
                    "payload_invalid", "expires_in not an integer",
                ) from None
        span.set_attribute(
            key="refresh_token_present", value=refresh_token is not None,
        )
        rtnval = TokenExchangeResponse(
            id_token=id_token,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=str(raw.payload.get("token_type", "Bearer")),
            expires_in_seconds=expires_in_seconds,
            raw=dict(raw.payload),
        )
    return rtnval
