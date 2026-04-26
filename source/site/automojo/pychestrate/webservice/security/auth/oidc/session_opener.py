"""
.. module:: security.auth.oidc.session_opener
    :synopsis: End-to-end OIDC session-open orchestration.

The session-opener is the controller-facing entry point
that ties P18a's ``complete_oidc_callback`` and P18b's
``resolve_user_from_claims`` to the existing
``session_service.open_session``. It is the one helper a
REST controller calls when the IdP redirects the browser
back to the callback URL — every other moving part lives
behind this seam.

Flow:

1. ``complete_oidc_callback`` consumes the state row,
   exchanges the code, and validates the id_token.
2. ``resolve_user_from_claims`` matches or provisions the
   identity user from the validated claim set.
3. ``open_session`` writes the auth_sessions row and emits
   ``entity.session.opened``.
4. Returns a :class:`OidcLoginResult` carrying the session,
   the resolved user, the provisioning outcome (matched /
   upgraded / provisioned), and the optional in-app
   redirect_target.

Token-exchange and id_token-validation failures bubble as
:class:`OidcCallbackError`. Provisioning failures
(claims missing, deactivated user) bubble unchanged from
the provisioning helper. The seam is intentionally narrow
so callers don't have to understand the OIDC primitives in
isolation.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
    AuthSession,
)
from automojo.pychestrate.webservice.security.auth.oidc.flow import (
    CompleteCallbackResult,
    OidcCallbackError,
    complete_oidc_callback,
)
from automojo.pychestrate.webservice.security.auth.oidc.id_token import (
    JwksKeyResolver,
)
from automojo.pychestrate.webservice.security.auth.oidc.provisioning import (
    ClaimsMissingError,
    OidcClaimMapping,
    ProvisioningResult,
    UserDeactivatedError,
    resolve_user_from_claims,
)
from automojo.pychestrate.webservice.security.auth.oidc.token_exchange import (
    TokenExchangeFetcher,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
    open_session,
)
from automojo.pychestrate.webservice.security.auth import (
    log_events,
    metrics_emitter,
)


DEFAULT_IDLE_TIMEOUT_SECONDS: int = 1800
DEFAULT_MAX_LIFETIME_SECONDS: int = 8 * 3600


@dataclass(frozen=True)
class OidcLoginResult:
    """
        Bundle returned to the controller on a successful
        login.

        :param session: The persisted :class:`AuthSession`.
        :param callback_result: The completed callback
                                bundle (state record, token
                                response, decoded id_token).
        :param provisioning_outcome: One of
                                     ``"matched_by_external_id"``,
                                     ``"matched_by_email_upgraded"``,
                                     ``"provisioned"``.
        :param redirect_target: Optional in-app redirect
                                target the controller
                                redirects the browser to.
    """
    session: AuthSession
    callback_result: CompleteCallbackResult
    provisioning_outcome: str
    redirect_target: str = ""


def open_oidc_session(
        *,
        db_session: DbSession,
        state: str,
        code: str,
        provider_name: str,
        token_endpoint: str,
        client_id: str,
        redirect_uri: str,
        token_fetcher: TokenExchangeFetcher,
        key_resolver: JwksKeyResolver,
        expected_issuer: str,
        request_fingerprint: RequestFingerprint,
        client_secret: Optional[str] = None,
        claim_mapping: Optional[OidcClaimMapping] = None,
        idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
        max_lifetime_seconds: int = DEFAULT_MAX_LIFETIME_SECONDS,
        clock_skew: Optional[timedelta] = None,
        now: Optional[Any] = None
    ) -> OidcLoginResult:
    """
        End-to-end OIDC login orchestration.

        :param db_session: Active SQLAlchemy session.
        :param state: ``state`` query param the IdP echoed
                      back.
        :param code: ``code`` query param the IdP issued.
        :param provider_name: Name of the configured OIDC
                              provider.
        :param token_endpoint: IdP's token-endpoint URL
                               (from discovery).
        :param client_id: OIDC client id.
        :param redirect_uri: Same redirect_uri the begin
                             flow used.
        :param token_fetcher: Pluggable token-exchange
                              callable.
        :param key_resolver: Pluggable JWKS-key resolver.
        :param expected_issuer: ``iss`` value the id_token
                                must carry.
        :param request_fingerprint: Captured at session
                                    open for replay
                                    mitigation.
        :param client_secret: Optional client secret for
                              confidential clients.
        :param claim_mapping: Optional per-provider claim
                              mapping.
        :param idle_timeout_seconds: Session idle timeout.
        :param max_lifetime_seconds: Session absolute
                                     ceiling.
        :param clock_skew: Optional clock-skew override
                           applied to id_token validation.
        :param now: Optional clock override.

        :returns: :class:`OidcLoginResult`.
        :raises: OidcCallbackError on state / token-exchange
                 / id_token failure;
                 ClaimsMissingError on bad claims;
                 UserDeactivatedError on a deactivated
                 matched user.
    """
    if request_fingerprint is None:
        err_lines = ["open_oidc_session requires a request_fingerprint."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    try:
        callback = complete_oidc_callback(
            db_session=db_session,
            state=state,
            code=code,
            provider_name=provider_name,
            token_endpoint=token_endpoint,
            client_id=client_id,
            redirect_uri=redirect_uri,
            token_fetcher=token_fetcher,
            key_resolver=key_resolver,
            expected_issuer=expected_issuer,
            client_secret=client_secret,
            clock_skew=clock_skew,
            now=now,
        )

        provisioning = resolve_user_from_claims(
            db_session=db_session,
            provider_name=provider_name,
            claims=callback.id_token.payload,
            mapping=claim_mapping,
        )

        access_payload = _maybe_payload_bytes(
            token=callback.token_response.access_token,
        )
        refresh_payload = _maybe_payload_bytes(
            token=callback.token_response.refresh_token,
        )
        session = open_session(
            db_session=db_session,
            user_id=str(provisioning.user.user_id),
            provider_kind=AuthProviderKind.OIDC,
            provider_name=provider_name,
            mfa_method_name=None,
            access_token_payload=access_payload,
            refresh_token_payload=refresh_payload,
            request_fingerprint=request_fingerprint,
            idle_timeout_seconds=idle_timeout_seconds,
            max_lifetime_seconds=max_lifetime_seconds,
        )
    except Exception as login_err:
        metrics_emitter.record_login(
            db_session=db_session,
            provider_kind=AuthProviderKind.OIDC,
            provider_name=provider_name,
            outcome=metrics_emitter.LOGIN_OUTCOME_REJECTED,
        )
        log_events.emit_log_event(
            event_name=log_events.AUTH_LOGIN_REJECTED,
            payload={
                "provider_kind": AuthProviderKind.OIDC.value,
                "provider_name": provider_name,
                "reason": _resolve_login_failure_reason(err=login_err),
            },
            level=logging.WARNING,
        )
        raise

    metrics_emitter.record_login(
        db_session=db_session,
        provider_kind=AuthProviderKind.OIDC,
        provider_name=provider_name,
        outcome=metrics_emitter.LOGIN_OUTCOME_SUCCEEDED,
    )
    log_events.emit_log_event(
        event_name=log_events.AUTH_LOGIN_SUCCEEDED,
        payload={
            "provider_kind": AuthProviderKind.OIDC.value,
            "provider_name": provider_name,
            "user_id": str(provisioning.user.user_id),
            "session_id": str(session.session_id),
            "provisioning_outcome": provisioning.outcome,
        },
    )

    rtnval = OidcLoginResult(
        session=session,
        callback_result=callback,
        provisioning_outcome=provisioning.outcome,
        redirect_target=callback.redirect_target,
    )
    return rtnval


def _resolve_login_failure_reason(*, err: BaseException) -> str:
    """
        Surface the stable reason token from the M2 auth-error
        types when present; fall back to the exception class
        name otherwise. Mirrors the tracing seam's behavior so
        log + span carry the same reason for a given failure.
    """
    reason = getattr(err, "reason", None)
    if reason is None or not isinstance(reason, str) or len(reason) == 0:
        rtnval = type(err).__name__
        return rtnval
    rtnval = reason
    return rtnval


def _maybe_payload_bytes(*, token: Optional[str]) -> Optional[bytes]:
    """
        Coerce an optional token string to bytes for the
        ``access_token_enc`` / ``refresh_token_enc`` columns.
        M2 stores the bytes verbatim; M3 hardening wraps
        them with KEK encryption.
    """
    if token is None or len(token) == 0:
        return None
    rtnval = token.encode("utf-8")
    return rtnval
