"""
.. module:: security.auth.saml.metadata
    :synopsis: SAML 2.0 IdP metadata refresh + atomic trust-set rotation.

The SAML callback path verifies the IdP's response against
the *currently-trusted* set of signing certificates. That
set lives in this module's per-``provider_name`` cache,
which the bootstrap path warms via
:func:`refresh_metadata_document`.

Atomic trust-set rotation: the cache stores one fully-built
:class:`SamlIdpMetadata` instance per provider. Concurrent
callers of :func:`current_trust_set` either see the prior
instance or the fresh one — never a partial set of
certificates. The rotation is a single dict-write under the
module lock.

The fetcher is pluggable so production wires ``urllib`` and
tests hand in a deterministic stub. The ``cacheDuration`` /
``validUntil`` hints from the metadata XML drive the cache
TTL, clamped to ``[60s, 24h]`` with a 3600s default per the
spec's ``metadata_refresh_seconds`` baseline.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re
import threading

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional, Tuple
from xml.etree import ElementTree as ET


MIN_METADATA_TTL: timedelta = timedelta(seconds=60)
MAX_METADATA_TTL: timedelta = timedelta(hours=24)
DEFAULT_METADATA_TTL: timedelta = timedelta(seconds=3600)


SAML_MD_NS: str = "urn:oasis:names:tc:SAML:2.0:metadata"
DSIG_NS: str = "http://www.w3.org/2000/09/xmldsig#"
HTTP_REDIRECT_BINDING: str = (
    "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
)
HTTP_POST_BINDING: str = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"


_NS_MAP = {"md": SAML_MD_NS, "ds": DSIG_NS}


class SamlMetadataParseError(Exception):
    """
        Raised when an IdP metadata XML document is missing a
        required field, malformed, or carries no usable
        signing certificate.

        Reasons (stable strings on ``reason``):

        * ``xml_malformed`` — XML parse failed.
        * ``entity_id_missing`` — no ``entityID`` attribute on
          the root descriptor.
        * ``idp_descriptor_missing`` — no
          ``IDPSSODescriptor`` element.
        * ``sso_endpoint_missing`` — no
          ``SingleSignOnService`` element with a recognized
          binding.
        * ``signing_certificate_missing`` — no
          ``KeyDescriptor[use='signing']`` (or unscoped
          ``KeyDescriptor``) with an ``X509Certificate``
          element.
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
class SamlIdpMetadata:
    """
        Parsed view of an IdP's SAML metadata document.

        :param entity_id: ``entityID`` attribute — the
                          canonical IdP identifier the
                          assertion's ``Issuer`` element must
                          equal.
        :param sso_redirect_url: ``Location`` of the
                                 ``HTTP-Redirect``
                                 ``SingleSignOnService``.
                                 ``""`` when the IdP only
                                 advertises POST.
        :param sso_post_url: ``Location`` of the ``HTTP-POST``
                             ``SingleSignOnService``. ``""``
                             when the IdP only advertises
                             redirect.
        :param signing_certificates: Tuple of base64-encoded
                                     X.509 certificate strings
                                     (the body of every
                                     ``KeyDescriptor[use='signing']``
                                     element, with whitespace
                                     stripped).
        :param want_authn_requests_signed: ``True`` when the
                                           IdP advertises
                                           ``WantAuthnRequestsSigned='true'``.
        :param cache_duration_seconds: Optional ``cacheDuration``
                                       hint parsed off the root
                                       descriptor; ``None`` when
                                       absent.
        :param valid_until: Optional ``validUntil`` hint parsed
                            off the root descriptor; ``None``
                            when absent.
        :param raw_xml: Original XML bytes — kept so callers
                        can re-serialize for audit / debug.
    """
    entity_id: str
    sso_redirect_url: str
    sso_post_url: str
    signing_certificates: Tuple[str, ...]
    want_authn_requests_signed: bool
    cache_duration_seconds: Optional[int]
    valid_until: Optional[datetime]
    raw_xml: bytes


@dataclass(frozen=True)
class SamlMetadataFetchResult:
    """
        Caller-side fetcher response.

        :param document_xml: Raw metadata XML bytes.
        :param max_age_seconds: Optional ``Cache-Control:
                                max-age`` hint from the HTTP
                                response. ``None`` lets the
                                cache fall back to the XML's
                                ``cacheDuration`` /
                                :data:`DEFAULT_METADATA_TTL`.
    """
    document_xml: bytes
    max_age_seconds: Optional[int] = None


