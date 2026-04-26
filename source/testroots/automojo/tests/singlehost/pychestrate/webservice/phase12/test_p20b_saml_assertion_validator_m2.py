"""
.. module:: test_p20b_saml_assertion_validator_m2
    :synopsis: Tests for P20b — 1-authentication M2 SAML assertion validator.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from automojo import testbase

from automojo.pychestrate.webservice.security.auth.saml.assertion import (
    DEFAULT_SAML_CLOCK_SKEW,
    SamlAssertionValidationError,
    SamlValidationParams,
    ValidatedSamlAssertion,
    validate_saml_assertion,
    verify_envelope_rsa_sha256,
)


ANCHOR: datetime = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
EXPECTED_ISSUER: str = "https://idp.example.com/entity"
EXPECTED_AUDIENCE: str = "https://app.example.com/sp"
EXPECTED_RECIPIENT: str = "https://app.example.com/saml/acs"
EXPECTED_IN_RESPONSE_TO: str = "_authn-request-id-123"


def _iso(value: datetime) -> str:
    rtnval = value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return rtnval


def _build_assertion_xml(
        *,
        issuer: str = EXPECTED_ISSUER,
        audience: str = EXPECTED_AUDIENCE,
        recipient: str = EXPECTED_RECIPIENT,
        in_response_to: Optional[str] = EXPECTED_IN_RESPONSE_TO,
        not_before: datetime = ANCHOR - timedelta(minutes=1),
        not_on_or_after: datetime = ANCHOR + timedelta(minutes=10),
        sc_not_on_or_after: Optional[datetime] = None,
        name_id: str = "alice@example.com",
        name_id_format: str = (
            "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
        ),
        session_index: Optional[str] = "_session-index-7",
        authn_instant: Optional[datetime] = None,
        attributes: Optional[List[Tuple[str, List[str]]]] = None,
        include_signature: bool = True,
        include_subject: bool = True,
        include_conditions: bool = True
    ) -> bytes:
    if sc_not_on_or_after is None:
        sc_not_on_or_after = ANCHOR + timedelta(minutes=5)
    if authn_instant is None:
        authn_instant = ANCHOR - timedelta(seconds=30)
    if attributes is None:
        attributes = [
            ("email", ["alice@example.com"]),
            ("groups", ["admins", "engineers"]),
        ]
    sc_in_response_to_attr = ""
    if in_response_to is not None:
        sc_in_response_to_attr = ' InResponseTo="{}"'.format(
            in_response_to,
        )
    signature_block = ""
    if include_signature is True:
        signature_block = (
            '  <ds:Signature xmlns:ds='
            '"http://www.w3.org/2000/09/xmldsig#">\n'
            '    <ds:SignedInfo>\n'
            '      <ds:CanonicalizationMethod Algorithm='
            '"http://www.w3.org/2001/10/xml-exc-c14n#"/>\n'
            '      <ds:SignatureMethod Algorithm='
            '"http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>\n'
            '    </ds:SignedInfo>\n'
            '    <ds:SignatureValue>fake-signature-bytes</ds:SignatureValue>\n'
            '  </ds:Signature>\n'
        )
    subject_block = ""
    if include_subject is True:
        subject_block = (
            '  <saml:Subject>\n'
            '    <saml:NameID Format="{nf}">{nid}</saml:NameID>\n'
            '    <saml:SubjectConfirmation Method='
            '"urn:oasis:names:tc:SAML:2.0:cm:bearer">\n'
            '      <saml:SubjectConfirmationData '
            'Recipient="{rcpt}" '
            'NotOnOrAfter="{sc_noa}"{ir2}/>\n'
            '    </saml:SubjectConfirmation>\n'
            '  </saml:Subject>\n'
        ).format(
            nf=name_id_format,
            nid=name_id,
            rcpt=recipient,
            sc_noa=_iso(sc_not_on_or_after),
            ir2=sc_in_response_to_attr,
        )
    conditions_block = ""
    if include_conditions is True:
        conditions_block = (
            '  <saml:Conditions NotBefore="{nb}" NotOnOrAfter="{noa}">\n'
            '    <saml:AudienceRestriction>\n'
            '      <saml:Audience>{aud}</saml:Audience>\n'
            '    </saml:AudienceRestriction>\n'
            '  </saml:Conditions>\n'
        ).format(
            nb=_iso(not_before),
            noa=_iso(not_on_or_after),
            aud=audience,
        )
    session_attr = ""
    if session_index is not None:
        session_attr = ' SessionIndex="{}"'.format(session_index)
    authn_attrs = ' AuthnInstant="{}"'.format(_iso(authn_instant))
    authn_block = (
        '  <saml:AuthnStatement{instant}{sess}>\n'
        '    <saml:AuthnContext>\n'
        '      <saml:AuthnContextClassRef>'
        'urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport'
        '</saml:AuthnContextClassRef>\n'
        '    </saml:AuthnContext>\n'
        '  </saml:AuthnStatement>\n'
    ).format(instant=authn_attrs, sess=session_attr)
    attr_xml_lines: List[str] = []
    if len(attributes) > 0:
        attr_xml_lines.append('  <saml:AttributeStatement>')
        for name, values in attributes:
            attr_xml_lines.append(
                '    <saml:Attribute Name="{}">'.format(name),
            )
            for value in values:
                attr_xml_lines.append(
                    '      <saml:AttributeValue>{}</saml:AttributeValue>'
                    .format(value),
                )
            attr_xml_lines.append('    </saml:Attribute>')
        attr_xml_lines.append('  </saml:AttributeStatement>')
    attr_block = "\n".join(attr_xml_lines)
    if len(attr_block) > 0:
        attr_block = attr_block + "\n"

    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<samlp:Response '
        'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        'ID="_response-id-1" Version="2.0" '
        'IssueInstant="{ii}">\n'
        '<saml:Assertion xmlns:saml='
        '"urn:oasis:names:tc:SAML:2.0:assertion" '
        'ID="_assertion-id-1" Version="2.0" '
        'IssueInstant="{ii}">\n'
        '  <saml:Issuer>{iss}</saml:Issuer>\n'
        '{sig}'
        '{subj}'
        '{cond}'
        '{authn}'
        '{attrs}'
        '</saml:Assertion>\n'
        '</samlp:Response>\n'
    ).format(
        ii=_iso(ANCHOR),
        iss=issuer,
        sig=signature_block,
        subj=subject_block,
        cond=conditions_block,
        authn=authn_block,
        attrs=attr_block,
    )
    rtnval = xml_text.encode("utf-8")
    return rtnval


def _accept_signature_verifier(
        assertion_xml: bytes, certs: Tuple[str, ...]
    ) -> bool:
    return True


def _reject_signature_verifier(
        assertion_xml: bytes, certs: Tuple[str, ...]
    ) -> bool:
    return False


def _params(
        *,
        in_response_to: Optional[str] = EXPECTED_IN_RESPONSE_TO,
        signature_verifier=_accept_signature_verifier,
        clock_skew: Optional[timedelta] = None,
        now: Optional[datetime] = None
    ) -> SamlValidationParams:
    if clock_skew is None:
        clock_skew = DEFAULT_SAML_CLOCK_SKEW
    rtnval = SamlValidationParams(
        expected_issuer=EXPECTED_ISSUER,
        expected_audience=EXPECTED_AUDIENCE,
        expected_recipient=EXPECTED_RECIPIENT,
        trusted_certificates=("CERT-BODY-A",),
        expected_in_response_to=in_response_to,
        signature_verifier=signature_verifier,
        clock_skew=clock_skew,
        now=now if now is not None else ANCHOR,
    )
    return rtnval


# -------------------------------------
# Happy-path
# -------------------------------------

def test_validate_returns_validated_assertion_with_claims():
    """
    **Feature: 1-authentication (M2)**
    **Property: a well-formed assertion with matching
    issuer, audience, recipient, InResponseTo, and time
    bounds returns ValidatedSamlAssertion carrying NameID,
    audiences, session_index, AuthnInstant, attributes, and
    raw_assertion_xml.**
    """
    response_xml = _build_assertion_xml()
    result = validate_saml_assertion(
        saml_response_xml=response_xml, params=_params(),
    )
    testbase.assert_equal(result.name_id, "alice@example.com")
    testbase.assert_equal(
        result.name_id_format,
        "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    )
    testbase.assert_equal(result.issuer, EXPECTED_ISSUER)
    testbase.assert_equal(result.audiences, (EXPECTED_AUDIENCE,))
    testbase.assert_equal(result.session_index, "_session-index-7")
    testbase.assert_equal(result.in_response_to, EXPECTED_IN_RESPONSE_TO)
    testbase.assert_equal(
        result.attributes["email"], ("alice@example.com",),
    )
    testbase.assert_equal(
        result.attributes["groups"], ("admins", "engineers"),
    )
    testbase.assert_equal(len(result.raw_assertion_xml) > 0, True)
    return


def test_validate_skips_signature_when_verifier_is_none():
    """
    **Feature: 1-authentication (M2)**
    **Property: a None signature_verifier (test seam) bypasses
    the signature path so callers can isolate claim-set
    semantics from crypto.**
    """
    response_xml = _build_assertion_xml(include_signature=False)
    result = validate_saml_assertion(
        saml_response_xml=response_xml,
        params=_params(signature_verifier=None),
    )
    testbase.assert_equal(result.name_id, "alice@example.com")
    return


def test_validate_skips_in_response_to_check_for_idp_initiated():
    """
    **Feature: 1-authentication (M2)**
    **Property: when expected_in_response_to is None the
    validator accepts an assertion that has no
    InResponseTo attribute (IdP-initiated flow).**
    """
    response_xml = _build_assertion_xml(in_response_to=None)
    params = _params(in_response_to=None)
    result = validate_saml_assertion(
        saml_response_xml=response_xml, params=params,
    )
    testbase.assert_equal(result.in_response_to, None)
    return


# -------------------------------------
# Signature failure modes
# -------------------------------------

def test_validate_signature_missing_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: an assertion with no enveloped Signature
    raises signature_missing when a verifier is configured.**
    """
    response_xml = _build_assertion_xml(include_signature=False)
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml,
            params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "signature_missing")
    return


