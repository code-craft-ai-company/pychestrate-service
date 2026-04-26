"""
.. module:: test_p23b_saml_flow_instrumentation_m3
    :synopsis: Tests for P23b — SAML flow instrumentation wiring.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from automojo import testbase

from automojo.pychestrate.webservice.metrics.timeseries import (
    register_builtin_extensions as register_timeseries_extensions,
    service as metrics_service,
)
from automojo.pychestrate.webservice.metrics.timeseries.facade import (
    reset_for_testing as reset_metrics_facade,
)
from automojo.pychestrate.webservice.security.auth import (
    log_events,
    metrics_emitter,
)
from automojo.pychestrate.webservice.security.auth.factories.auth_provider import (
    InboundFlowPayload,
)
from automojo.pychestrate.webservice.security.auth.factories.saml_provider import (
    SamlAuthProvider,
)
from automojo.pychestrate.webservice.security.auth.log_events import (
    AUTH_LOGIN_REJECTED,
    AUTH_LOGIN_SUCCEEDED,
    AUTH_SAML_METADATA_REFRESH_FAILED,
    AUTH_SAML_METADATA_REFRESHED,
    LOGGER_NAME,
)
from automojo.pychestrate.webservice.security.auth.metrics_emitter import (
    METRIC_LOGIN_TOTAL,
    METRIC_SAML_METADATA_REFRESH_FAILURES_TOTAL,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthProviderKind,
)
from automojo.pychestrate.webservice.security.auth.saml.assertion import (
    SamlAssertionValidationError,
)
from automojo.pychestrate.webservice.security.auth.saml.metadata import (
    SamlMetadataFetchResult,
    refresh_metadata_document,
    reset_for_testing as reset_metadata_cache,
)
from automojo.pychestrate.webservice.security.auth.saml.provider_registry import (
    SamlProviderConfig,
    register_saml_provider,
    reset_for_testing as reset_provider_registry,
)
from automojo.pychestrate.webservice.security.auth.tracing import (
    SPAN_SAML_METADATA_REFRESH,
    SPAN_SAML_VALIDATE,
    SPAN_STATUS_ERROR,
    SPAN_STATUS_OK,
    get_recorder,
    reset_for_testing as reset_tracing,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


EXPECTED_ISSUER: str = "https://idp.example.com/entity"
SP_ENTITY_ID: str = "https://app.example.com/sp"
ACS_URL: str = "https://app.example.com/saml/acs"


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
        '          <ds:X509Certificate>CERT-A</ds:X509Certificate>\n'
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


def _good_metadata_fetcher():
    def _fetcher(_url):
        return SamlMetadataFetchResult(
            document_xml=_build_idp_metadata_xml(),
            max_age_seconds=3600,
        )
    return _fetcher


def _failing_metadata_fetcher():
    def _fetcher(_url):
        raise RuntimeError("upstream-503")
    return _fetcher


def _iso(value: datetime) -> str:
    rtnval = value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return rtnval


def _build_saml_response_xml(
        *,
        response_id: str = "_resp-1",
        in_response_to: Optional[str] = "_authn-1",
        name_id: str = "alice@example.com"
    ) -> bytes:
    issue_instant = datetime.now(tz=timezone.utc).replace(microsecond=0)
    not_on_or_after = issue_instant + timedelta(minutes=10)
    in_response_to_attr = ""
    if in_response_to is not None:
        in_response_to_attr = ' InResponseTo="{}"'.format(in_response_to)
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<samlp:Response '
        'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        'ID="{rid}" Version="2.0" IssueInstant="{ii}">\n'
        '<saml:Assertion ID="_a" Version="2.0" IssueInstant="{ii}">\n'
        '  <saml:Issuer>{iss}</saml:Issuer>\n'
        '  <saml:Subject>\n'
        '    <saml:NameID>{nid}</saml:NameID>\n'
        '    <saml:SubjectConfirmation Method='
        '"urn:oasis:names:tc:SAML:2.0:cm:bearer">\n'
        '      <saml:SubjectConfirmationData '
        'Recipient="{rcpt}" NotOnOrAfter="{noa}"{ir}/>\n'
        '    </saml:SubjectConfirmation>\n'
        '  </saml:Subject>\n'
        '  <saml:Conditions NotBefore="{nb}" NotOnOrAfter="{noa}">\n'
        '    <saml:AudienceRestriction>\n'
        '      <saml:Audience>{aud}</saml:Audience>\n'
        '    </saml:AudienceRestriction>\n'
        '  </saml:Conditions>\n'
        '  <saml:AuthnStatement AuthnInstant="{ii}">\n'
        '    <saml:AuthnContext>\n'
        '      <saml:AuthnContextClassRef>'
        'urn:oasis:names:tc:SAML:2.0:ac:classes:Password'
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
        ir=in_response_to_attr,
        aud=SP_ENTITY_ID,
    )
    rtnval = xml_text.encode("utf-8")
    return rtnval


def _setup_saml_provider(*, db_session) -> None:
    register_saml_provider(
        config=SamlProviderConfig(
            provider_name="okta-saml",
            sp_entity_id=SP_ENTITY_ID,
            acs_url=ACS_URL,
            metadata_url="https://idp.example.com/m.xml",
            metadata_fetcher=_good_metadata_fetcher(),
            session_factory=lambda: db_session,
        ),
    )
    return


def _setup_with_metrics() -> tuple:
    reset_phase1_runtime()
    reset_metrics_facade()
    reset_tracing()
    reset_metadata_cache()
    reset_provider_registry()
    register_timeseries_extensions()
    _engine, session = build_in_memory_session()
    metrics_emitter.register_auth_metrics(db_session=session)
    return _engine, session


class _CapturingHandler(logging.Handler):

    def __init__(self) -> None:
        super().__init__()
        self.records: List[logging.LogRecord] = []
        return

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        return


def _capture_auth_log() -> _CapturingHandler:
    handler = _CapturingHandler()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return handler


def _detach_auth_log(handler: _CapturingHandler) -> None:
    logging.getLogger(LOGGER_NAME).removeHandler(handler)
    return


# -------------------------------------
# refresh_metadata_document spans + logs
# -------------------------------------

def test_refresh_metadata_emits_span_with_entity_id_attribute():
    """
    **Feature: 1-authentication (M3)**
    **Property: a successful refresh_metadata_document
    opens a saml.metadata_refresh span carrying the
    parsed entity_id and signing_cert_count.**
    """
    _setup_with_metrics()
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=_good_metadata_fetcher(),
    )
    spans = get_recorder().list_spans_by_name(
        name=SPAN_SAML_METADATA_REFRESH,
    )
    testbase.assert_equal(len(spans), 1)
    testbase.assert_equal(spans[0].status, SPAN_STATUS_OK)
    testbase.assert_equal(
        spans[0].attributes["entity_id"], EXPECTED_ISSUER,
    )
    testbase.assert_equal(
        spans[0].attributes["signing_cert_count"], 1,
    )
    return


def test_refresh_metadata_emits_auth_saml_metadata_refreshed_log_event():
    """
    **Feature: 1-authentication (M3)**
    **Property: a successful refresh emits the
    auth.saml.metadata.refreshed log event with
    provider_name + entity_id + expires_at +
    signing_cert_count.**
    """
    _setup_with_metrics()
    handler = _capture_auth_log()
    try:
        refresh_metadata_document(
            provider_name="okta-saml",
            metadata_url="https://idp.example.com/m.xml",
            fetcher=_good_metadata_fetcher(),
        )
    finally:
        _detach_auth_log(handler)
    matched = [
        r for r in handler.records
        if r.msg == AUTH_SAML_METADATA_REFRESHED
    ]
    testbase.assert_equal(len(matched), 1)
    payload = matched[0].__dict__.get("payload", {})
    testbase.assert_equal(payload["provider_name"], "okta-saml")
    testbase.assert_equal(payload["entity_id"], EXPECTED_ISSUER)
    testbase.assert_equal(payload["signing_cert_count"], 1)
    return


def test_refresh_metadata_failure_emits_failure_log_event_and_error_span():
    """
    **Feature: 1-authentication (M3)**
    **Property: when the fetcher raises, refresh_metadata_document
    emits the auth.saml.metadata.refresh_failed log event
    and finalizes the span with status='error'. The
    original exception bubbles unchanged so the cached row
    (per NFR-4) stays put.**
    """
    _setup_with_metrics()
    handler = _capture_auth_log()
    raised = False
    try:
        try:
            refresh_metadata_document(
                provider_name="okta-saml",
                metadata_url="https://idp.example.com/m.xml",
                fetcher=_failing_metadata_fetcher(),
            )
        except RuntimeError:
            raised = True
    finally:
        _detach_auth_log(handler)
    testbase.assert_equal(raised, True)
    matched = [
        r for r in handler.records
        if r.msg == AUTH_SAML_METADATA_REFRESH_FAILED
    ]
    testbase.assert_equal(len(matched), 1)
    spans = get_recorder().list_spans_by_name(
        name=SPAN_SAML_METADATA_REFRESH,
    )
    testbase.assert_equal(spans[0].status, SPAN_STATUS_ERROR)
    return


# -------------------------------------
# validate_saml_assertion span
# -------------------------------------

def test_saml_provider_complete_callback_emits_saml_validate_span():
    """
    **Feature: 1-authentication (M3)**
    **Property: SamlAuthProvider.complete_callback runs
    validate_saml_assertion under a saml.validate span
    that finalizes status='ok' on a clean assertion and
    carries the issuer + audience_count attributes.**
    """
    _engine, session = _setup_with_metrics()
    _setup_saml_provider(db_session=session)
    inbound = InboundFlowPayload(
        fields={
            "saml_response": _build_saml_response_xml(),
            "expected_in_response_to": "_authn-1",
            "db_session": session,
        },
    )
    SamlAuthProvider.complete_callback(
        provider_name="okta-saml", inbound=inbound,
    )
    spans = get_recorder().list_spans_by_name(
        name=SPAN_SAML_VALIDATE,
    )
    testbase.assert_equal(len(spans), 1)
    testbase.assert_equal(spans[0].status, SPAN_STATUS_OK)
    testbase.assert_equal(
        spans[0].attributes["issuer"], EXPECTED_ISSUER,
    )
    testbase.assert_equal(
        spans[0].attributes["audience_count"], 1,
    )
    return


def test_saml_validate_failure_finalizes_span_as_error_with_reason():
    """
    **Feature: 1-authentication (M3)**
    **Property: a SamlAssertionValidationError raised inside
    the saml.validate span finalizes the span with status=
    'error' and surfaces the stable reason token.**
    """
    _engine, session = _setup_with_metrics()
    _setup_saml_provider(db_session=session)
    bad_xml = _build_saml_response_xml().replace(
        EXPECTED_ISSUER.encode(),
        b"https://different-idp.example.com/entity",
    )
    inbound = InboundFlowPayload(
        fields={
            "saml_response": bad_xml,
            "expected_in_response_to": "_authn-1",
            "db_session": session,
        },
    )
    raised = False
    try:
        SamlAuthProvider.complete_callback(
            provider_name="okta-saml", inbound=inbound,
        )
    except SamlAssertionValidationError:
        raised = True
    testbase.assert_equal(raised, True)
    spans = get_recorder().list_spans_by_name(
        name=SPAN_SAML_VALIDATE,
    )
    testbase.assert_equal(spans[0].status, SPAN_STATUS_ERROR)
    testbase.assert_equal(
        spans[0].exception_reason, "issuer_mismatch",
    )
    return


# -------------------------------------
# SamlAuthProvider login outcome metrics
# -------------------------------------

def test_saml_provider_complete_callback_emits_login_succeeded_counter_and_log():
    """
    **Feature: 1-authentication (M3)**
    **Property: a successful SAML callback emits
    pychestrate_auth_login_total{provider_kind=SAML,
    outcome=succeeded} and the auth.login.succeeded log
    event with the NameID as user_id + the assertion
    Issuer.**
    """
    _engine, session = _setup_with_metrics()
    _setup_saml_provider(db_session=session)
    handler = _capture_auth_log()
    try:
        SamlAuthProvider.complete_callback(
            provider_name="okta-saml",
            inbound=InboundFlowPayload(
                fields={
                    "saml_response": _build_saml_response_xml(),
                    "expected_in_response_to": "_authn-1",
                    "db_session": session,
                },
            ),
        )
    finally:
        _detach_auth_log(handler)
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_LOGIN_TOTAL,
    )
    succeeded = [
        s for s in samples
        if s.labels.get("provider_kind") == "SAML"
        and s.labels.get("outcome") == "succeeded"
    ]
    testbase.assert_equal(len(succeeded), 1)
    matched = [
        r for r in handler.records if r.msg == AUTH_LOGIN_SUCCEEDED
    ]
    testbase.assert_equal(len(matched), 1)
    payload = matched[0].__dict__.get("payload", {})
    testbase.assert_equal(payload["provider_kind"], "SAML")
    testbase.assert_equal(payload["user_id"], "alice@example.com")
    testbase.assert_equal(payload["issuer"], EXPECTED_ISSUER)
    return


def test_saml_provider_complete_callback_emits_login_rejected_counter_on_failure():
    """
    **Feature: 1-authentication (M3)**
    **Property: an assertion-validation failure emits
    pychestrate_auth_login_total{provider_kind=SAML,
    outcome=rejected} and the auth.login.rejected log
    event with the underlying reason.**
    """
    _engine, session = _setup_with_metrics()
    _setup_saml_provider(db_session=session)
    bad_xml = _build_saml_response_xml().replace(
        SP_ENTITY_ID.encode(),
        b"https://wrong-sp.example.com/sp",
    )
    handler = _capture_auth_log()
    try:
        try:
            SamlAuthProvider.complete_callback(
                provider_name="okta-saml",
                inbound=InboundFlowPayload(
                    fields={
                        "saml_response": bad_xml,
                        "expected_in_response_to": "_authn-1",
                        "db_session": session,
                    },
                ),
            )
        except SamlAssertionValidationError:
            pass
    finally:
        _detach_auth_log(handler)
    samples = metrics_service.list_samples_for_metric(
        db_session=session, metric_name=METRIC_LOGIN_TOTAL,
    )
    rejected = [
        s for s in samples
        if s.labels.get("provider_kind") == "SAML"
        and s.labels.get("outcome") == "rejected"
    ]
    testbase.assert_equal(len(rejected), 1)
    matched = [
        r for r in handler.records if r.msg == AUTH_LOGIN_REJECTED
    ]
    testbase.assert_equal(len(matched), 1)
    payload = matched[0].__dict__.get("payload", {})
    testbase.assert_equal(payload["provider_kind"], "SAML")
    testbase.assert_equal(payload["reason"], "audience_mismatch")
    return


# -------------------------------------
# Safe behavior without metrics bootstrap
# -------------------------------------

def test_saml_flows_work_when_metrics_driver_not_registered():
    """
    **Feature: 1-authentication (M3)**
    **Property: SAML flows never crash when the timeseries
    driver isn't bootstrapped — recorder helpers swallow
    the missing-driver case.**
    """
    reset_phase1_runtime()
    reset_metrics_facade()
    reset_tracing()
    reset_metadata_cache()
    reset_provider_registry()
    _engine, session = build_in_memory_session()
    _setup_saml_provider(db_session=session)
    completed = SamlAuthProvider.complete_callback(
        provider_name="okta-saml",
        inbound=InboundFlowPayload(
            fields={
                "saml_response": _build_saml_response_xml(),
                "expected_in_response_to": "_authn-1",
                "db_session": session,
            },
        ),
    )
    testbase.assert_equal(completed.user_id, "alice@example.com")
    return
