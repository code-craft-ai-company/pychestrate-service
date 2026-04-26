"""
.. module:: security.auth.oidc.flow
    :synopsis: OIDC begin-login orchestration.

The ``begin_oidc_login`` entry point composes the PKCE pair
and the state / nonce tokens, persists the
``auth_oidc_state`` row, and returns the authorization URL
the controller redirects the browser to.

The matching ``complete_oidc_callback`` lands in a follow-on
slice — it consumes the state row, validates the IdP's
``id_token``, and opens an ``auth_sessions`` row through
the existing session_service.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Mapping, Optional, Tuple
from urllib import parse as urlparse

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.security.auth.oidc.pkce import (
    PkcePair,
    generate_pkce_pair,
)
from automojo.pychestrate.webservice.security.auth.oidc.state import (
    DEFAULT_STATE_TTL,
    generate_nonce,
    generate_state_token,
    insert_state,
)


@dataclass(frozen=True)
class BeginLoginRedirect:
    """
        The output the controller redirects the browser to.

        :param authorization_url: Fully-formed authorization
                                  endpoint URL with every
                                  query parameter folded in.
        :param state: State token the IdP echoes back; the
                      callback path passes this to
                      ``consume_state`` to retrieve the
                      original PKCE verifier + nonce.
        :param nonce: Nonce the callback path uses to
                      validate the returned ``id_token``.
        :param pkce: PkcePair captured for tests and audit;
                     production controllers only need the
                     state value.
    """
    authorization_url: str
    state: str
    nonce: str
    pkce: PkcePair


def begin_oidc_login(
        *,
        db_session: DbSession,
        provider_name: str,
        authorization_endpoint: str,
        client_id: str,
        redirect_uri: str,
        scopes: Tuple[str, ...] = ("openid", "email", "profile"),
        redirect_target: str = "",
        ttl: Optional[timedelta] = None,
        extra_params: Optional[Mapping[str, str]] = None
    ) -> BeginLoginRedirect:
    """
        Generate PKCE + state + nonce, persist the
        ``auth_oidc_state`` row, and assemble the
        authorization URL.

        :param db_session: Active SQLAlchemy session.
        :param provider_name: Name of the registered OIDC
                              provider (e.g.
                              ``"google-workspace"``).
        :param authorization_endpoint: IdP's authorization
                                       endpoint URL (from
                                       discovery).
        :param client_id: OIDC client id.
        :param redirect_uri: Callback URL the IdP redirects
                             back to.
        :param scopes: Tuple of scope strings; defaults to
                       ``openid email profile``.
        :param redirect_target: Optional in-app target the
                                callback path will
                                redirect the user to after
                                a successful login.
        :param ttl: Optional state-row TTL override.
        :param extra_params: Optional caller-supplied query
                             parameters to fold into the
                             authorization URL.

        :returns: :class:`BeginLoginRedirect`.
        :raises: ValueError on empty provider_name /
                 authorization_endpoint / client_id /
                 redirect_uri.
    """
    if provider_name is None or len(provider_name) == 0:
        err_lines = [
            "begin_oidc_login requires a non-empty provider_name.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if authorization_endpoint is None or len(authorization_endpoint) == 0:
        err_lines = [
            "begin_oidc_login requires a non-empty authorization_endpoint.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if client_id is None or len(client_id) == 0:
        err_lines = ["begin_oidc_login requires a non-empty client_id."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if redirect_uri is None or len(redirect_uri) == 0:
        err_lines = ["begin_oidc_login requires a non-empty redirect_uri."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if scopes is None or len(scopes) == 0:
        err_lines = ["begin_oidc_login requires at least one scope."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    pkce = generate_pkce_pair()
    state = generate_state_token()
    nonce = generate_nonce()

    insert_state(
        db_session=db_session,
        state=state,
        nonce=nonce,
        pkce_verifier=pkce.verifier.encode("ascii"),
        provider_name=provider_name,
        redirect_target=redirect_target or "",
        ttl=ttl if ttl is not None else DEFAULT_STATE_TTL,
    )

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "nonce": nonce,
        "code_challenge": pkce.challenge,
        "code_challenge_method": pkce.method,
    }
    if extra_params is not None:
        for key, value in extra_params.items():
            if key in params:
                continue
            params[key] = value

    authorization_url = _build_authorization_url(
        endpoint=authorization_endpoint, params=params,
    )
    rtnval = BeginLoginRedirect(
        authorization_url=authorization_url,
        state=state,
        nonce=nonce,
        pkce=pkce,
    )
    return rtnval


def _build_authorization_url(
        *,
        endpoint: str,
        params: Mapping[str, str]
    ) -> str:
    """
        Append ``params`` to ``endpoint`` as a query string,
        preserving any existing query already on the
        endpoint URL (some IdPs include implementation
        params).
    """
    parsed = urlparse.urlparse(endpoint)
    existing = urlparse.parse_qsl(parsed.query, keep_blank_values=True)
    merged = list(existing)
    for key, value in params.items():
        merged.append((key, value))
    new_query = urlparse.urlencode(merged)
    rebuilt = parsed._replace(query=new_query)
    rtnval = urlparse.urlunparse(rebuilt)
    return rtnval


# ----------------------------------------------------------------
# complete_oidc_callback
# ----------------------------------------------------------------


from automojo.pychestrate.webservice.security.auth.oidc.id_token import (
    DecodedIdToken,
    IdTokenValidationError,
    JwksKey,
    JwksKeyResolver,
    ValidationParams,
    validate_id_token,
)
from automojo.pychestrate.webservice.security.auth.oidc.state import (
    StateRecord,
    consume_state,
)
from automojo.pychestrate.webservice.security.auth.oidc.token_exchange import (
    TokenExchangeError,
    TokenExchangeFetcher,
    TokenExchangeRequest,
    TokenExchangeResponse,
    exchange_code_for_tokens,
)
from automojo.pychestrate.webservice.security.auth.tracing import (
    SPAN_OIDC_CALLBACK,
    start_span,
)


class OidcCallbackError(Exception):
    """
        Raised when complete_oidc_callback fails. ``reason``
        token is stable so the controller can log + branch
        without leaking detail to the client.

        Reasons:

        * ``state_unknown`` — IdP returned a state token the
          server never issued (replay or forged callback).
        * ``provider_mismatch`` — the consumed state row
          declared a different provider than the caller's
          arguments.
        * ``token_exchange_failed`` — code-for-token swap
          failed; ``cause`` carries the
          :class:`TokenExchangeError` reason.
        * ``id_token_invalid`` — id_token validation failed;
          ``cause`` carries the
          :class:`IdTokenValidationError` reason.
    """

    def __init__(
            self,
            reason: str,
            detail: str = "",
            cause: Optional[str] = None
        ) -> None:
        message = reason if len(detail) == 0 else "{}: {}".format(reason, detail)
        super().__init__(message)
        self.reason: str = reason
        self.detail: str = detail
        self.cause: Optional[str] = cause
        return


@dataclass(frozen=True)
class CompleteCallbackResult:
    """
        Successful callback bundle.

        :param state_record: Consumed
                             :class:`StateRecord` (the
                             state row was deleted on the
                             way out).
        :param token_response: IdP token-endpoint response.
        :param id_token: Decoded id_token bundle the
                         downstream session-opener consumes.
        :param redirect_target: Optional in-app redirect
                                target captured at begin
                                time.
    """
    state_record: StateRecord
    token_response: TokenExchangeResponse
    id_token: DecodedIdToken
    redirect_target: str = ""


def complete_oidc_callback(
        *,
        db_session,
        state: str,
        code: str,
        provider_name: str,
        token_endpoint: str,
        client_id: str,
        redirect_uri: str,
        token_fetcher: TokenExchangeFetcher,
        key_resolver: JwksKeyResolver,
        expected_issuer: str,
        client_secret: Optional[str] = None,
        clock_skew: Optional[Any] = None,
        now: Optional[Any] = None
    ) -> CompleteCallbackResult:
    """
        Run the post-redirect half of the OIDC flow. Steps:

        1. Atomically consume the ``auth_oidc_state`` row by
           ``state``. Returns ``None`` for unknown / expired
           states; the orchestrator surfaces that as
           ``OidcCallbackError(reason='state_unknown')``.
        2. Confirm the consumed row's provider matches the
           caller's ``provider_name`` so a callback can't
           replay a state issued for a different provider.
        3. Run the code-for-token swap through
           ``exchange_code_for_tokens``.
        4. Validate the returned ``id_token`` against the
           configured issuer / client_id (audience) /
           recovered nonce.
        5. Return a :class:`CompleteCallbackResult` carrying
           the decoded id_token, the token response, the
           consumed state record, and the optional redirect
           target the controller redirects to.

        :raises: OidcCallbackError with stable reason
                 tokens.
    """
    if state is None or len(state) == 0:
        raise OidcCallbackError(
            "state_unknown", "missing state",
        ) from None
    if code is None or len(code) == 0:
        raise OidcCallbackError(
            "id_token_invalid", "missing code",
        ) from None

    with start_span(
        name=SPAN_OIDC_CALLBACK,
        attributes={"provider_name": provider_name},
    ) as span:
        state_record = consume_state(db_session=db_session, state=state)
        if state_record is None:
            raise OidcCallbackError(
                "state_unknown",
                "no auth_oidc_state row matched state",
            ) from None
        if state_record.provider_name != provider_name:
            raise OidcCallbackError(
                "provider_mismatch",
                "state.provider={!r} caller.provider={!r}".format(
                    state_record.provider_name, provider_name,
                ),
            ) from None

        request = TokenExchangeRequest(
            token_endpoint=token_endpoint,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code=code,
            pkce_verifier=state_record.pkce_verifier.decode("ascii"),
        )
        try:
            token_response = exchange_code_for_tokens(
                request=request, fetcher=token_fetcher,
            )
        except TokenExchangeError as exchange_err:
            raise OidcCallbackError(
                "token_exchange_failed",
                exchange_err.detail,
                cause=exchange_err.reason,
            ) from None

        validation_params = ValidationParams(
            expected_issuer=expected_issuer,
            expected_audience=client_id,
            expected_nonce=state_record.nonce,
            clock_skew=(
                clock_skew if clock_skew is not None
                else _default_clock_skew()
            ),
            now=now,
        )
        try:
            decoded = validate_id_token(
                token=token_response.id_token,
                params=validation_params,
                key_resolver=key_resolver,
            )
        except IdTokenValidationError as token_err:
            raise OidcCallbackError(
                "id_token_invalid",
                token_err.detail,
                cause=token_err.reason,
            ) from None

        span.set_attribute(
            key="audience", value=client_id,
        )
        rtnval = CompleteCallbackResult(
            state_record=state_record,
            token_response=token_response,
            id_token=decoded,
            redirect_target=state_record.redirect_target or "",
        )
    return rtnval


def _default_clock_skew():
    from automojo.pychestrate.webservice.security.auth.oidc.id_token import (
        DEFAULT_CLOCK_SKEW,
    )
    return DEFAULT_CLOCK_SKEW