SamlMetadataFetcher = Callable[[str], SamlMetadataFetchResult]


@dataclass(frozen=True)
class _CacheEntry:
    metadata: SamlIdpMetadata
    cached_at: datetime
    expires_at: datetime
    metadata_url: str


_LOCK: threading.RLock = threading.RLock()
_CACHE: Dict[str, _CacheEntry] = {}


def reset_for_testing() -> None:
    """
        Drop every cached trust set. Test-only seam.
    """
    with _LOCK:
        _CACHE.clear()
    return


def parse_metadata_document(*, xml_bytes: bytes) -> SamlIdpMetadata:
    """
        Parse an IdP metadata XML document into a
        :class:`SamlIdpMetadata`.

        :raises: SamlMetadataParseError with a stable reason
                 token.
    """
    if xml_bytes is None or len(xml_bytes) == 0:
        raise SamlMetadataParseError(
            "xml_malformed", "empty document",
        ) from None
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as parse_err:
        raise SamlMetadataParseError(
            "xml_malformed", str(parse_err),
        ) from None

    entity_id = root.attrib.get("entityID", "")
    if entity_id is None or len(entity_id) == 0:
        raise SamlMetadataParseError(
            "entity_id_missing",
            "root EntityDescriptor lacks entityID",
        ) from None

    idp_descriptor = root.find("md:IDPSSODescriptor", _NS_MAP)
    if idp_descriptor is None:
        raise SamlMetadataParseError(
            "idp_descriptor_missing",
            "no IDPSSODescriptor under EntityDescriptor",
        ) from None

    redirect_url, post_url = _extract_sso_endpoints(
        descriptor=idp_descriptor,
    )
    if len(redirect_url) == 0 and len(post_url) == 0:
        raise SamlMetadataParseError(
            "sso_endpoint_missing",
            "no SingleSignOnService with HTTP-Redirect or HTTP-POST binding",
        ) from None

    certs = _extract_signing_certificates(
        descriptor=idp_descriptor,
    )
    if len(certs) == 0:
        raise SamlMetadataParseError(
            "signing_certificate_missing",
            "no KeyDescriptor[use='signing'] with X509Certificate",
        ) from None

    want_signed_attr = idp_descriptor.attrib.get(
        "WantAuthnRequestsSigned", "false",
    )
    want_authn_requests_signed = (
        want_signed_attr.lower() == "true"
    )
    cache_duration_seconds = _parse_cache_duration(
        attribute=root.attrib.get("cacheDuration", ""),
    )
    valid_until = _parse_iso_datetime(
        attribute=root.attrib.get("validUntil", ""),
    )

    rtnval = SamlIdpMetadata(
        entity_id=entity_id,
        sso_redirect_url=redirect_url,
        sso_post_url=post_url,
        signing_certificates=tuple(certs),
        want_authn_requests_signed=want_authn_requests_signed,
        cache_duration_seconds=cache_duration_seconds,
        valid_until=valid_until,
        raw_xml=bytes(xml_bytes),
    )
    return rtnval


def clamp_ttl(*, max_age_seconds: Optional[int]) -> timedelta:
    """
        Apply the ``[MIN_METADATA_TTL, MAX_METADATA_TTL]``
        window to a caller-supplied hint. ``None`` falls
        back to :data:`DEFAULT_METADATA_TTL`.
    """
    if max_age_seconds is None:
        rtnval = DEFAULT_METADATA_TTL
        return rtnval
    seconds = int(max_age_seconds)
    if seconds < int(MIN_METADATA_TTL.total_seconds()):
        return MIN_METADATA_TTL
    if seconds > int(MAX_METADATA_TTL.total_seconds()):
        return MAX_METADATA_TTL
    rtnval = timedelta(seconds=seconds)
    return rtnval


