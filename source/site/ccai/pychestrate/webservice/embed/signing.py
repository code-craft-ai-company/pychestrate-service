"""
.. module:: webservice.embed.signing
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HMAC-SHA-256 signing primitives for embed URLs.

.. moduleauthor:: Code Craft AI LLC

The signing service composes a canonical payload and HMAC-SHA-256
signs it under the active key. The wire URL embeds every field
needed to verify the signature without external state lookup beyond
``key_id`` → key bytes (:func:`resolve_key_callable`). M1 leaves the
key store implementation to a caller-supplied resolver so this
module is fully testable without a database / vault.

Canonical payload layout (per spec §1.4):

    "<view_kind>|<resource_id>|<audience>|<expires_unix>|<key_id>"

Wire URL layout:

    /embed/<view_kind>/<resource_id>?a=<audience>&e=<expires_unix>&k=<key_id>&s=<signature_hex>

Verification rules:

* ``hmac.compare_digest`` for the signature compare (constant-time).
* ``now >= expires_unix`` rejects with :data:`VerificationOutcome.EXPIRED`.
* The ``view_kind`` / ``resource_id`` / ``audience`` / ``key_id`` /
  ``expires_unix`` quintet are bound into the signed payload — any
  tampered field invalidates the signature.

The module emits :class:`VerificationOutcome` rather than raising on
the verification failure path so callers can branch on a stable
machine-readable token (rendered into the audit log via
``embed.url_rejected.reason=<outcome>``).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum
import hmac
import hashlib
import os

from dataclasses import dataclass
from typing import Callable, Optional

from ccai.errors.exceptions import ConfigurationError, SemanticError

from ccai.pychestrate.webservice.embed.view_catalog import (
    EMBED_NAMESPACE_PREFIX,
    EmbedViewKind,
    get_view_kind,
)


CANONICAL_FIELD_SEPARATOR: str = "|"
SIGNATURE_QUERY_KEY: str = "s"
EXPIRES_QUERY_KEY: str = "e"
KEY_ID_QUERY_KEY: str = "k"
AUDIENCE_QUERY_KEY: str = "a"


class VerificationOutcome(str, enum.Enum):
    """
        Documented machine-readable verification result.

        :param VERIFIED: Signature checked and TTL is in the future.
        :param SIGNATURE_MISMATCH: Constant-time compare rejected.
        :param EXPIRED: ``now >= expires_unix``.
        :param SIGNING_KEY_UNKNOWN: Resolver returned None / raised.
        :param MALFORMED_PAYLOAD: One of the required URL fields was
                                  missing or empty.
    """
    VERIFIED = "verified"
    SIGNATURE_MISMATCH = "signature_mismatch"
    EXPIRED = "expired"
    SIGNING_KEY_UNKNOWN = "signing_key_unknown"
    MALFORMED_PAYLOAD = "malformed_payload"


@dataclass(frozen=True)
class EmbedSigningKey:
    """
        Resolved signing key — what the caller-supplied resolver
        returns to :func:`verify_signed_url`. The actual storage
        lives in :mod:`secrets` (M2 wires that path); the dataclass
        stays minimal so test resolvers can construct one inline.

        :param key_id: 12-byte base32 identifier embedded in the URL.
        :param key_bytes: Raw HMAC key material (caller manages
                          rotation + revocation lifecycle).
    """
    key_id: str
    key_bytes: bytes


@dataclass(frozen=True)
class SignedEmbedUrl:
    """
        Successful issuance result returned by
        :func:`issue_signed_url`.

        :param url: Fully-rendered ``/embed/...`` URL.
        :param key_id: Key id that signed the URL.
        :param expires_unix: Unix timestamp when the URL expires.
        :param view_kind: Resolved :class:`EmbedViewKind`.
        :param canonical_payload: The exact bytes the signer signed
                                  (exposed for tests + audit logs).
    """
    url: str
    key_id: str
    expires_unix: int
    view_kind: EmbedViewKind
    canonical_payload: str


@dataclass(frozen=True)
class SignatureVerificationFailure:
    """
        Verification failure detail returned alongside
        :data:`VerificationOutcome.SIGNATURE_MISMATCH` (and friends).

        :param outcome: The :class:`VerificationOutcome` value.
        :param diagnostic: Operator-facing string. Free-form; safe
                           to surface in audit logs.
    """
    outcome: VerificationOutcome
    diagnostic: str


def _build_canonical_payload(
        *,
        view_kind: str,
        resource_id: str,
        audience: str,
        expires_unix: int,
        key_id: str
    ) -> str:
    """
        Compose the documented canonical payload string.

        :param view_kind: Catalog view-kind name.
        :param resource_id: Caller-supplied resource id.
        :param audience: Caller-supplied audience claim.
        :param expires_unix: Unix expiry timestamp.
        :param key_id: Signing key id.

        :returns: ``"<view_kind>|<resource_id>|<audience>|<expires_unix>|<key_id>"``.
    """
    parts = [
        str(view_kind),
        str(resource_id),
        str(audience),
        str(int(expires_unix)),
        str(key_id),
    ]
    rtnval = CANONICAL_FIELD_SEPARATOR.join(parts)
    return rtnval


def _hmac_sign(*, key_bytes: bytes, payload: str) -> str:
    """
        HMAC-SHA-256 sign ``payload`` and return lower-hex.

        :param key_bytes: Raw key material.
        :param payload: Canonical payload string.

        :returns: Lowercase hex digest.
    """
    digest = hmac.new(
        key_bytes,
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    rtnval = digest
    return rtnval


def _validate_issuance_inputs(
        *,
        view_kind: EmbedViewKind,
        resource_id: str,
        audience: str,
        ttl_seconds: int
    ) -> None:
    """
        Reject issuance inputs that would produce an unparseable
        canonical payload (separator-bearing strings, non-positive
        TTL).

        :returns: None.
        :raises: SemanticError on invariant violation.
    """
    if resource_id is None or len(resource_id) == 0:
        raise SemanticError("issue_signed_url requires non-empty resource_id")
    if audience is None or len(audience) == 0:
        raise SemanticError("issue_signed_url requires non-empty audience")
    if ttl_seconds <= 0:
        raise SemanticError(
            "issue_signed_url requires positive ttl_seconds; got {}".format(ttl_seconds)
        )

    for label, value in (
        ("view_kind", view_kind.view_kind_name),
        ("resource_id", resource_id),
        ("audience", audience),
    ):
        if CANONICAL_FIELD_SEPARATOR in value:
            err_msg_lines = [
                "Embed payload field cannot contain '{}'.".format(
                    CANONICAL_FIELD_SEPARATOR
                )
            ]
            err_msg_lines.append("FIELD: {}".format(label))
            err_msg_lines.append("VALUE: {!r}".format(value))
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg) from None

    return


def issue_signed_url(
        *,
        view_kind: str,
        resource_id: str,
        audience: str,
        ttl_seconds: int,
        signing_key: EmbedSigningKey,
        now_unix: int
    ) -> SignedEmbedUrl:
    """
        Mint a signed embed URL.

        :param view_kind: View-kind name from the fixed catalog.
        :param resource_id: Caller-supplied resource identifier.
        :param audience: Caller-supplied audience claim (typically
                         the consuming portal's hostname).
        :param ttl_seconds: Validity window in seconds; the wire
                            ``e`` parameter is ``now_unix + ttl_seconds``.
        :param signing_key: Active :class:`EmbedSigningKey`.
        :param now_unix: Caller-supplied current time (Unix seconds).
                         Tests inject a fixed value so the URL is
                         deterministic.

        :returns: :class:`SignedEmbedUrl`.
        :raises: ConfigurationError on unknown view_kind;
                 SemanticError on invalid resource_id / audience /
                 ttl_seconds.
    """
    resolved_view_kind = get_view_kind(view_kind_name=view_kind)
    _validate_issuance_inputs(
        view_kind=resolved_view_kind,
        resource_id=resource_id,
        audience=audience,
        ttl_seconds=ttl_seconds,
    )

    expires_unix = int(now_unix) + int(ttl_seconds)
    canonical_payload = _build_canonical_payload(
        view_kind=resolved_view_kind.view_kind_name,
        resource_id=resource_id,
        audience=audience,
        expires_unix=expires_unix,
        key_id=signing_key.key_id,
    )
    signature_hex = _hmac_sign(
        key_bytes=signing_key.key_bytes, payload=canonical_payload
    )

    url = "{prefix}{view_kind}/{resource_id}?{a}={audience}&{e}={expires}&{k}={key_id}&{s}={sig}".format(
        prefix=EMBED_NAMESPACE_PREFIX,
        view_kind=resolved_view_kind.view_kind_name,
        resource_id=resource_id,
        a=AUDIENCE_QUERY_KEY,
        audience=audience,
        e=EXPIRES_QUERY_KEY,
        expires=expires_unix,
        k=KEY_ID_QUERY_KEY,
        key_id=signing_key.key_id,
        s=SIGNATURE_QUERY_KEY,
        sig=signature_hex,
    )

    rtnval = SignedEmbedUrl(
        url=url,
        key_id=signing_key.key_id,
        expires_unix=expires_unix,
        view_kind=resolved_view_kind,
        canonical_payload=canonical_payload,
    )
    return rtnval


def _empty_or_none(value: Optional[str]) -> bool:
    """
        Return True when ``value`` is None or zero-length.
    """
    if value is None:
        rtnval = True
        return rtnval
    rtnval = len(value) == 0
    return rtnval


def verify_signed_url(
        *,
        view_kind: str,
        resource_id: str,
        audience: str,
        expires_unix: int,
        key_id: str,
        signature_hex: str,
        now_unix: int,
        key_resolver: Callable[[str], Optional[EmbedSigningKey]]
    ) -> VerificationOutcome:
    """
        Constant-time verify a signed embed URL.

        :param view_kind: Catalog view-kind name (usually parsed from
                          the URL path segment).
        :param resource_id: Resource id from the URL path segment.
        :param audience: ``a`` query-string value.
        :param expires_unix: ``e`` query-string value (parsed to int).
        :param key_id: ``k`` query-string value.
        :param signature_hex: ``s`` query-string value.
        :param now_unix: Caller-supplied current time (Unix seconds).
        :param key_resolver: Callable returning the
                             :class:`EmbedSigningKey` for a key id, or
                             None when the key is unknown / expired /
                             revoked. M2 hooks this to the live key
                             store.

        :returns: :class:`VerificationOutcome`.
    """
    if _empty_or_none(view_kind):
        rtnval = VerificationOutcome.MALFORMED_PAYLOAD
        return rtnval
    if _empty_or_none(resource_id):
        rtnval = VerificationOutcome.MALFORMED_PAYLOAD
        return rtnval
    if _empty_or_none(audience):
        rtnval = VerificationOutcome.MALFORMED_PAYLOAD
        return rtnval
    if _empty_or_none(key_id):
        rtnval = VerificationOutcome.MALFORMED_PAYLOAD
        return rtnval
    if _empty_or_none(signature_hex):
        rtnval = VerificationOutcome.MALFORMED_PAYLOAD
        return rtnval

    try:
        resolved_view_kind = get_view_kind(view_kind_name=view_kind)
    except ConfigurationError:
        rtnval = VerificationOutcome.MALFORMED_PAYLOAD
        return rtnval

    _ = resolved_view_kind  # the catalog lookup proves the kind is known

    if int(now_unix) >= int(expires_unix):
        rtnval = VerificationOutcome.EXPIRED
        return rtnval

    try:
        signing_key = key_resolver(key_id)
    except Exception:  # noqa: BLE001 — purposeful: resolver errors are key-unknown.
        rtnval = VerificationOutcome.SIGNING_KEY_UNKNOWN
        return rtnval

    if signing_key is None:
        rtnval = VerificationOutcome.SIGNING_KEY_UNKNOWN
        return rtnval

    canonical_payload = _build_canonical_payload(
        view_kind=view_kind,
        resource_id=resource_id,
        audience=audience,
        expires_unix=int(expires_unix),
        key_id=key_id,
    )
    expected_signature = _hmac_sign(
        key_bytes=signing_key.key_bytes, payload=canonical_payload
    )

    matched = hmac.compare_digest(
        expected_signature.encode("utf-8"),
        signature_hex.encode("utf-8"),
    )
    if matched is True:
        rtnval = VerificationOutcome.VERIFIED
        return rtnval

    rtnval = VerificationOutcome.SIGNATURE_MISMATCH
    return rtnval