def test_validate_signature_invalid_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: a verifier returning False bubbles
    SamlAssertionValidationError(reason='signature_invalid').**
    """
    response_xml = _build_assertion_xml()
    params = _params(signature_verifier=_reject_signature_verifier)
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml, params=params,
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "signature_invalid")
    return


# -------------------------------------
# Issuer / audience / recipient mismatches
# -------------------------------------

def test_validate_issuer_mismatch_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: an Issuer that doesn't match
    expected_issuer raises issuer_mismatch.**
    """
    response_xml = _build_assertion_xml(
        issuer="https://different-idp.example.com/entity",
    )
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml, params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "issuer_mismatch")
    return


def test_validate_audience_mismatch_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: an AudienceRestriction that doesn't list
    expected_audience raises audience_mismatch.**
    """
    response_xml = _build_assertion_xml(
        audience="https://other-sp.example.com",
    )
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml, params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "audience_mismatch")
    return


def test_validate_subject_recipient_mismatch_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: a SubjectConfirmationData/@Recipient that
    doesn't match expected_recipient raises
    subject_recipient_mismatch.**
    """
    response_xml = _build_assertion_xml(
        recipient="https://app.example.com/saml/different-acs",
    )
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml, params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "subject_recipient_mismatch")
    return


def test_validate_in_response_to_mismatch_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: an InResponseTo that doesn't match the
    issued AuthnRequest id raises in_response_to_mismatch.**
    """
    response_xml = _build_assertion_xml(
        in_response_to="_different-authn-request-id",
    )
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml, params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "in_response_to_mismatch")
    return


# -------------------------------------
# Time-bound checks (clock skew)
# -------------------------------------

def test_validate_condition_not_yet_valid_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: a NotBefore farther in the future than the
    clock-skew window raises condition_not_yet_valid.**
    """
    future_not_before = ANCHOR + timedelta(minutes=10)
    response_xml = _build_assertion_xml(not_before=future_not_before)
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml, params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "condition_not_yet_valid")
    return


