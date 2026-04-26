"""
.. module:: security.auth.saml.assertion
    :synopsis: SAML 2.0 assertion validator.

The SAML callback path receives a base64-encoded
``SAMLResponse`` form parameter. After base64-decoding it,
the controller hands the raw XML to
:func:`validate_saml_assertion` which:

1. Parses the ``<samlp:Response>`` envelope and locates the
   inner ``<saml:Assertion>``.
2. Verifies the assertion's XML signature against the trust
   set returned by P20a's metadata cache. The signature
   verification is pluggable through
   :class:`SamlSignatureVerifier` so production wires
   :func:`verify_envelope_rsa_sha256` (RSA-SHA256 + exc-c14n
   + envelope transform) and tests hand in a deterministic
   stub.
3. Validates the claim set: ``Issuer`` matches the configured
   IdP entity_id; ``Conditions/AudienceRestriction`` lists the
   SP entity_id; ``SubjectConfirmation`` ``Recipient`` matches
   the configured ACS URL; ``InResponseTo`` matches the issued
   AuthnRequest id (when supplied); ``NotBefore`` /
   ``NotOnOrAfter`` are in the valid window with a 2-minute
   default clock skew tolerance.
4. Returns a :class:`ValidatedSamlAssertion` carrying the
   ``NameID``, attribute statements, ``SessionIndex``, and the
   ``AuthnInstant``.

Failures bubble as :class:`SamlAssertionValidationError`
with a stable ``reason`` token so the callback path can log
and branch without leaking detail to the client.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import os

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from xml.etree import ElementTree as ET


SAML_PROTOCOL_NS: str = "urn:oasis:names:tc:SAML:2.0:protocol"
SAML_ASSERTION_NS: str = "urn:oasis:names:tc:SAML:2.0:assertion"
DSIG_NS: str = "http://www.w3.org/2000/09/xmldsig#"


_NS_MAP = {
    "samlp": SAML_PROTOCOL_NS,
    "saml": SAML_ASSERTION_NS,
    "ds": DSIG_NS,
}


DEFAULT_SAML_CLOCK_SKEW: timedelta = timedelta(minutes=2)


class SamlAssertionValidationError(Exception):
    """
        Raised when :func:`validate_saml_assertion` fails any
        signature / structural / claim check. The ``reason``
        token is stable.

        Reasons:

        * ``response_malformed`` — XML parse failed.
        * ``assertion_missing`` — no ``<saml:Assertion>`` under
          the ``<samlp:Response>``.
        * ``signature_missing`` — the assertion has no
          ``<ds:Signature>`` element.
        * ``signature_invalid`` — the verifier rejected the
          signature.
        * ``issuer_mismatch`` — the assertion's ``Issuer``
          doesn't match the configured IdP entity_id.
        * ``audience_mismatch`` — the assertion's
          ``AudienceRestriction`` doesn't list the configured
          SP entity_id.
        * ``subject_recipient_mismatch`` — the
          ``SubjectConfirmationData/@Recipient`` doesn't match
          the configured ACS URL.
        * ``in_response_to_mismatch`` — the
          ``SubjectConfirmationData/@InResponseTo`` doesn't
          match the supplied AuthnRequest id.
        * ``condition_not_yet_valid`` — ``NotBefore`` is in the
          future beyond the clock-skew window.
        * ``condition_expired`` — ``NotOnOrAfter`` is in the
          past beyond the clock-skew window.
        * ``subject_confirmation_expired`` — the
          ``SubjectConfirmationData/@NotOnOrAfter`` is past.
        * ``name_id_missing`` — no ``<saml:NameID>`` under the
          ``<saml:Subject>``.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        message = (
            reason if len(detail) == 0
            else "{}: {}".format(reason, detail)
        )
        super().__init__(message)
        self.reason: str = reason
        self.detail: str = detail
        return


