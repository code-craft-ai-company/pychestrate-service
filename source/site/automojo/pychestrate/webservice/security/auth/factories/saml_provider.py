"""
.. module:: security.auth.factories.saml_provider
    :synopsis: Reference ``SamlAuthProvider`` factory implementation.

The :class:`SamlAuthProvider` is the controller-facing
factory that ties P20a's metadata cache, P20b's assertion
validator, and P20c's replay cache into the
:class:`AuthProviderProtocol` surface used by the
``/auth/saml/{provider_name}/login`` and
``/auth/saml/{provider_name}/acs`` REST controllers.

Each registered provider name maps to a
:class:`SamlProviderConfig` (held by the module-level
:mod:`saml.provider_registry`). The factory looks the
config up on every call so a single class instance can
serve every configured IdP.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import logging
import os
import secrets

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Tuple
from urllib import parse as urlparse

from automojo.pychestrate.webservice.security.auth.factories.auth_provider import (
    AuthProviderProtocol,
    CompletedFlow,
    InboundFlowPayload,
    RedirectDescriptor,
)
from automojo.pychestrate.webservice.security.auth.models import AuthProviderKind
from automojo.pychestrate.webservice.security.auth.saml.assertion import (
    SamlValidationParams,
    ValidatedSamlAssertion,
    validate_saml_assertion,
)
from automojo.pychestrate.webservice.security.auth.saml.metadata import (
    SamlIdpMetadata,
    current_trust_set,
    refresh_metadata_document,
)
from automojo.pychestrate.webservice.security.auth.saml.provider_registry import (
    SamlProviderConfig,
    get_saml_provider_config,
)
from automojo.pychestrate.webservice.security.auth.saml.replay_cache import (
    SamlReplayDetectedError,
    record_response_id,
)
from automojo.pychestrate.webservice.security.auth import (
    log_events,
    metrics_emitter,
)


class SamlAuthProvider(AuthProviderProtocol):
    """
        Reference :class:`AuthProviderProtocol` implementation
        for SAML 2.0.

        Lookup of per-provider configuration goes through
        :func:`get_saml_provider_config`; metadata refresh
        goes through :func:`refresh_metadata_document`;
        assertion validation goes through
        :func:`validate_saml_assertion`; replay defense goes
        through :func:`record_response_id`.
    """

    factory_protocol_name: str = "auth_provider"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def provider_kind(cls) -> AuthProviderKind:
        rtnval = AuthProviderKind.SAML
        return rtnval

    @classmethod
    def build_begin_login_redirect(
            cls,
            *,
            provider_name: str,
            redirect_target: str
        ) -> RedirectDescriptor:
        """
            Refresh the IdP metadata if necessary, build an
            AuthnRequest id, and return the SSO redirect URL
            with the id stashed in ``state_token`` so the
            ACS can match the assertion's ``InResponseTo``.
        """
        config = get_saml_provider_config(provider_name=provider_name)
        metadata = _ensure_metadata(config=config)
        request_id = _new_authn_request_id()
        sso_url = _build_sso_redirect_url(
            sso_endpoint=metadata.sso_redirect_url,
            relay_state=redirect_target,
            request_id=request_id,
        )
        rtnval = RedirectDescriptor(
            target_url=sso_url,
            state_token=request_id,
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
            Consume the IdP ACS callback. ``inbound.fields``
            must carry ``saml_response`` (the base64-decoded
            SAMLResponse XML bytes) and may carry
            ``expected_in_response_to`` (the AuthnRequest id
            from begin time, or None for IdP-initiated
            flows). An optional ``db_session`` field
            overrides the registered ``session_factory`` so
            tests can keep the in-memory engine bound to a
            single session.
        """
        config = get_saml_provider_config(provider_name=provider_name)
        saml_response_xml, in_response_to, supplied_session = (
            _read_inbound(inbound=inbound)
        )
        # Open a session early so login-outcome metrics can
        # land regardless of the failure point. The session
        # owns its commit / close semantics — the validate /
        # replay-record both use it.
        db_session = (
            supplied_session if supplied_session is not None
            else config.session_factory()
        )
        owns_session = supplied_session is None
        try:
            try:
                metadata = _ensure_metadata(config=config)
                params = SamlValidationParams(
                    expected_issuer=metadata.entity_id,
                    expected_audience=config.sp_entity_id,
                    expected_recipient=config.acs_url,
                    trusted_certificates=metadata.signing_certificates,
                    expected_in_response_to=in_response_to,
                    signature_verifier=config.signature_verifier,
                )
                validated = validate_saml_assertion(
                    saml_response_xml=saml_response_xml, params=params,
                )
                # Replay-cache record happens AFTER assertion validation
                # so a forged Response/@ID for an invalid assertion
                # can't poison the cache.
                response_id = _extract_response_id(
                    saml_response_xml=saml_response_xml,
                )
                not_on_or_after = _extract_conditions_not_on_or_after(
                    validated=validated,
                )
                record_response_id(
                    db_session=db_session,
                    response_id=response_id,
                    not_on_or_after=not_on_or_after,
                )
            except Exception as login_err:
                metrics_emitter.record_login(
                    db_session=db_session,
                    provider_kind=AuthProviderKind.SAML,
                    provider_name=provider_name,
                    outcome=metrics_emitter.LOGIN_OUTCOME_REJECTED,
                )
                log_events.emit_log_event(
                    event_name=log_events.AUTH_LOGIN_REJECTED,
                    payload={
                        "provider_kind": AuthProviderKind.SAML.value,
                        "provider_name": provider_name,
                        "reason": _resolve_saml_login_failure_reason(
                            err=login_err,
                        ),
                    },
                    level=logging.WARNING,
                )
                raise
            metrics_emitter.record_login(
                db_session=db_session,
                provider_kind=AuthProviderKind.SAML,
                provider_name=provider_name,
                outcome=metrics_emitter.LOGIN_OUTCOME_SUCCEEDED,
            )
            log_events.emit_log_event(
                event_name=log_events.AUTH_LOGIN_SUCCEEDED,
                payload={
                    "provider_kind": AuthProviderKind.SAML.value,
                    "provider_name": provider_name,
                    "user_id": validated.name_id,
                    "issuer": validated.issuer,
                },
            )
        finally:
            if owns_session is True:
                db_session.close()
        rtnval = CompletedFlow(
            user_id=validated.name_id,
            provider_kind=AuthProviderKind.SAML,
            provider_name=provider_name,
            access_token_payload=None,
            refresh_token_payload=None,
            mfa_method_name=None,
        )
        return rtnval