def test_validate_condition_expired_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: a NotOnOrAfter past the clock-skew window
    raises condition_expired.**
    """
    past_not_on_or_after = ANCHOR - timedelta(minutes=10)
    response_xml = _build_assertion_xml(
        not_before=ANCHOR - timedelta(minutes=20),
        not_on_or_after=past_not_on_or_after,
    )
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml, params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "condition_expired")
    return


def test_validate_clock_skew_absorbs_small_drift():
    """
    **Feature: 1-authentication (M2)**
    **Property: a NotBefore one minute in the future is
    accepted because the default clock-skew window is two
    minutes.**
    """
    response_xml = _build_assertion_xml(
        not_before=ANCHOR + timedelta(minutes=1),
        not_on_or_after=ANCHOR + timedelta(minutes=20),
    )
    result = validate_saml_assertion(
        saml_response_xml=response_xml, params=_params(),
    )
    testbase.assert_equal(result.name_id, "alice@example.com")
    return


def test_validate_subject_confirmation_expired_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: a SubjectConfirmationData/@NotOnOrAfter
    past the clock-skew window raises
    subject_confirmation_expired.**
    """
    response_xml = _build_assertion_xml(
        sc_not_on_or_after=ANCHOR - timedelta(minutes=10),
    )
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml, params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "subject_confirmation_expired")
    return