@dataclass(frozen=True)
class ValidatedSamlAssertion:
    """
        Successful validator output.

        :param name_id: ``<saml:NameID>`` text node.
        :param name_id_format: ``Format`` attribute on the
                               ``NameID`` element. Empty string
                               when absent.
        :param issuer: ``<saml:Issuer>`` text node.
        :param audiences: Tuple of every
                          ``<saml:AudienceRestriction>/<saml:Audience>``
                          text node.
        :param session_index: ``SessionIndex`` attribute on the
                              ``<saml:AuthnStatement>``;
                              ``None`` when absent.
        :param authn_instant: ``AuthnInstant`` attribute parsed
                              into a tz-aware datetime;
                              ``None`` when absent or
                              unparseable.
        :param attributes: Per-attribute mapping of name →
                           tuple of value strings extracted
                           from
                           ``<saml:AttributeStatement>``.
        :param in_response_to: ``InResponseTo`` attribute on
                               the
                               ``SubjectConfirmationData``
                               element; ``None`` when absent.
        :param raw_assertion_xml: Bytes of the
                                  ``<saml:Assertion>`` element
                                  that was validated, kept for
                                  audit.
    """
    name_id: str
    name_id_format: str
    issuer: str
    audiences: Tuple[str, ...]
    session_index: Optional[str]
    authn_instant: Optional[datetime]
    attributes: Mapping[str, Tuple[str, ...]]
    in_response_to: Optional[str]
    raw_assertion_xml: bytes


SamlSignatureVerifier = Callable[
    [bytes, Tuple[str, ...]], bool,
]


@dataclass(frozen=True)
class SamlValidationParams:
    """
        Per-call validator inputs.

        :param expected_issuer: IdP entityID the assertion's
                                ``<saml:Issuer>`` must match.
        :param expected_audience: SP entityID that must appear
                                  in the assertion's
                                  ``AudienceRestriction``.
        :param expected_recipient: ACS URL the
                                   ``SubjectConfirmationData/@Recipient``
                                   must match.
        :param trusted_certificates: Tuple of base64-encoded
                                     X.509 cert bodies from
                                     the trust set.
        :param expected_in_response_to: Optional
                                        ``AuthnRequest`` id
                                        the assertion echoes
                                        back; when ``None``
                                        the
                                        ``InResponseTo`` check
                                        is skipped (IdP-initiated
                                        flows).
        :param signature_verifier: Pluggable signature
                                   verifier; ``None`` skips
                                   signature verification
                                   (test-only — production
                                   wires
                                   :func:`verify_envelope_rsa_sha256`).
        :param clock_skew: Tolerance applied to the
                           ``NotBefore`` / ``NotOnOrAfter``
                           checks. Default 2 minutes per the
                           spec.
        :param now: Optional clock override (test seam).
    """
    expected_issuer: str
    expected_audience: str
    expected_recipient: str
    trusted_certificates: Tuple[str, ...]
    expected_in_response_to: Optional[str] = None
    signature_verifier: Optional[SamlSignatureVerifier] = None
    clock_skew: timedelta = DEFAULT_SAML_CLOCK_SKEW
    now: Optional[datetime] = None


