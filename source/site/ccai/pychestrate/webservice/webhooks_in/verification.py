"""
.. module:: webhooks_in.verification
    :synopsis: Constant-time signature verification for inbound parsers.

The verifier walks every :class:`SignatureHeaderSpec` declared
by a parser, computes the canonical digest with the supplied
shared secret, and uses :func:`hmac.compare_digest` for the
compare. M1 enforces *strong-or-rejected*: if the only
signature offered is marked ``weak=True``, verification fails
with ``reason="signature_weak"`` so legacy SHA-1-only providers
cannot slip through.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac

from dataclasses import dataclass
from typing import Mapping, Optional, Type

from ccai.pychestrate.webservice.webhooks_in.factories.inbound_webhook_parser import (
    InboundWebhookParserProtocol,
)
from ccai.pychestrate.webservice.webhooks_in.models import (
    SignatureAlgorithm,
    SignatureEncoding,
    SignatureHeaderSpec,
)


@dataclass(frozen=True)
class VerificationOutcome:
    """
        Result of a signature compare.

        :param verified: ``True`` when at least one strong
                         spec accepted the signature.
        :param matched_header: Header name that produced the
                               match, when verified.
        :param reason: Stable token (``"signature_invalid"``,
                       ``"signature_missing"``,
                       ``"signature_weak"``) when not verified.
        :param weak_only: ``True`` when the request offered
                          only weak signatures.
    """
    verified: bool
    matched_header: Optional[str] = None
    reason: Optional[str] = None
    weak_only: bool = False


def verify_signature(
        *,
        parser: Type[InboundWebhookParserProtocol],
        raw_bytes: bytes,
        headers: Mapping[str, str],
        shared_secret: bytes
    ) -> VerificationOutcome:
    """
        Run each :class:`SignatureHeaderSpec` declared by
        ``parser`` against ``headers`` in declaration order and
        return the verdict.

        :param parser: Parser implementation class supplying
                       the signature specs.
        :param raw_bytes: Raw request body bytes (the canonical
                          form fed to HMAC).
        :param headers: Request headers mapping; keys are
                        compared case-insensitively.
        :param shared_secret: Bytes resolved from
                              ``1-secrets-vault`` for the
                              configured webhook.

        :returns: :class:`VerificationOutcome`.
    """
    specs = parser.signature_headers()
    if specs is None or len(specs) == 0:
        rtnval = VerificationOutcome(
            verified=False,
            reason="signature_missing",
        )
        return rtnval

    seen_any_value = False
    seen_only_weak = True
    for spec in specs:
        provided = _read_header(headers=headers, name=spec.header)
        if provided is None or len(provided) == 0:
            continue
        seen_any_value = True
        if spec.weak is False:
            seen_only_weak = False
        ok = _compare_signature(
            spec=spec,
            shared_secret=shared_secret,
            raw_bytes=raw_bytes,
            provided=provided,
        )
        if ok is True:
            if spec.weak is True:
                # We accepted a weak match but only for parity;
                # the dispatcher upgrades the verdict to a
                # rejection when no strong spec confirmed.
                continue
            rtnval = VerificationOutcome(
                verified=True,
                matched_header=spec.header,
                weak_only=False,
            )
            return rtnval

    if seen_any_value is False:
        rtnval = VerificationOutcome(
            verified=False,
            reason="signature_missing",
        )
        return rtnval

    if seen_only_weak is True:
        rtnval = VerificationOutcome(
            verified=False,
            reason="signature_weak",
            weak_only=True,
        )
        return rtnval

    rtnval = VerificationOutcome(
        verified=False,
        reason="signature_invalid",
    )
    return rtnval


def _read_header(*, headers: Mapping[str, str], name: str) -> Optional[str]:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    rtnval: Optional[str] = None
    return rtnval


def _compare_signature(
        *,
        spec: SignatureHeaderSpec,
        shared_secret: bytes,
        raw_bytes: bytes,
        provided: str
    ) -> bool:
    """
        Constant-time compare of the provided header against
        the canonical digest computed with the shared secret.
    """
    if spec.algorithm == SignatureAlgorithm.OPAQUE_TOKEN:
        # The whole header value is the secret token; constant
        # time compare against the raw shared_secret bytes.
        try:
            provided_bytes = provided.encode("utf-8")
        except UnicodeError:
            rtnval = False
            return rtnval
        rtnval = hmac.compare_digest(provided_bytes, shared_secret)
        return rtnval

    digest_module = _select_digest(algorithm=spec.algorithm)
    if digest_module is None:
        rtnval = False
        return rtnval
    expected_digest_bytes = hmac.new(
        key=shared_secret, msg=raw_bytes, digestmod=digest_module,
    ).hexdigest()

    if spec.encoding == SignatureEncoding.HEX_WITH_PREFIX:
        prefix = spec.prefix or ""
        if not provided.startswith(prefix):
            rtnval = False
            return rtnval
        provided_digest = provided[len(prefix):]
    elif spec.encoding == SignatureEncoding.HEX:
        provided_digest = provided
    else:
        # RAW encoding has no canonical digest path on the HMAC
        # algorithms; treat as a non-match.
        rtnval = False
        return rtnval

    rtnval = hmac.compare_digest(
        provided_digest.lower(), expected_digest_bytes.lower(),
    )
    return rtnval


def _select_digest(*, algorithm: SignatureAlgorithm):
    if algorithm == SignatureAlgorithm.HMAC_SHA256:
        return hashlib.sha256
    if algorithm == SignatureAlgorithm.HMAC_SHA1:
        return hashlib.sha1
    return None