def refresh_metadata_document(
        *,
        provider_name: str,
        metadata_url: str,
        fetcher: SamlMetadataFetcher,
        force_refresh: bool = False,
        now: Optional[datetime] = None
    ) -> SamlIdpMetadata:
    """
        Re-read the IdP metadata document for
        ``provider_name`` and atomically rotate the cached
        trust set.

        :param provider_name: Per-deployment provider name
                              (matches the URL segment in
                              ``/auth/saml/{provider_name}/...``).
        :param metadata_url: IdP metadata-document URL.
        :param fetcher: Pluggable callable that performs the
                        HTTP GET against the metadata URL.
        :param force_refresh: When ``True`` bypass the cache
                              entirely; otherwise return the
                              cached entry if it has not
                              expired.
        :param now: Optional clock override (test seam).

        :returns: Newly-cached :class:`SamlIdpMetadata`.
        :raises: ValueError on missing inputs;
                 SamlMetadataParseError on bad XML.
    """
    if provider_name is None or len(provider_name) == 0:
        err_lines = [
            "refresh_metadata_document requires a non-empty provider_name.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if metadata_url is None or len(metadata_url) == 0:
        err_lines = [
            "refresh_metadata_document requires a non-empty metadata_url.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if fetcher is None:
        err_lines = [
            "refresh_metadata_document requires a fetcher.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    # Local imports keep the metadata module loadable
    # before the auth package's instrumentation modules
    # are wired in by phase11+ tests.
    from automojo.pychestrate.webservice.security.auth import (
        log_events as _log_events,
        metrics_emitter as _metrics_emitter,
    )
    from automojo.pychestrate.webservice.security.auth.tracing import (
        SPAN_SAML_METADATA_REFRESH as _SPAN_SAML_METADATA_REFRESH,
        start_span as _start_span,
    )

    materialized_now = now if now is not None else _now_utc()
    if force_refresh is False:
        cached = _read_cache(
            provider_name=provider_name, now=materialized_now,
        )
        if cached is not None:
            return cached

    with _start_span(
        name=_SPAN_SAML_METADATA_REFRESH,
        attributes={"provider_name": provider_name},
    ) as span:
        try:
            fetch_result = fetcher(metadata_url)
            if fetch_result is None:
                err_lines = [
                    "SAML metadata fetcher returned None.",
                    "PROVIDER_NAME: {}".format(provider_name),
                    "METADATA_URL: {}".format(metadata_url),
                ]
                err_msg = os.linesep.join(err_lines)
                raise RuntimeError(err_msg) from None
            metadata = parse_metadata_document(
                xml_bytes=fetch_result.document_xml,
            )
        except Exception:
            # Failed refresh: record the metric + log event
            # so operators see the failure rate. The
            # exception bubbles unchanged; the cached row
            # (if any) stays put per NFR-4.
            _metrics_emitter.record_saml_metadata_refresh_failure(
                # We don't have a db_session here — call the
                # safe helper via a sentinel so the recorder
                # short-circuits when no driver is wired.
                db_session=None,
                provider_name=provider_name,
            )
            _log_events.emit_log_event(
                event_name=_log_events.AUTH_SAML_METADATA_REFRESH_FAILED,
                payload={
                    "provider_name": provider_name,
                    "metadata_url": metadata_url,
                },
            )
            raise
        span.set_attribute(
            key="entity_id", value=metadata.entity_id,
        )
        span.set_attribute(
            key="signing_cert_count",
            value=len(metadata.signing_certificates),
        )
    ttl_hint = (
        fetch_result.max_age_seconds
        if fetch_result.max_age_seconds is not None
        else metadata.cache_duration_seconds
    )
    ttl = clamp_ttl(max_age_seconds=ttl_hint)
    expires_at = materialized_now + ttl
    if metadata.valid_until is not None:
        normalized_valid = _normalize_aware(value=metadata.valid_until)
        if normalized_valid < expires_at:
            expires_at = normalized_valid

    entry = _CacheEntry(
        metadata=metadata,
        cached_at=materialized_now,
        expires_at=expires_at,
        metadata_url=metadata_url,
    )
    # Atomic trust-set rotation: a single dict assignment
    # swaps the previous trust set out for the new one;
    # concurrent readers see one or the other, never both.
    with _LOCK:
        _CACHE[provider_name] = entry

    _log_events.emit_log_event(
        event_name=_log_events.AUTH_SAML_METADATA_REFRESHED,
        payload={
            "provider_name": provider_name,
            "entity_id": metadata.entity_id,
            "expires_at": expires_at.isoformat(),
            "signing_cert_count": len(metadata.signing_certificates),
        },
    )
    return metadata


def current_trust_set(
        *,
        provider_name: str,
        now: Optional[datetime] = None
    ) -> Optional[SamlIdpMetadata]:
    """
        Read the cached trust set for ``provider_name``.
        Returns ``None`` on miss or expiry without falling
        through to a fetcher.
    """
    materialized_now = now if now is not None else _now_utc()
    rtnval = _read_cache(
        provider_name=provider_name, now=materialized_now,
    )
    return rtnval


def invalidate(*, provider_name: str) -> bool:
    """
        Drop the cached entry for ``provider_name``.
        Returns ``True`` when an entry was removed,
        ``False`` when none existed.
    """
    with _LOCK:
        if provider_name not in _CACHE:
            return False
        del _CACHE[provider_name]
    return True


def _read_cache(
        *,
        provider_name: str,
        now: datetime
    ) -> Optional[SamlIdpMetadata]:
    with _LOCK:
        entry = _CACHE.get(provider_name)
    if entry is None:
        return None
    if _is_expired(entry=entry, now=now):
        with _LOCK:
            _CACHE.pop(provider_name, None)
        return None
    rtnval = entry.metadata
    return rtnval


def _is_expired(*, entry: _CacheEntry, now: datetime) -> bool:
    deadline = entry.expires_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    rtnval = now >= deadline
    return rtnval


def _now_utc() -> datetime:
    rtnval = datetime.now(tz=timezone.utc)
    return rtnval


def _extract_sso_endpoints(
        *, descriptor: ET.Element
    ) -> Tuple[str, str]:
    redirect_url = ""
    post_url = ""
    for sso in descriptor.findall("md:SingleSignOnService", _NS_MAP):
        binding = sso.attrib.get("Binding", "")
        location = sso.attrib.get("Location", "")
        if binding == HTTP_REDIRECT_BINDING and len(location) > 0:
            if len(redirect_url) == 0:
                redirect_url = location
        elif binding == HTTP_POST_BINDING and len(location) > 0:
            if len(post_url) == 0:
                post_url = location
    rtnval = (redirect_url, post_url)
    return rtnval


def _extract_signing_certificates(
        *, descriptor: ET.Element
    ) -> Tuple[str, ...]:
    matched: list = []
    for key_descriptor in descriptor.findall(
        "md:KeyDescriptor", _NS_MAP,
    ):
        use = key_descriptor.attrib.get("use", "")
        # Per the OASIS SAML 2.0 metadata schema an
        # un-scoped KeyDescriptor is usable for both
        # signing and encryption — we accept it for the
        # signing trust set.
        if use not in ("", "signing"):
            continue
        for cert_elem in key_descriptor.findall(
            "ds:KeyInfo/ds:X509Data/ds:X509Certificate",
            _NS_MAP,
        ):
            text = cert_elem.text or ""
            cleaned = "".join(text.split())
            if len(cleaned) > 0:
                matched.append(cleaned)
    rtnval = tuple(matched)
    return rtnval


_DURATION_RE = re.compile(
    r"^(?P<sign>-)?P"
    r"(?:(?P<years>\d+)Y)?"
    r"(?:(?P<months>\d+)M)?"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
    r")?$"
)


def _parse_cache_duration(*, attribute: str) -> Optional[int]:
    """
        Parse an XML-Schema ``xs:duration`` literal into
        seconds. ``None`` when the attribute is empty or
        unparseable. Years and months are not unambiguously
        convertible to seconds; we use 365d / 30d
        approximations because the value gets clamped to the
        24h ceiling anyway.
    """
    if attribute is None or len(attribute) == 0:
        return None
    match = _DURATION_RE.match(attribute.strip())
    if match is None:
        return None
    parts = match.groupdict()
    seconds = 0
    if parts.get("years") is not None:
        seconds += int(parts["years"]) * 365 * 24 * 3600
    if parts.get("months") is not None:
        seconds += int(parts["months"]) * 30 * 24 * 3600
    if parts.get("days") is not None:
        seconds += int(parts["days"]) * 24 * 3600
    if parts.get("hours") is not None:
        seconds += int(parts["hours"]) * 3600
    if parts.get("minutes") is not None:
        seconds += int(parts["minutes"]) * 60
    if parts.get("seconds") is not None:
        seconds += int(float(parts["seconds"]))
    if parts.get("sign") == "-":
        return None
    if seconds == 0:
        return None
    rtnval = seconds
    return rtnval


def _parse_iso_datetime(*, attribute: str) -> Optional[datetime]:
    if attribute is None or len(attribute) == 0:
        return None
    raw = attribute.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        rtnval = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if rtnval.tzinfo is None:
        rtnval = rtnval.replace(tzinfo=timezone.utc)
    return rtnval


def _normalize_aware(*, value: datetime) -> datetime:
    if value.tzinfo is None:
        rtnval = value.replace(tzinfo=timezone.utc)
        return rtnval
    rtnval = value
    return rtnval
