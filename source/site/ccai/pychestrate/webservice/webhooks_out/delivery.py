"""
.. module:: webhooks_out.delivery
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Put a signed outbound webhook request on the wire.

.. moduleauthor:: Code Craft AI LLC

:func:`send_signed_request` POSTs a :class:`SignedRequest` built by
:func:`webhooks_out.service.build_signed_request` and reports what
happened as a :class:`SendResult` the caller records with
:func:`webhooks_out.service.record_delivery_attempt`.

A subscription URL is user-supplied, so the server refuses to call
addresses that would let a subscription reach the Pychestrate server
itself, its local services or the host's metadata service: loopback,
link-local (including ``169.254.169.254``), unspecified, multicast and
reserved addresses, and ``localhost``. Private ranges stay allowed --
on-premises receivers live there. Redirects are not followed (a 3xx
answer is recorded as a failed delivery), so a receiver cannot bounce
the request to a refused address.

Before audit ORC-04 nothing sent outbound requests: a test event was
recorded as ``pending`` and stayed that way.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import ipaddress
import socket
import time
import urllib.error
import urllib.request

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from ccai.pychestrate.webservice.webhooks_out.models import DeliveryOutcome
from ccai.pychestrate.webservice.webhooks_out.service import SignedRequest


#: Seconds a delivery may take (connect + response) before it fails.
DELIVERY_TIMEOUT_SECONDS: float = 10.0

#: Bytes of the receiver's response body kept on the delivery row.
MAX_RESPONSE_EXCERPT_BYTES: int = 512

#: URL schemes a subscription may use.
DELIVERY_URL_SCHEMES = ("http", "https")


@dataclass(frozen=True)
class SendResult:
    """
        What one delivery attempt produced.

        :param outcome: ``SUCCEEDED`` for a 2xx answer, ``FAILED``
                        otherwise (including requests never sent).
        :param response_status: The receiver's HTTP status, or
                                ``None`` when no answer arrived.
        :param response_excerpt: Start of the response body, or why
                                 the request was not sent / answered.
        :param duration_ms: Wall-clock milliseconds spent.
    """
    outcome: DeliveryOutcome
    response_status: Optional[int]
    response_excerpt: Optional[str]
    duration_ms: int


def forbidden_address_reason(*, address: str) -> Optional[str]:
    """
        Why the server must not deliver to ``address``, or ``None``
        when it may.

        :param address: IPv4 or IPv6 address literal.

        :returns: A human-readable reason, or ``None``.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        rtnval = "an address that is not valid ({})".format(address)
        return rtnval
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    rtnval: Optional[str] = None
    if ip.is_loopback:
        rtnval = "a loopback address ({})".format(ip)
    elif ip.is_link_local:
        rtnval = "a link-local address ({})".format(ip)
    elif ip.is_unspecified:
        rtnval = "an unspecified address ({})".format(ip)
    elif ip.is_multicast:
        rtnval = "a multicast address ({})".format(ip)
    elif ip.is_reserved:
        rtnval = "a reserved address ({})".format(ip)
    return rtnval


def check_delivery_url(*, url: str) -> Optional[str]:
    """
        Check that the server may deliver to ``url``: an http(s)
        URL whose host is not ``localhost`` and does not resolve to
        a refused address (see :func:`forbidden_address_reason`).

        :param url: The subscription URL.

        :returns: Why the URL is refused, or ``None`` when allowed.
    """
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        rtnval = "the URL is not valid"
        return rtnval
    if parsed.scheme not in DELIVERY_URL_SCHEMES:
        rtnval = "the URL must start with http:// or https://"
        return rtnval
    host = parsed.hostname
    if host is None or len(host) == 0:
        rtnval = "the URL has no host"
        return rtnval
    lowered = host.lower()
    if lowered == "localhost" or lowered.endswith(".localhost"):
        rtnval = "the URL targets the Pychestrate server itself (localhost)"
        return rtnval

    try:
        port = parsed.port
    except ValueError:
        rtnval = "the URL port is not valid"
        return rtnval
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        rtnval = "the host '{}' could not be resolved".format(host)
        return rtnval
    for info in infos:
        reason = forbidden_address_reason(address=str(info[4][0]))
        if reason is not None:
            rtnval = "the host '{}' resolves to {}, which webhooks may not target".format(host, reason)
            return rtnval
    return None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
        Refuse every redirect so a receiver cannot bounce a delivery
        to an address :func:`check_delivery_url` would refuse.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 -- urllib hook
        return None


