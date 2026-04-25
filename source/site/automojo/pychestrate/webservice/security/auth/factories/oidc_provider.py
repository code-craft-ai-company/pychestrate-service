"""
.. module:: security.auth.factories.oidc_provider
    :synopsis: Reference ``OidcAuthProvider`` factory implementation.

The :class:`OidcAuthProvider` is the controller-facing
factory that ties the OIDC primitives shipped in P17/P18
(``begin_oidc_login``, ``complete_oidc_callback``,
``resolve_user_from_claims``, ``open_oidc_session``) into
the :class:`AuthProviderProtocol` surface used by the
``/auth/{provider_kind}/{provider_name}/login`` and
``/auth/{provider_kind}/{provider_name}/callback`` REST
controllers.

Each registered provider name maps to an
:class:`OidcProviderConfig` (held by the module-level
:mod:`provider_registry`). The factory looks the config up
on every call so a single class instance can serve every
configured IdP.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Mapping, Optional

from automojo.pychestrate.webservice.security.auth.factories.auth_provider import (
    AuthProviderProtocol,
    CompletedFlow,
    InboundFlowPayload,
    RedirectDescriptor,
)
from automojo.pychestrate.webservice.security.auth.models import AuthProviderKind
from automojo.pychestrate.webservice.security.auth.oidc.flow import (
    begin_oidc_login,
)
from automojo.pychestrate.webservice.security.auth.oidc.provider_registry import (
    OidcProviderConfig,
    get_oidc_provider_config,
)
from automojo.pychestrate.webservice.security.auth.oidc.session_opener import (
    OidcLoginResult,
    open_oidc_session,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
)


class OidcAuthProvider(AuthProviderProtocol):
    """
        Reference :class:`AuthProviderProtocol` implementation
        for OIDC authorization-code-with-PKCE.

        Lookup of per-provider configuration goes through
        :func:`get_oidc_provider_config`; flow execution goes
        through :func:`begin_oidc_login` for the begin half and
        :func:`open_oidc_session` for the complete half.
    """

    factory_protocol_name: str = "auth_provider"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def provider_kind(cls) -> AuthProviderKind:
        rtnval = AuthProviderKind.OIDC
        return rtnval

    @classmethod
    def build_begin_login_redirect(
            cls,
            *,
            provider_name: str,
            redirect_target: str
        ) -> RedirectDescriptor:
        """
            Generate PKCE / state / nonce, persist the
            ``auth_oidc_state`` row, and return the IdP
            authorization URL the controller redirects to.
        """
        config = get_oidc_provider_config(provider_name=provider_name)
        db_session = config.session_factory()
        try:
            redirect = begin_oidc_login(
                db_session=db_session,
                provider_name=provider_name,
                authorization_endpoint=config.authorization_endpoint,
                client_id=config.client_id,
                redirect_uri=config.redirect_uri,
                scopes=config.scopes,
                redirect_target=redirect_target,
            )
        finally:
            db_session.close()
        rtnval = RedirectDescriptor(
            target_url=redirect.authorization_url,
            state_token=redirect.state,
        )
        return rtnval

    @classmethod
    def complete_callback(
            cls,
            *,
            provider_name: str,
            inbound: InboundFlowPayload
        ) -> CompletedFlow:
        """
            Consume the IdP callback. ``inbound.fields`` must
            carry ``state``, ``code``, and
            ``request_fingerprint``. An optional
            ``db_session`` field overrides the registered
            ``session_factory`` (used by tests so the in-memory
            engine doesn't get a fresh disconnected session).
        """
        config = get_oidc_provider_config(provider_name=provider_name)
        state, code, fingerprint, supplied_session = _read_inbound(
            inbound=inbound,
        )
        db_session = (
            supplied_session if supplied_session is not None
            else config.session_factory()
        )
        owns_session = supplied_session is None
        try:
            login_result = open_oidc_session(
                db_session=db_session,
                state=state,
                code=code,
                provider_name=provider_name,
                token_endpoint=config.token_endpoint,
                client_id=config.client_id,
                redirect_uri=config.redirect_uri,
                token_fetcher=config.token_fetcher,
                key_resolver=config.key_resolver,
                expected_issuer=config.expected_issuer,
                request_fingerprint=fingerprint,
                client_secret=config.client_secret,
            )
        finally:
            if owns_session is True:
                db_session.close()
        rtnval = _build_completed_flow(
            provider_name=provider_name,
            login_result=login_result,
        )
        return rtnval


def _read_inbound(
        *, inbound: InboundFlowPayload
    ) -> "tuple":
    if inbound is None:
        err_lines = ["OidcAuthProvider.complete_callback requires an inbound."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    fields = inbound.fields if inbound.fields is not None else {}
    state = str(fields.get("state", "") or "")
    code = str(fields.get("code", "") or "")
    fingerprint = fields.get("request_fingerprint", None)
    db_session = fields.get("db_session", None)
    if len(state) == 0:
        err_lines = ["OidcAuthProvider inbound is missing 'state'."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if len(code) == 0:
        err_lines = ["OidcAuthProvider inbound is missing 'code'."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if not isinstance(fingerprint, RequestFingerprint):
        err_lines = [
            "OidcAuthProvider inbound 'request_fingerprint' "
            "must be a RequestFingerprint.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    rtnval = (state, code, fingerprint, db_session)
    return rtnval


def _build_completed_flow(
        *, provider_name: str, login_result: OidcLoginResult
    ) -> CompletedFlow:
    session = login_result.session
    access_payload: Optional[bytes] = None
    if session.access_token_enc is not None:
        access_payload = bytes(session.access_token_enc)
    refresh_payload: Optional[bytes] = None
    if session.refresh_token_enc is not None:
        refresh_payload = bytes(session.refresh_token_enc)
    rtnval = CompletedFlow(
        user_id=str(session.user_id),
        provider_kind=AuthProviderKind.OIDC,
        provider_name=provider_name,
        access_token_payload=access_payload,
        refresh_token_payload=refresh_payload,
        mfa_method_name=session.mfa_method_name,
    )
    return rtnval