def _resolve_saml_login_failure_reason(*, err: BaseException) -> str:
    reason = getattr(err, "reason", None)
    if reason is None or not isinstance(reason, str) or len(reason) == 0:
        rtnval = type(err).__name__
        return rtnval
    rtnval = reason
    return rtnval


def _ensure_metadata(
        *, config: SamlProviderConfig
    ) -> SamlIdpMetadata:
    cached = current_trust_set(provider_name=config.provider_name)
    if cached is not None:
        return cached
    rtnval = refresh_metadata_document(
        provider_name=config.provider_name,
        metadata_url=config.metadata_url,
        fetcher=config.metadata_fetcher,
    )
    return rtnval


def _new_authn_request_id() -> str:
    # SAML AuthnRequest IDs must be XML-NCName values; we
    # prefix with '_' so a leading-digit token_hex value is
    # still a valid NCName.
    rtnval = "_" + secrets.token_hex(16)
    return rtnval


def _build_sso_redirect_url(
        *,
        sso_endpoint: str,
        relay_state: str,
        request_id: str
    ) -> str:
    """
        Build the IdP redirect URL with a synthetic
        ``SAMLRequest`` query parameter and a ``RelayState``
        carrying the redirect_target so the ACS can return
        the user to where they came from.

        For the M2 reference impl we deflate-and-base64
        encode a minimal AuthnRequest envelope. The
        AuthnRequest is unsigned (the
        ``WantAuthnRequestsSigned`` honoring path lands in
        M3 hardening); operators that need signed requests
        wire a signing fetcher on the provider config.
    """
    import zlib

    authn_request_xml = (
        '<samlp:AuthnRequest '
        'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        'ID="{}" '
        'Version="2.0" '
        'IssueInstant="{}" '
        'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">'
        '<saml:Issuer>pychestrate-saml-sp</saml:Issuer>'
        '</samlp:AuthnRequest>'
    ).format(
        request_id,
        datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    deflated = zlib.compress(authn_request_xml.encode("utf-8"))[2:-4]
    encoded = base64.b64encode(deflated).decode("ascii")
    parsed = urlparse.urlparse(sso_endpoint)
    existing = list(urlparse.parse_qsl(
        parsed.query, keep_blank_values=True,
    ))
    existing.append(("SAMLRequest", encoded))
    if relay_state is not None and len(relay_state) > 0:
        existing.append(("RelayState", relay_state))
    new_query = urlparse.urlencode(existing)
    rebuilt = parsed._replace(query=new_query)
    rtnval = urlparse.urlunparse(rebuilt)
    return rtnval


def _read_inbound(
        *, inbound: InboundFlowPayload
    ) -> Tuple[bytes, Optional[str], Any]:
    if inbound is None:
        err_lines = ["SamlAuthProvider.complete_callback requires inbound."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    fields = inbound.fields if inbound.fields is not None else {}
    saml_response = fields.get("saml_response", None)
    if saml_response is None or len(saml_response) == 0:
        err_lines = [
            "SamlAuthProvider inbound is missing 'saml_response' bytes.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if isinstance(saml_response, str):
        saml_response = saml_response.encode("utf-8")
    in_response_to = fields.get("expected_in_response_to", None)
    db_session = fields.get("db_session", None)
    rtnval = (saml_response, in_response_to, db_session)
    return rtnval


def _extract_response_id(*, saml_response_xml: bytes) -> str:
    from xml.etree import ElementTree as ET

    try:
        root = ET.fromstring(saml_response_xml)
    except ET.ParseError as parse_err:
        err_lines = [
            "Failed to extract Response/@ID — XML parse failed.",
            "PARSE_ERROR: {}".format(parse_err),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    response_id = root.attrib.get("ID", "")
    if response_id is None or len(response_id) == 0:
        err_lines = [
            "Response/@ID is missing — refusing to seat a session.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    rtnval = response_id
    return rtnval


def _extract_conditions_not_on_or_after(
        *, validated: ValidatedSamlAssertion
    ) -> datetime:
    from xml.etree import ElementTree as ET

    root = ET.fromstring(validated.raw_assertion_xml)
    conditions = root.find(
        "{urn:oasis:names:tc:SAML:2.0:assertion}Conditions",
    )
    if conditions is None:
        # Fall back to "now + 1h" so the row gets pruned
        # eventually; the validator already required the
        # Conditions in the validation path so this is a
        # belt-and-suspenders default.
        rtnval = datetime.now(tz=timezone.utc).replace(
            microsecond=0,
        )
        return rtnval
    not_on_or_after = conditions.attrib.get("NotOnOrAfter", "")
    if len(not_on_or_after) == 0:
        rtnval = datetime.now(tz=timezone.utc).replace(microsecond=0)
        return rtnval
    raw = not_on_or_after.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        rtnval = datetime.fromisoformat(raw)
    except ValueError:
        rtnval = datetime.now(tz=timezone.utc).replace(microsecond=0)
        return rtnval
    if rtnval.tzinfo is None:
        rtnval = rtnval.replace(tzinfo=timezone.utc)
    return rtnval