def _excerpt(*, raw: bytes) -> str:
    """
        Decode the first :data:`MAX_RESPONSE_EXCERPT_BYTES` of a
        response body.

        :param raw: Response bytes.

        :returns: Text excerpt.
    """
    rtnval = raw[:MAX_RESPONSE_EXCERPT_BYTES].decode("utf-8", errors="replace")
    return rtnval


def send_signed_request(
        *,
        signed: SignedRequest,
        timeout_seconds: float = DELIVERY_TIMEOUT_SECONDS
    ) -> SendResult:
    """
        POST ``signed`` to its URL and report the outcome. Never
        raises for network or receiver errors -- they are reported
        as a ``FAILED`` result.

        :param signed: The signed request to send.
        :param timeout_seconds: Connect + read timeout.

        :returns: The :class:`SendResult`.
    """
    started = time.monotonic()
    refused = check_delivery_url(url=signed.url)
    if refused is not None:
        rtnval = SendResult(
            outcome=DeliveryOutcome.FAILED,
            response_status=None,
            response_excerpt="not sent: {}".format(refused),
            duration_ms=_elapsed_ms(started=started),
        )
        return rtnval

    request = urllib.request.Request(
        url=signed.url,
        data=bytes(signed.body),
        headers=dict(signed.headers),
        method=signed.method,
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status = int(response.status)
            body = response.read(MAX_RESPONSE_EXCERPT_BYTES)
        outcome = DeliveryOutcome.SUCCEEDED if 200 <= status < 300 else DeliveryOutcome.FAILED
        rtnval = SendResult(
            outcome=outcome,
            response_status=status,
            response_excerpt=_excerpt(raw=body),
            duration_ms=_elapsed_ms(started=started),
        )
    except urllib.error.HTTPError as xcpt:
        body = b""
        try:
            body = xcpt.read(MAX_RESPONSE_EXCERPT_BYTES)
        except Exception:  # noqa: BLE001 -- the status is what matters
            body = b""
        excerpt = _excerpt(raw=body)
        if 300 <= int(xcpt.code) < 400:
            excerpt = "redirect not followed (HTTP {})".format(int(xcpt.code))
        rtnval = SendResult(
            outcome=DeliveryOutcome.FAILED,
            response_status=int(xcpt.code),
            response_excerpt=excerpt,
            duration_ms=_elapsed_ms(started=started),
        )
    except (urllib.error.URLError, OSError, ValueError) as xcpt:
        reason = getattr(xcpt, "reason", None)
        rtnval = SendResult(
            outcome=DeliveryOutcome.FAILED,
            response_status=None,
            response_excerpt="not delivered: {}".format(reason if reason is not None else xcpt),
            duration_ms=_elapsed_ms(started=started),
        )
    return rtnval


def _elapsed_ms(*, started: float) -> int:
    """
        Milliseconds since ``started`` (a :func:`time.monotonic`
        reading).

        :param started: Start reading.

        :returns: Elapsed milliseconds.
    """
    rtnval = int(round((time.monotonic() - started) * 1000.0))
    return rtnval


__all__ = [
    "DELIVERY_TIMEOUT_SECONDS",
    "MAX_RESPONSE_EXCERPT_BYTES",
    "SendResult",
    "check_delivery_url",
    "forbidden_address_reason",
    "send_signed_request",
]