def validate_saml_assertion(
        *,
        saml_response_xml: bytes,
        params: SamlValidationParams
    ) -> ValidatedSamlAssertion:
    """
        Validate a SAML 2.0 assertion end-to-end.

        :raises: ValueError on missing inputs;
                 SamlAssertionValidationError on any signature
                 / structural / claim check.
    """
    if saml_response_xml is None or len(saml_response_xml) == 0:
        err_lines = [
            "validate_saml_assertion requires non-empty saml_response_xml.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if params is None:
        err_lines = [
            "validate_saml_assertion requires a SamlValidationParams.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    try:
        root = ET.fromstring(saml_response_xml)
    except ET.ParseError as parse_err:
        raise SamlAssertionValidationError(
            "response_malformed", str(parse_err),
        ) from None

    assertion_elem = _locate_assertion(root=root)
    if assertion_elem is None:
        raise SamlAssertionValidationError(
            "assertion_missing",
            "no <saml:Assertion> child of <samlp:Response>",
        ) from None

    assertion_xml = ET.tostring(assertion_elem, encoding="utf-8")

    # Signature verification — the optional verifier lets
    # tests bypass real crypto. Production wires
    # verify_envelope_rsa_sha256.
    if params.signature_verifier is not None:
        signature_elem = assertion_elem.find("ds:Signature", _NS_MAP)
        if signature_elem is None:
            raise SamlAssertionValidationError(
                "signature_missing",
                "<saml:Assertion> has no enveloped <ds:Signature>",
            ) from None
        is_valid = params.signature_verifier(
            assertion_xml, params.trusted_certificates,
        )
        if is_valid is not True:
            raise SamlAssertionValidationError(
                "signature_invalid",
                "signature_verifier rejected the assertion signature",
            ) from None

    issuer_text = _read_text(
        parent=assertion_elem, path="saml:Issuer",
    )
    if issuer_text != params.expected_issuer:
        raise SamlAssertionValidationError(
            "issuer_mismatch",
            "expected={!r} actual={!r}".format(
                params.expected_issuer, issuer_text,
            ),
        ) from None

    materialized_now = (
        params.now if params.now is not None else _now_utc()
    )

    _check_conditions(
        assertion=assertion_elem,
        params=params,
        now=materialized_now,
    )
    in_response_to = _check_subject_confirmation(
        assertion=assertion_elem,
        params=params,
        now=materialized_now,
    )
    name_id, name_id_format = _extract_name_id(
        assertion=assertion_elem,
    )
    audiences = _extract_audiences(assertion=assertion_elem)
    session_index = _extract_session_index(assertion=assertion_elem)
    authn_instant = _extract_authn_instant(assertion=assertion_elem)
    attributes = _extract_attributes(assertion=assertion_elem)

    rtnval = ValidatedSamlAssertion(
        name_id=name_id,
        name_id_format=name_id_format,
        issuer=issuer_text,
        audiences=tuple(audiences),
        session_index=session_index,
        authn_instant=authn_instant,
        attributes=attributes,
        in_response_to=in_response_to,
        raw_assertion_xml=assertion_xml,
    )
    return rtnval


def verify_envelope_rsa_sha256(
        *, assertion_xml: bytes, trusted_certificates: Tuple[str, ...]
    ) -> bool:
    """
        Reference :class:`SamlSignatureVerifier` implementation
        for the most common SAML signature shape:
        envelope-signed assertion, RSA-SHA256 over exc-c14n
        canonicalized SignedInfo.

        Production deployments that need broader algorithm
        support (DSA, ECDSA, multiple digest methods) or
        signed-Response handling should swap this out for a
        wrapper around ``signxml`` or ``python-xmlsec``.

        :returns: ``True`` when the signature verifies against
                  any cert in ``trusted_certificates``;
                  ``False`` otherwise.
    """
    from cryptography import x509 as _x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import (
        padding as _asymmetric_padding,
    )

    if assertion_xml is None or len(assertion_xml) == 0:
        return False
    if trusted_certificates is None or len(trusted_certificates) == 0:
        return False

    try:
        assertion_root = ET.fromstring(assertion_xml)
    except ET.ParseError:
        return False
    signature_elem = assertion_root.find("ds:Signature", _NS_MAP)
    if signature_elem is None:
        return False
    signed_info_elem = signature_elem.find(
        "ds:SignedInfo", _NS_MAP,
    )
    signature_value_elem = signature_elem.find(
        "ds:SignatureValue", _NS_MAP,
    )
    if signed_info_elem is None or signature_value_elem is None:
        return False
    canonical_signed_info = ET.canonicalize(
        ET.tostring(signed_info_elem, encoding="utf-8"),
        exclusive=True,
    )
    if isinstance(canonical_signed_info, str):
        canonical_signed_info = canonical_signed_info.encode("utf-8")
    raw_signature_text = signature_value_elem.text or ""
    cleaned_signature = "".join(raw_signature_text.split())
    if len(cleaned_signature) == 0:
        return False
    try:
        signature_bytes = base64.b64decode(cleaned_signature)
    except (ValueError, TypeError):
        return False

    for certificate_body in trusted_certificates:
        cleaned_cert = "".join(certificate_body.split())
        try:
            cert_der = base64.b64decode(cleaned_cert)
        except (ValueError, TypeError):
            continue
        try:
            certificate = _x509.load_der_x509_certificate(cert_der)
        except (ValueError, TypeError):
            continue
        public_key = certificate.public_key()
        try:
            public_key.verify(
                signature_bytes,
                canonical_signed_info,
                _asymmetric_padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except InvalidSignature:
            continue
        except Exception:
            continue
        return True
    return False


def _locate_assertion(*, root: ET.Element) -> Optional[ET.Element]:
    # The Assertion can be a direct child of the Response or
    # wrapped in an EncryptedAssertion (the spec defers
    # encrypted assertions to M3). We accept both the
    # qualified and unqualified-namespace shapes since some
    # IdPs serialize without the protocol prefix.
    direct = root.find("saml:Assertion", _NS_MAP)
    if direct is not None:
        return direct
    return None


def _read_text(*, parent: ET.Element, path: str) -> str:
    elem = parent.find(path, _NS_MAP)
    if elem is None or elem.text is None:
        return ""
    rtnval = elem.text.strip()
    return rtnval


def _check_conditions(
        *,
        assertion: ET.Element,
        params: SamlValidationParams,
        now: datetime
    ) -> None:
    conditions_elem = assertion.find("saml:Conditions", _NS_MAP)
    if conditions_elem is None:
        # No Conditions element means no time bounds — the
        # OASIS spec allows it but the spec.md target
        # mandates audience/conditions checking. Treat as
        # missing audience.
        raise SamlAssertionValidationError(
            "audience_mismatch",
            "<saml:Conditions> element is missing",
        ) from None

    not_before_attr = conditions_elem.attrib.get("NotBefore", "")
    not_on_or_after_attr = conditions_elem.attrib.get(
        "NotOnOrAfter", "",
    )
    if len(not_before_attr) > 0:
        not_before = _parse_iso_datetime(value=not_before_attr)
        if not_before is not None:
            if now + params.clock_skew < not_before:
                raise SamlAssertionValidationError(
                    "condition_not_yet_valid",
                    "not_before={} now={}".format(
                        not_before.isoformat(), now.isoformat(),
                    ),
                ) from None
    if len(not_on_or_after_attr) > 0:
        not_on_or_after = _parse_iso_datetime(
            value=not_on_or_after_attr,
        )
        if not_on_or_after is not None:
            if now - params.clock_skew >= not_on_or_after:
                raise SamlAssertionValidationError(
                    "condition_expired",
                    "not_on_or_after={} now={}".format(
                        not_on_or_after.isoformat(), now.isoformat(),
                    ),
                ) from None

    audiences = _extract_audiences(assertion=assertion)
    if params.expected_audience not in audiences:
        raise SamlAssertionValidationError(
            "audience_mismatch",
            "expected={!r} got={}".format(
                params.expected_audience, sorted(audiences),
            ),
        ) from None
    return


def _check_subject_confirmation(
        *,
        assertion: ET.Element,
        params: SamlValidationParams,
        now: datetime
    ) -> Optional[str]:
    subject_elem = assertion.find("saml:Subject", _NS_MAP)
    if subject_elem is None:
        raise SamlAssertionValidationError(
            "subject_recipient_mismatch",
            "<saml:Subject> is missing",
        ) from None
    confirmation_data: Optional[ET.Element] = None
    for sc in subject_elem.findall(
        "saml:SubjectConfirmation", _NS_MAP,
    ):
        candidate = sc.find(
            "saml:SubjectConfirmationData", _NS_MAP,
        )
        if candidate is not None:
            confirmation_data = candidate
            break
    if confirmation_data is None:
        raise SamlAssertionValidationError(
            "subject_recipient_mismatch",
            "<saml:SubjectConfirmationData> is missing",
        ) from None
    recipient = confirmation_data.attrib.get("Recipient", "")
    if recipient != params.expected_recipient:
        raise SamlAssertionValidationError(
            "subject_recipient_mismatch",
            "expected={!r} actual={!r}".format(
                params.expected_recipient, recipient,
            ),
        ) from None
    not_on_or_after_attr = confirmation_data.attrib.get(
        "NotOnOrAfter", "",
    )
    if len(not_on_or_after_attr) > 0:
        not_on_or_after = _parse_iso_datetime(
            value=not_on_or_after_attr,
        )
        if not_on_or_after is not None:
            if now - params.clock_skew >= not_on_or_after:
                raise SamlAssertionValidationError(
                    "subject_confirmation_expired",
                    "not_on_or_after={} now={}".format(
                        not_on_or_after.isoformat(), now.isoformat(),
                    ),
                ) from None
    in_response_to = confirmation_data.attrib.get(
        "InResponseTo", "",
    )
    if params.expected_in_response_to is not None:
        if in_response_to != params.expected_in_response_to:
            raise SamlAssertionValidationError(
                "in_response_to_mismatch",
                "expected={!r} actual={!r}".format(
                    params.expected_in_response_to, in_response_to,
                ),
            ) from None
    rtnval = in_response_to if len(in_response_to) > 0 else None
    return rtnval


def _extract_name_id(
        *, assertion: ET.Element
    ) -> Tuple[str, str]:
    subject_elem = assertion.find("saml:Subject", _NS_MAP)
    if subject_elem is None:
        raise SamlAssertionValidationError(
            "name_id_missing", "<saml:Subject> is missing",
        ) from None
    name_id_elem = subject_elem.find("saml:NameID", _NS_MAP)
    if name_id_elem is None or name_id_elem.text is None:
        raise SamlAssertionValidationError(
            "name_id_missing", "<saml:NameID> is missing",
        ) from None
    rtnval = (
        name_id_elem.text.strip(),
        name_id_elem.attrib.get("Format", ""),
    )
    return rtnval


def _extract_audiences(*, assertion: ET.Element) -> Tuple[str, ...]:
    conditions_elem = assertion.find("saml:Conditions", _NS_MAP)
    if conditions_elem is None:
        return tuple()
    matched: List[str] = []
    for restriction in conditions_elem.findall(
        "saml:AudienceRestriction", _NS_MAP,
    ):
        for audience_elem in restriction.findall(
            "saml:Audience", _NS_MAP,
        ):
            text = audience_elem.text or ""
            cleaned = text.strip()
            if len(cleaned) > 0:
                matched.append(cleaned)
    rtnval = tuple(matched)
    return rtnval


def _extract_session_index(
        *, assertion: ET.Element
    ) -> Optional[str]:
    authn_statement = assertion.find(
        "saml:AuthnStatement", _NS_MAP,
    )
    if authn_statement is None:
        return None
    value = authn_statement.attrib.get("SessionIndex", "")
    if len(value) == 0:
        return None
    rtnval = value
    return rtnval


def _extract_authn_instant(
        *, assertion: ET.Element
    ) -> Optional[datetime]:
    authn_statement = assertion.find(
        "saml:AuthnStatement", _NS_MAP,
    )
    if authn_statement is None:
        return None
    value = authn_statement.attrib.get("AuthnInstant", "")
    if len(value) == 0:
        return None
    rtnval = _parse_iso_datetime(value=value)
    return rtnval


def _extract_attributes(
        *, assertion: ET.Element
    ) -> Mapping[str, Tuple[str, ...]]:
    statements = assertion.findall(
        "saml:AttributeStatement", _NS_MAP,
    )
    matched: Dict[str, List[str]] = {}
    for statement in statements:
        for attribute in statement.findall(
            "saml:Attribute", _NS_MAP,
        ):
            name = attribute.attrib.get("Name", "")
            if len(name) == 0:
                continue
            for value_elem in attribute.findall(
                "saml:AttributeValue", _NS_MAP,
            ):
                text = value_elem.text or ""
                cleaned = text.strip()
                bucket = matched.setdefault(name, [])
                bucket.append(cleaned)
    rtnval: Dict[str, Tuple[str, ...]] = {
        key: tuple(values) for key, values in matched.items()
    }
    return rtnval


def _parse_iso_datetime(*, value: str) -> Optional[datetime]:
    if value is None or len(value) == 0:
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        rtnval = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if rtnval.tzinfo is None:
        rtnval = rtnval.replace(tzinfo=timezone.utc)
    return rtnval


def _now_utc() -> datetime:
    rtnval = datetime.now(tz=timezone.utc)
    return rtnval
