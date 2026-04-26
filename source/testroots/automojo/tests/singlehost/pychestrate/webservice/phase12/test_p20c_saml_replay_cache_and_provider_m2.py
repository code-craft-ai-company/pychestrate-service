"""
.. module:: test_p20c_saml_replay_cache_and_provider_m2
    :synopsis: Tests for P20c — 1-authentication M2 SAML replay cache + SamlAuthProvider.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib import parse as urlparse

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.factories.auth_provider import (
    InboundFlowPayload,
    RedirectDescriptor,
)
from automojo.pychestrate.webservice.security.auth.factories.saml_provider import (
    SamlAuthProvider,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
    AuthSamlReplayCache,
)
from automojo.pychestrate.webservice.security.auth.saml.metadata import (
    SamlMetadataFetchResult,
    reset_for_testing as reset_metadata_cache,
)
from automojo.pychestrate.webservice.security.auth.saml.provider_registry import (
    SamlProviderConfig,
    get_saml_provider_config,
    list_saml_provider_names,
    register_saml_provider,
    reset_for_testing as reset_provider_registry,
)
from automojo.pychestrate.webservice.security.auth.saml.replay_cache import (
    SamlReplayDetectedError,
    is_recorded,
    record_response_id,
    sweep_expired,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


ANCHOR: datetime = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
EXPECTED_ISSUER: str = "https://idp.example.com/entity"
SP_ENTITY_ID: str = "https://app.example.com/sp"
ACS_URL: str = "https://app.example.com/saml/acs"


def _iso(value: datetime) -> str:
    rtnval = value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return rtnval


def _build_idp_metadata_xml() -> bytes:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<md:EntityDescriptor '
        'xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
        'entityID="{iss}" cacheDuration="PT1H">\n'
        '  <md:IDPSSODescriptor '
        'protocolSupportEnumeration='
        '"urn:oasis:names:tc:SAML:2.0:protocol">\n'
        '    <md:KeyDescriptor use="signing">\n'
        '      <ds:KeyInfo '
        'xmlns:ds="http://www.w3.org/2000/09/xmldsig#">\n'
        '        <ds:X509Data>\n'
        '          <ds:X509Certificate>CERT-BODY-A</ds:X509Certificate>\n'
        '        </ds:X509Data>\n'
        '      </ds:KeyInfo>\n'
        '    </md:KeyDescriptor>\n'
        '    <md:SingleSignOnService '
        'Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" '
        'Location="https://idp.example.com/sso/redirect"/>\n'
        '  </md:IDPSSODescriptor>\n'
        '</md:EntityDescriptor>\n'
    ).format(iss=EXPECTED_ISSUER)
    rtnval = xml_text.encode("utf-8")
    return rtnval


def _metadata_fetcher(call_log=None):
    if call_log is None:
        call_log = []

    def _fetcher(metadata_url: str) -> SamlMetadataFetchResult:
        call_log.append(metadata_url)
        return SamlMetadataFetchResult(
            document_xml=_build_idp_metadata_xml(),
            max_age_seconds=3600,
        )
    return _fetcher


def _build_saml_response_xml(
        *,
        response_id: str = "_response-id-7",
        in_response_to: Optional[str] = "_authn-id-1",
        not_on_or_after: Optional[datetime] = None,
        name_id: str = "alice@example.com"
    ) -> bytes:
    # SamlAuthProvider.complete_callback doesn't expose a 'now'
    # override on the protocol surface, so the assertion has to
    # be valid against real wall-clock time.
    issue_instant = datetime.now(tz=timezone.utc).replace(microsecond=0)
    if not_on_or_after is None:
        not_on_or_after = issue_instant + timedelta(minutes=10)
    sc_in_response_to_attr = ""
    if in_response_to is not None:
        sc_in_response_to_attr = ' InResponseTo="{}"'.format(
            in_response_to,
        )
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<samlp:Response '
        'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        'ID="{rid}" Version="2.0" IssueInstant="{ii}">\n'
        '<saml:Assertion ID="_assertion-id-1" Version="2.0" '
        'IssueInstant="{ii}">\n'
        '  <saml:Issuer>{iss}</saml:Issuer>\n'
        '  <saml:Subject>\n'
        '    <saml:NameID Format='
        '"urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">'
        '{nid}</saml:NameID>\n'
        '    <saml:SubjectConfirmation Method='
        '"urn:oasis:names:tc:SAML:2.0:cm:bearer">\n'
        '      <saml:SubjectConfirmationData '
        'Recipient="{rcpt}" '
        'NotOnOrAfter="{noa}"{ir2}/>\n'
        '    </saml:SubjectConfirmation>\n'
        '  </saml:Subject>\n'
        '  <saml:Conditions NotBefore="{nb}" NotOnOrAfter="{noa}">\n'
        '    <saml:AudienceRestriction>\n'
        '      <saml:Audience>{aud}</saml:Audience>\n'
        '    </saml:AudienceRestriction>\n'
        '  </saml:Conditions>\n'
        '  <saml:AuthnStatement AuthnInstant="{ii}" '
        'SessionIndex="_si-1">\n'
        '    <saml:AuthnContext>\n'
        '      <saml:AuthnContextClassRef>'
        'urn:oasis:names:tc:SAML:2.0:ac:classes:'
        'PasswordProtectedTransport'
        '</saml:AuthnContextClassRef>\n'
        '    </saml:AuthnContext>\n'
        '  </saml:AuthnStatement>\n'
        '</saml:Assertion>\n'
        '</samlp:Response>\n'
    ).format(
        rid=response_id,
        ii=_iso(issue_instant),
        iss=EXPECTED_ISSUER,
        nid=name_id,
        rcpt=ACS_URL,
        nb=_iso(issue_instant - timedelta(minutes=1)),
        noa=_iso(not_on_or_after),
        ir2=sc_in_response_to_attr,
        aud=SP_ENTITY_ID,
    )
    rtnval = xml_text.encode("utf-8")
    return rtnval


def _build_provider_config(
        *,
        session,
        provider_name: str = "okta-saml",
        signature_verifier=None
    ) -> SamlProviderConfig:
    rtnval = SamlProviderConfig(
        provider_name=provider_name,
        sp_entity_id=SP_ENTITY_ID,
        acs_url=ACS_URL,
        metadata_url="https://idp.example.com/metadata.xml",
        metadata_fetcher=_metadata_fetcher(),
        session_factory=lambda: session,
        signature_verifier=signature_verifier,
    )
    return rtnval


def _setup() -> tuple:
    reset_metadata_cache()
    reset_provider_registry()
    _engine, session = build_in_memory_session()
    config = _build_provider_config(session=session)
    register_saml_provider(config=config)
    return session, config


# -------------------------------------
# Replay cache primitives
# -------------------------------------

def test_record_response_id_persists_row():
    """
    **Feature: 1-authentication (M2)**
    **Property: record_response_id inserts a row into
    auth_saml_replay_cache that is_recorded then sees.**
    """
    _engine, session = build_in_memory_session()
    record_response_id(
        db_session=session,
        response_id="_resp-1",
        not_on_or_after=ANCHOR + timedelta(minutes=10),
    )
    testbase.assert_equal(
        is_recorded(db_session=session, response_id="_resp-1"),
        True,
    )
    testbase.assert_equal(
        is_recorded(db_session=session, response_id="_resp-2"),
        False,
    )
    return


def test_record_response_id_rejects_replay():
    """
    **Feature: 1-authentication (M2)**
    **Property: a second record_response_id call with the
    same id raises SamlReplayDetectedError so the
    controller refuses to seat a session.**
    """
    _engine, session = build_in_memory_session()
    record_response_id(
        db_session=session,
        response_id="_resp-1",
        not_on_or_after=ANCHOR + timedelta(minutes=10),
    )
    raised = False
    try:
        record_response_id(
            db_session=session,
            response_id="_resp-1",
            not_on_or_after=ANCHOR + timedelta(minutes=10),
        )
    except SamlReplayDetectedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_record_response_id_validates_inputs():
    """
    **Feature: 1-authentication (M2)**
    **Property: empty response_id / None not_on_or_after /
    None db_session each raise ValueError.**
    """
    _engine, session = build_in_memory_session()
    raised_id = False
    raised_noa = False
    raised_db = False
    try:
        record_response_id(
            db_session=session,
            response_id="",
            not_on_or_after=ANCHOR,
        )
    except ValueError:
        raised_id = True
    try:
        record_response_id(
            db_session=session,
            response_id="_x",
            not_on_or_after=None,
        )
    except ValueError:
        raised_noa = True
    try:
        record_response_id(
            db_session=None,
            response_id="_x",
            not_on_or_after=ANCHOR,
        )
    except ValueError:
        raised_db = True
    testbase.assert_equal(raised_id, True)
    testbase.assert_equal(raised_noa, True)
    testbase.assert_equal(raised_db, True)
    return


def test_sweep_expired_drops_rows_past_horizon():
    """
    **Feature: 1-authentication (M2)**
    **Property: sweep_expired deletes rows whose
    not_on_or_after is at or before now and returns the
    count.**
    """
    _engine, session = build_in_memory_session()
    record_response_id(
        db_session=session,
        response_id="_old-1",
        not_on_or_after=ANCHOR - timedelta(minutes=10),
    )
    record_response_id(
        db_session=session,
        response_id="_old-2",
        not_on_or_after=ANCHOR - timedelta(minutes=5),
    )
    record_response_id(
        db_session=session,
        response_id="_fresh-1",
        not_on_or_after=ANCHOR + timedelta(minutes=10),
    )
    deleted = sweep_expired(db_session=session, now=ANCHOR)
    testbase.assert_equal(deleted, 2)
    remaining = session.query(AuthSamlReplayCache).all()
    testbase.assert_equal(len(remaining), 1)
    testbase.assert_equal(remaining[0].response_id, "_fresh-1")
    return


def test_sweep_expired_returns_zero_when_nothing_to_drop():
    """
    **Feature: 1-authentication (M2)**
    **Property: sweep_expired returns 0 when no rows are
    past the horizon.**
    """
    _engine, session = build_in_memory_session()
    record_response_id(
        db_session=session,
        response_id="_fresh",
        not_on_or_after=ANCHOR + timedelta(minutes=10),
    )
    deleted = sweep_expired(db_session=session, now=ANCHOR)
    testbase.assert_equal(deleted, 0)
    return


# -------------------------------------
# Provider registry
# -------------------------------------

def test_provider_kind_is_saml_and_precedence_is_1000():
    """
    **Feature: 1-authentication (M2)**
    **Property: SamlAuthProvider declares SAML kind and the
    documented PRECEDENCE = 1000.**
    """
    testbase.assert_equal(
        SamlAuthProvider.provider_kind(), AuthProviderKind.SAML,
    )
    testbase.assert_equal(SamlAuthProvider.PRECEDENCE, 1000)
    testbase.assert_equal(
        SamlAuthProvider.factory_protocol_name, "auth_provider",
    )
    return


def test_provider_registry_register_get_list_round_trip():
    """
    **Feature: 1-authentication (M2)**
    **Property: register / get / list round-trip the same
    SamlProviderConfig instance and list returns sorted
    names.**
    """
    session, config = _setup()
    second = _build_provider_config(
        session=session, provider_name="auth0-saml",
    )
    register_saml_provider(config=second)
    testbase.assert_equal(
        list_saml_provider_names(),
        ["auth0-saml", "okta-saml"],
    )
    testbase.assert_equal(
        get_saml_provider_config(provider_name="okta-saml") is config,
        True,
    )
    return


def test_provider_registry_rejects_duplicate():
    """
    **Feature: 1-authentication (M2)**
    **Property: a second register_saml_provider with the
    same provider_name raises ValueError.**
    """
    session, _ = _setup()
    duplicate = _build_provider_config(session=session)
    raised = False
    try:
        register_saml_provider(config=duplicate)
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_provider_registry_rejects_empty_acs_url():
    """
    **Feature: 1-authentication (M2)**
    **Property: a SamlProviderConfig with an empty acs_url
    is rejected at registration time.**
    """
    reset_provider_registry()
    _engine, session = build_in_memory_session()
    bad = SamlProviderConfig(
        provider_name="okta-saml",
        sp_entity_id=SP_ENTITY_ID,
        acs_url="",
        metadata_url="https://idp/m.xml",
        metadata_fetcher=_metadata_fetcher(),
        session_factory=lambda: session,
    )
    raised = False
    try:
        register_saml_provider(config=bad)
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# build_begin_login_redirect
# -------------------------------------

def test_build_begin_login_redirect_returns_sso_url_with_authn_request():
    """
    **Feature: 1-authentication (M2)**
    **Property: build_begin_login_redirect returns a
    RedirectDescriptor whose target_url is the IdP SSO
    endpoint with SAMLRequest + RelayState query params,
    and whose state_token is the AuthnRequest id the ACS
    will match against InResponseTo.**
    """
    _setup()
    redirect = SamlAuthProvider.build_begin_login_redirect(
        provider_name="okta-saml",
        redirect_target="/welcome",
    )
    testbase.assert_equal(isinstance(redirect, RedirectDescriptor), True)
    testbase.assert_equal(
        redirect.target_url.startswith(
            "https://idp.example.com/sso/redirect?",
        ),
        True,
    )
    parsed = urlparse.urlparse(redirect.target_url)
    params = dict(urlparse.parse_qsl(parsed.query))
    testbase.assert_equal(len(params.get("SAMLRequest", "")) > 0, True)
    testbase.assert_equal(params.get("RelayState"), "/welcome")
    testbase.assert_equal(redirect.state_token.startswith("_"), True)
    return


# -------------------------------------
# complete_callback happy path
# -------------------------------------

def test_complete_callback_validates_assertion_and_records_replay():
    """
    **Feature: 1-authentication (M2)**
    **Property: complete_callback runs the assertion
    validator end-to-end, records the Response/@ID in the
    replay cache, and returns CompletedFlow whose user_id
    is the assertion NameID.**
    """
    session, _ = _setup()
    saml_response = _build_saml_response_xml(
        response_id="_resp-callback-1",
        in_response_to="_authn-id-1",
    )
    inbound = InboundFlowPayload(
        fields={
            "saml_response": saml_response,
            "expected_in_response_to": "_authn-id-1",
            "db_session": session,
        },
    )
    completed = SamlAuthProvider.complete_callback(
        provider_name="okta-saml", inbound=inbound,
    )
    testbase.assert_equal(completed.provider_kind, AuthProviderKind.SAML)
    testbase.assert_equal(completed.provider_name, "okta-saml")
    testbase.assert_equal(completed.user_id, "alice@example.com")
    testbase.assert_equal(completed.access_token_payload, None)
    testbase.assert_equal(completed.refresh_token_payload, None)
    testbase.assert_equal(
        is_recorded(
            db_session=session, response_id="_resp-callback-1",
        ),
        True,
    )
    return


def test_complete_callback_replay_detected_on_second_call():
    """
    **Feature: 1-authentication (M2)**
    **Property: a second complete_callback for the same
    Response/@ID raises SamlReplayDetectedError so the
    second seating attempt is refused.**
    """
    session, _ = _setup()
    saml_response = _build_saml_response_xml(
        response_id="_resp-replay-1",
        in_response_to="_authn-id-2",
    )
    inbound = InboundFlowPayload(
        fields={
            "saml_response": saml_response,
            "expected_in_response_to": "_authn-id-2",
            "db_session": session,
        },
    )
    SamlAuthProvider.complete_callback(
        provider_name="okta-saml", inbound=inbound,
    )
    raised = False
    try:
        SamlAuthProvider.complete_callback(
            provider_name="okta-saml", inbound=inbound,
        )
    except SamlReplayDetectedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_complete_callback_validates_inbound_required_fields():
    """
    **Feature: 1-authentication (M2)**
    **Property: missing 'saml_response' raises ValueError
    so the controller refuses to dispatch.**
    """
    _setup()
    bad = InboundFlowPayload(fields={})
    raised = False
    try:
        SamlAuthProvider.complete_callback(
            provider_name="okta-saml", inbound=bad,
        )
    except ValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_complete_callback_unknown_provider_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: dispatching against an unregistered
    provider_name raises KeyError.**
    """
    reset_provider_registry()
    inbound = InboundFlowPayload(
        fields={
            "saml_response": _build_saml_response_xml(),
        },
    )
    raised = False
    try:
        SamlAuthProvider.complete_callback(
            provider_name="missing", inbound=inbound,
        )
    except KeyError:
        raised = True
    testbase.assert_equal(raised, True)
    return
