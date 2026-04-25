"""
.. module:: test_p20a_saml_metadata_refresh_m2
    :synopsis: Tests for P20a — 1-authentication M2 SAML metadata cache.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import List, Optional

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.saml.metadata import (
    DEFAULT_METADATA_TTL,
    MAX_METADATA_TTL,
    MIN_METADATA_TTL,
    SamlIdpMetadata,
    SamlMetadataFetchResult,
    SamlMetadataParseError,
    clamp_ttl,
    current_trust_set,
    invalidate,
    parse_metadata_document,
    refresh_metadata_document,
    reset_for_testing as reset_metadata_cache,
)


SAMPLE_CERT_BODY: str = (
    "MIIBkTCCATugAwIBAgIQ-EXAMPLE-CERTIFICATE-BODY-1"
)
ROTATED_CERT_BODY: str = (
    "MIIBkTCCATugAwIBAgIQ-ROTATED-CERTIFICATE-BODY-9"
)


def _build_metadata_xml(
        *,
        entity_id: str = "https://idp.example.com/entity",
        cert_body: str = SAMPLE_CERT_BODY,
        cache_duration: str = "PT1H",
        valid_until: Optional[str] = None,
        want_signed: str = "false",
        include_redirect: bool = True,
        include_post: bool = True
    ) -> bytes:
    valid_until_attr = ""
    if valid_until is not None:
        valid_until_attr = ' validUntil="{}"'.format(valid_until)
    redirect_block = ""
    if include_redirect is True:
        redirect_block = (
            '    <md:SingleSignOnService '
            'Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" '
            'Location="https://idp.example.com/sso/redirect"/>\n'
        )
    post_block = ""
    if include_post is True:
        post_block = (
            '    <md:SingleSignOnService '
            'Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
            'Location="https://idp.example.com/sso/post"/>\n'
        )
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<md:EntityDescriptor '
        'xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
        'entityID="{}" '
        'cacheDuration="{}"{}>\n'
        '  <md:IDPSSODescriptor '
        'WantAuthnRequestsSigned="{}" '
        'protocolSupportEnumeration='
        '"urn:oasis:names:tc:SAML:2.0:protocol">\n'
        '    <md:KeyDescriptor use="signing">\n'
        '      <ds:KeyInfo '
        'xmlns:ds="http://www.w3.org/2000/09/xmldsig#">\n'
        '        <ds:X509Data>\n'
        '          <ds:X509Certificate>{}</ds:X509Certificate>\n'
        '        </ds:X509Data>\n'
        '      </ds:KeyInfo>\n'
        '    </md:KeyDescriptor>\n'
        '{}{}'
        '  </md:IDPSSODescriptor>\n'
        '</md:EntityDescriptor>\n'
    ).format(
        entity_id, cache_duration, valid_until_attr,
        want_signed, cert_body,
        redirect_block, post_block,
    )
    rtnval = xml_text.encode("utf-8")
    return rtnval


def _make_fetcher(
        *,
        xml_bytes: bytes,
        max_age_seconds: Optional[int] = None,
        call_log: Optional[list] = None
    ):
    if call_log is None:
        call_log = []

    def _fetcher(metadata_url: str) -> SamlMetadataFetchResult:
        call_log.append(metadata_url)
        return SamlMetadataFetchResult(
            document_xml=xml_bytes,
            max_age_seconds=max_age_seconds,
        )
    return _fetcher


# -------------------------------------
# parse_metadata_document
# -------------------------------------

def test_parse_extracts_entity_id_endpoints_and_certificates():
    """
    **Feature: 1-authentication (M2)**
    **Property: parse_metadata_document extracts entityID,
    HTTP-Redirect / HTTP-POST SSO endpoints, signing
    certificates, and the WantAuthnRequestsSigned flag from
    a well-formed IdP metadata XML.**
    """
    xml_bytes = _build_metadata_xml(
        want_signed="true",
        cache_duration="PT2H",
    )
    metadata = parse_metadata_document(xml_bytes=xml_bytes)
    testbase.assert_equal(
        metadata.entity_id, "https://idp.example.com/entity",
    )
    testbase.assert_equal(
        metadata.sso_redirect_url,
        "https://idp.example.com/sso/redirect",
    )
    testbase.assert_equal(
        metadata.sso_post_url,
        "https://idp.example.com/sso/post",
    )
    testbase.assert_equal(
        list(metadata.signing_certificates), [SAMPLE_CERT_BODY],
    )
    testbase.assert_equal(metadata.want_authn_requests_signed, True)
    testbase.assert_equal(metadata.cache_duration_seconds, 2 * 3600)
    return


def test_parse_strips_whitespace_inside_certificate_body():
    """
    **Feature: 1-authentication (M2)**
    **Property: parse_metadata_document strips whitespace
    embedded inside the X509Certificate text node so it
    matches the canonical PEM body.**
    """
    xml_bytes = _build_metadata_xml(
        cert_body=(
            "  MIIBk\n"
            "      TCCAT-EXAMPLE-CERTIFICATE-BODY-2\n"
        ),
    )
    metadata = parse_metadata_document(xml_bytes=xml_bytes)
    testbase.assert_equal(
        list(metadata.signing_certificates),
        ["MIIBkTCCAT-EXAMPLE-CERTIFICATE-BODY-2"],
    )
    return


def test_parse_rejects_malformed_xml():
    """
    **Feature: 1-authentication (M2)**
    **Property: a non-XML payload bubbles
    SamlMetadataParseError(reason='xml_malformed').**
    """
    raised_reason = ""
    try:
        parse_metadata_document(xml_bytes=b"<not-actually-xml")
    except SamlMetadataParseError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "xml_malformed")
    return


def test_parse_rejects_missing_entity_id():
    """
    **Feature: 1-authentication (M2)**
    **Property: an EntityDescriptor with no entityID
    attribute raises
    SamlMetadataParseError(reason='entity_id_missing').**
    """
    xml_bytes = _build_metadata_xml().replace(
        b'entityID="https://idp.example.com/entity" ',
        b"",
    )
    raised_reason = ""
    try:
        parse_metadata_document(xml_bytes=xml_bytes)
    except SamlMetadataParseError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "entity_id_missing")
    return


def test_parse_rejects_no_signing_certificate():
    """
    **Feature: 1-authentication (M2)**
    **Property: an IDPSSODescriptor with no signing-use
    KeyDescriptor raises
    SamlMetadataParseError(reason='signing_certificate_missing').**
    """
    xml_bytes = _build_metadata_xml().replace(
        b'use="signing"', b'use="encryption"',
    )
    raised_reason = ""
    try:
        parse_metadata_document(xml_bytes=xml_bytes)
    except SamlMetadataParseError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "signing_certificate_missing")
    return


def test_parse_rejects_no_sso_endpoint():
    """
    **Feature: 1-authentication (M2)**
    **Property: an IDPSSODescriptor with no
    SingleSignOnService elements raises
    SamlMetadataParseError(reason='sso_endpoint_missing').**
    """
    xml_bytes = _build_metadata_xml(
        include_redirect=False, include_post=False,
    )
    raised_reason = ""
    try:
        parse_metadata_document(xml_bytes=xml_bytes)
    except SamlMetadataParseError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "sso_endpoint_missing")
    return


# -------------------------------------
# clamp_ttl
# -------------------------------------

def test_clamp_ttl_applies_min_max_window_and_default():
    """
    **Feature: 1-authentication (M2)**
    **Property: clamp_ttl honors the
    [MIN_METADATA_TTL, MAX_METADATA_TTL] window and falls
    back to DEFAULT_METADATA_TTL on None.**
    """
    testbase.assert_equal(
        clamp_ttl(max_age_seconds=None), DEFAULT_METADATA_TTL,
    )
    testbase.assert_equal(
        clamp_ttl(max_age_seconds=10), MIN_METADATA_TTL,
    )
    testbase.assert_equal(
        clamp_ttl(max_age_seconds=10 * 24 * 3600), MAX_METADATA_TTL,
    )
    testbase.assert_equal(
        clamp_ttl(max_age_seconds=600).total_seconds(), 600.0,
    )
    return


# -------------------------------------
# refresh_metadata_document + cache
# -------------------------------------

def test_refresh_writes_cache_and_returns_metadata():
    """
    **Feature: 1-authentication (M2)**
    **Property: refresh_metadata_document fetches the IdP
    XML once, parses it, lands the trust set in the cache,
    and returns the SamlIdpMetadata.**
    """
    reset_metadata_cache()
    xml_bytes = _build_metadata_xml()
    call_log: list = []
    fetcher = _make_fetcher(
        xml_bytes=xml_bytes, max_age_seconds=600, call_log=call_log,
    )
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    metadata = refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/metadata.xml",
        fetcher=fetcher,
        now=anchor,
    )
    testbase.assert_equal(
        metadata.entity_id, "https://idp.example.com/entity",
    )
    testbase.assert_equal(len(call_log), 1)
    cached = current_trust_set(
        provider_name="okta-saml", now=anchor,
    )
    testbase.assert_equal(cached is metadata, True)
    return


def test_refresh_returns_cached_within_ttl_without_refetching():
    """
    **Feature: 1-authentication (M2)**
    **Property: a second refresh_metadata_document call
    inside the TTL window returns the cached entry without
    calling the fetcher again.**
    """
    reset_metadata_cache()
    xml_bytes = _build_metadata_xml()
    call_log: list = []
    fetcher = _make_fetcher(
        xml_bytes=xml_bytes, max_age_seconds=3600, call_log=call_log,
    )
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=fetcher,
        now=anchor,
    )
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=fetcher,
        now=anchor + timedelta(seconds=60),
    )
    testbase.assert_equal(len(call_log), 1)
    return


def test_refresh_refetches_after_ttl_expiry():
    """
    **Feature: 1-authentication (M2)**
    **Property: a refresh_metadata_document call past the
    TTL re-runs the fetcher and rotates the trust set.**
    """
    reset_metadata_cache()
    xml_bytes = _build_metadata_xml()
    call_log: list = []
    fetcher = _make_fetcher(
        xml_bytes=xml_bytes, max_age_seconds=120, call_log=call_log,
    )
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=fetcher,
        now=anchor,
    )
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=fetcher,
        now=anchor + timedelta(seconds=200),
    )
    testbase.assert_equal(len(call_log), 2)
    return


def test_refresh_force_refresh_bypasses_cache():
    """
    **Feature: 1-authentication (M2)**
    **Property: force_refresh=True re-runs the fetcher
    even when the cached entry is still warm.**
    """
    reset_metadata_cache()
    xml_bytes = _build_metadata_xml()
    call_log: list = []
    fetcher = _make_fetcher(
        xml_bytes=xml_bytes, max_age_seconds=3600, call_log=call_log,
    )
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=fetcher,
        now=anchor,
    )
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=fetcher,
        force_refresh=True,
        now=anchor + timedelta(seconds=60),
    )
    testbase.assert_equal(len(call_log), 2)
    return


def test_refresh_rotates_trust_set_atomically_per_provider():
    """
    **Feature: 1-authentication (M2)**
    **Property: a successful refresh swaps the cached
    SamlIdpMetadata in a single operation — readers see the
    old set or the new set, never a mix. We assert that
    after force_refresh the cached certificates are exactly
    the rotated set.**
    """
    reset_metadata_cache()
    initial_xml = _build_metadata_xml(cert_body=SAMPLE_CERT_BODY)
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=_make_fetcher(xml_bytes=initial_xml),
    )
    rotated_xml = _build_metadata_xml(cert_body=ROTATED_CERT_BODY)
    refreshed = refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=_make_fetcher(xml_bytes=rotated_xml),
        force_refresh=True,
    )
    testbase.assert_equal(
        list(refreshed.signing_certificates), [ROTATED_CERT_BODY],
    )
    cached = current_trust_set(provider_name="okta-saml")
    testbase.assert_equal(
        list(cached.signing_certificates), [ROTATED_CERT_BODY],
    )
    return


def test_refresh_separate_providers_have_independent_caches():
    """
    **Feature: 1-authentication (M2)**
    **Property: cache entries are keyed by provider_name —
    two providers refreshed in the same process don't
    collide.**
    """
    reset_metadata_cache()
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=_make_fetcher(
            xml_bytes=_build_metadata_xml(
                entity_id="https://idp-okta.example.com",
                cert_body=SAMPLE_CERT_BODY,
            ),
        ),
    )
    refresh_metadata_document(
        provider_name="auth0-saml",
        metadata_url="https://idp.example.com/m2.xml",
        fetcher=_make_fetcher(
            xml_bytes=_build_metadata_xml(
                entity_id="https://idp-auth0.example.com",
                cert_body=ROTATED_CERT_BODY,
            ),
        ),
    )
    okta = current_trust_set(provider_name="okta-saml")
    auth0 = current_trust_set(provider_name="auth0-saml")
    testbase.assert_equal(
        okta.entity_id, "https://idp-okta.example.com",
    )
    testbase.assert_equal(
        auth0.entity_id, "https://idp-auth0.example.com",
    )
    testbase.assert_equal(
        list(okta.signing_certificates), [SAMPLE_CERT_BODY],
    )
    testbase.assert_equal(
        list(auth0.signing_certificates), [ROTATED_CERT_BODY],
    )
    return


def test_refresh_caps_expiry_at_valid_until_attribute():
    """
    **Feature: 1-authentication (M2)**
    **Property: when the metadata document carries a
    validUntil attribute earlier than the TTL window, the
    cached entry expires at validUntil instead.**
    """
    reset_metadata_cache()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    valid_until = anchor + timedelta(seconds=120)
    xml_bytes = _build_metadata_xml(
        cache_duration="PT24H",
        valid_until=valid_until.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    call_log: list = []
    fetcher = _make_fetcher(
        xml_bytes=xml_bytes, call_log=call_log,
    )
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=fetcher,
        now=anchor,
    )
    # Inside validUntil — cached entry returned, no refetch.
    cached = current_trust_set(
        provider_name="okta-saml",
        now=anchor + timedelta(seconds=60),
    )
    testbase.assert_equal(cached is not None, True)
    # Past validUntil — the cache treats the entry as stale.
    expired = current_trust_set(
        provider_name="okta-saml",
        now=anchor + timedelta(seconds=180),
    )
    testbase.assert_equal(expired is None, True)
    return


def test_invalidate_drops_named_provider_cache():
    """
    **Feature: 1-authentication (M2)**
    **Property: invalidate(provider_name=...) drops the
    cached entry; second invalidate against the same name
    returns False.**
    """
    reset_metadata_cache()
    refresh_metadata_document(
        provider_name="okta-saml",
        metadata_url="https://idp.example.com/m.xml",
        fetcher=_make_fetcher(xml_bytes=_build_metadata_xml()),
    )
    testbase.assert_equal(
        invalidate(provider_name="okta-saml"), True,
    )
    testbase.assert_equal(
        current_trust_set(provider_name="okta-saml"), None,
    )
    testbase.assert_equal(
        invalidate(provider_name="okta-saml"), False,
    )
    return


def test_refresh_requires_non_empty_inputs():
    """
    **Feature: 1-authentication (M2)**
    **Property: refresh_metadata_document raises ValueError
    for empty provider_name / metadata_url and for None
    fetchers.**
    """
    reset_metadata_cache()
    raised_provider = False
    raised_url = False
    raised_fetcher = False
    try:
        refresh_metadata_document(
            provider_name="",
            metadata_url="https://x/m.xml",
            fetcher=_make_fetcher(xml_bytes=_build_metadata_xml()),
        )
    except ValueError:
        raised_provider = True
    try:
        refresh_metadata_document(
            provider_name="okta",
            metadata_url="",
            fetcher=_make_fetcher(xml_bytes=_build_metadata_xml()),
        )
    except ValueError:
        raised_url = True
    try:
        refresh_metadata_document(
            provider_name="okta",
            metadata_url="https://x/m.xml",
            fetcher=None,
        )
    except ValueError:
        raised_fetcher = True
    testbase.assert_equal(raised_provider, True)
    testbase.assert_equal(raised_url, True)
    testbase.assert_equal(raised_fetcher, True)
    return