# -------------------------------------
# Structural failure modes
# -------------------------------------

def test_validate_response_malformed_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: a non-XML payload raises
    response_malformed.**
    """
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=b"<not-actually-xml",
            params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "response_malformed")
    return


def test_validate_assertion_missing_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: a samlp:Response with no inner
    saml:Assertion raises assertion_missing.**
    """
    response_xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<samlp:Response '
        b'xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        b'ID="_x" Version="2.0" IssueInstant="2026-04-25T12:00:00Z">'
        b'</samlp:Response>'
    )
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml, params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    testbase.assert_equal(raised_reason, "assertion_missing")
    return


def test_validate_name_id_missing_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: an assertion subject with no NameID raises
    name_id_missing.**
    """
    response_xml = _build_assertion_xml(name_id="")
    raised_reason = ""
    try:
        validate_saml_assertion(
            saml_response_xml=response_xml, params=_params(),
        )
    except SamlAssertionValidationError as err:
        raised_reason = err.reason
    # An empty <saml:NameID></saml:NameID> renders as
    # text=None which the validator treats as missing.
    testbase.assert_equal(raised_reason, "name_id_missing")
    return


def test_validate_requires_non_empty_inputs():
    """
    **Feature: 1-authentication (M2)**
    **Property: empty saml_response_xml or None params raise
    ValueError before any XML parsing.**
    """
    raised_xml = False
    raised_params = False
    try:
        validate_saml_assertion(
            saml_response_xml=b"", params=_params(),
        )
    except ValueError:
        raised_xml = True
    try:
        validate_saml_assertion(
            saml_response_xml=_build_assertion_xml(),
            params=None,
        )
    except ValueError:
        raised_params = True
    testbase.assert_equal(raised_xml, True)
    testbase.assert_equal(raised_params, True)
    return


# -------------------------------------
# verify_envelope_rsa_sha256 reference impl
# -------------------------------------

def test_verify_envelope_rsa_sha256_returns_false_for_empty_inputs():
    """
    **Feature: 1-authentication (M2)**
    **Property: the reference RSA verifier returns False
    for empty XML, empty cert tuples, and unparseable
    inputs — never raises.**
    """
    testbase.assert_equal(
        verify_envelope_rsa_sha256(
            assertion_xml=b"", trusted_certificates=("c",),
        ),
        False,
    )
    testbase.assert_equal(
        verify_envelope_rsa_sha256(
            assertion_xml=_build_assertion_xml(),
            trusted_certificates=tuple(),
        ),
        False,
    )
    testbase.assert_equal(
        verify_envelope_rsa_sha256(
            assertion_xml=b"<not-xml",
            trusted_certificates=("c",),
        ),
        False,
    )
    return


def test_verify_envelope_rsa_sha256_returns_false_for_bad_signature():
    """
    **Feature: 1-authentication (M2)**
    **Property: the reference RSA verifier returns False
    when the SignatureValue is junk under a real
    certificate.**
    """
    # Build a self-signed RSA cert for the verifier to
    # consume; the SignatureValue in the assertion is
    # garbage, so the verify must return False without
    # throwing.
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
    from cryptography import x509 as _x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization

    private_key = _rsa.generate_private_key(
        public_exponent=65537, key_size=2048,
    )
    subject = _x509.Name([
        _x509.NameAttribute(NameOID.COMMON_NAME, "test-idp"),
    ])
    cert = (
        _x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(1)
        .not_valid_before(
            datetime.now(timezone.utc) - timedelta(days=1),
        )
        .not_valid_after(
            datetime.now(timezone.utc) + timedelta(days=365),
        )
        .sign(private_key, hashes.SHA256())
    )
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    cert_b64 = base64.b64encode(cert_der).decode("ascii")
    assertion_xml = _build_assertion_xml()
    accepted = verify_envelope_rsa_sha256(
        assertion_xml=assertion_xml,
        trusted_certificates=(cert_b64,),
    )
    testbase.assert_equal(accepted, False)
    return
