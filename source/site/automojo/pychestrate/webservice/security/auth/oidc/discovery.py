"""
.. module:: security.auth.oidc.discovery
    :synopsis: OIDC discovery document cache.

The discovery cache fronts an IdP's
``.well-known/openid-configuration`` endpoint so the
authorization / token / JWKS URIs and the issuer claim are
in-process when the begin-login + callback paths run.

The cache key is the configured issuer URL (the canonical
identifier across IdPs). Each entry stores the parsed
:class:`DiscoveryDocument` plus the absolute deadline at
which the entry expires. The cache reader honors the
``max-age`` directive returned by the discovery response,
clamped to the configured ``[min_ttl, max_ttl]`` window
(default [5 min, 24 h]) so a hostile IdP can't force
either rapid re-fetching or arbitrarily-stale documents.

The fetch path is pluggable: callers supply a
:class:`DiscoveryFetcher` callable so the production code
can use ``urllib`` and tests can hand in a deterministic
fixture.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Mapping, Optional, Tuple


MIN_DISCOVERY_TTL: timedelta = timedelta(minutes=5)
MAX_DISCOVERY_TTL: timedelta = timedelta(hours=24)
DEFAULT_DISCOVERY_TTL: timedelta = timedelta(hours=1)


@dataclass(frozen=True)
class DiscoveryDocument:
    """
        Subset of the IdP's discovery payload Pychestrate
        cares about. The raw mapping is preserved for
        callers that need additional fields.

        :param issuer: Canonical issuer URL.
        :param authorization_endpoint: Auth-code endpoint.
        :param token_endpoint: Token-exchange endpoint.
        :param jwks_uri: JWKS endpoint for id_token sig
                         verification.
        :param raw: Original mapping returned by the IdP.
    """
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveryFetchResult:
    """
        Caller-side fetcher response.

        :param document: Parsed :class:`DiscoveryDocument`.
        :param max_age_seconds: Cache lifetime hint from the
                                IdP's ``Cache-Control`` header
                                (or response payload). ``None``
                                falls back to the cache's
                                default TTL.
    """
    document: DiscoveryDocument
    max_age_seconds: Optional[int] = None


DiscoveryFetcher = Callable[[str], DiscoveryFetchResult]


@dataclass(frozen=True)
class _CacheEntry:
    document: DiscoveryDocument
    cached_at: datetime
    expires_at: datetime


_LOCK = threading.RLock()
_CACHE: Dict[str, _CacheEntry] = {}


def reset_for_testing() -> None:
    """
        Drop every cached document. Tests use this to keep
        the module-level cache from leaking across cases.
    """
    with _LOCK:
        _CACHE.clear()
    return


def parse_discovery_document(
        *,
        payload: Mapping[str, Any]
    ) -> DiscoveryDocument:
    """
        Validate ``payload`` carries the four canonical
        endpoints and wrap into a :class:`DiscoveryDocument`.

        :raises: ValueError when any required field is
                 missing / non-string / empty.
    """
    required = (
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "jwks_uri",
    )
    for field_name in required:
        value = payload.get(field_name)
        if value is None or not isinstance(value, str) or len(value) == 0:
            err_lines = [
                "OIDC discovery payload is missing a required field.",
            ]
            err_lines.append("FIELD: {}".format(field_name))
            err_lines.append("PAYLOAD_KEYS: {}".format(
                sorted(payload.keys()),
            ))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None

    rtnval = DiscoveryDocument(
        issuer=payload["issuer"],
        authorization_endpoint=payload["authorization_endpoint"],
        token_endpoint=payload["token_endpoint"],
        jwks_uri=payload["jwks_uri"],
        raw=dict(payload),
    )
    return rtnval


def clamp_ttl(*, max_age_seconds: Optional[int]) -> timedelta:
    """
        Apply the [MIN_DISCOVERY_TTL, MAX_DISCOVERY_TTL]
        window to a caller-supplied ``max-age`` hint.
        ``None`` falls back to :data:`DEFAULT_DISCOVERY_TTL`.
    """
    if max_age_seconds is None:
        rtnval = DEFAULT_DISCOVERY_TTL
        return rtnval
    seconds = int(max_age_seconds)
    if seconds < int(MIN_DISCOVERY_TTL.total_seconds()):
        return MIN_DISCOVERY_TTL
    if seconds > int(MAX_DISCOVERY_TTL.total_seconds()):
        return MAX_DISCOVERY_TTL
    rtnval = timedelta(seconds=seconds)
    return rtnval


def load_and_cache(
        *,
        issuer: str,
        fetcher: DiscoveryFetcher,
        force_refresh: bool = False,
        now: Optional[datetime] = None
    ) -> DiscoveryDocument:
    """
        Return the discovery document for ``issuer``, hitting
        the cache when warm and falling through to
        ``fetcher`` otherwise. ``force_refresh=True`` bypasses
        the cache entirely.

        The fetched document's
        :attr:`DiscoveryFetchResult.max_age_seconds` is
        clamped via :func:`clamp_ttl` before the row lands.

        :raises: ValueError on empty ``issuer``.
    """
    if issuer is None or len(issuer) == 0:
        err_lines = ["load_and_cache requires a non-empty issuer."]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    materialized_now = now if now is not None else _now_utc()
    if force_refresh is False:
        cached = _read_cache(
            issuer=issuer, now=materialized_now,
        )
        if cached is not None:
            return cached
    fetch_result = fetcher(issuer)
    if fetch_result is None:
        err_lines = ["OIDC discovery fetcher returned None."]
        err_lines.append("ISSUER: {}".format(issuer))
        err_msg = os.linesep.join(err_lines)
        raise RuntimeError(err_msg) from None
    document = fetch_result.document
    ttl = clamp_ttl(max_age_seconds=fetch_result.max_age_seconds)
    expires_at = materialized_now + ttl
    entry = _CacheEntry(
        document=document,
        cached_at=materialized_now,
        expires_at=expires_at,
    )
    with _LOCK:
        _CACHE[issuer] = entry
    return document


def cached_document(
        *,
        issuer: str,
        now: Optional[datetime] = None
    ) -> Optional[DiscoveryDocument]:
    """
        Read the cached document for ``issuer`` without
        falling through to a fetcher. ``None`` on miss /
        expiry.
    """
    materialized_now = now if now is not None else _now_utc()
    rtnval = _read_cache(issuer=issuer, now=materialized_now)
    return rtnval


def invalidate(*, issuer: str) -> bool:
    """
        Drop the cached entry for ``issuer``. Returns
        ``True`` when an entry was removed, ``False`` when
        none existed.
    """
    with _LOCK:
        if issuer not in _CACHE:
            return False
        del _CACHE[issuer]
    return True


def _read_cache(
        *,
        issuer: str,
        now: datetime
    ) -> Optional[DiscoveryDocument]:
    with _LOCK:
        entry = _CACHE.get(issuer)
    if entry is None:
        return None
    if _is_expired(entry=entry, now=now):
        with _LOCK:
            _CACHE.pop(issuer, None)
        return None
    rtnval = entry.document
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
