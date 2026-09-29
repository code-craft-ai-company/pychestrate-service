"""
.. module:: public_endpoint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The service's public identity as signed into job envelopes:
               the issuer and the per-run forwarding URLs.

.. moduleauthor:: Code Craft AI LLC

Every orchestrator (test, RPA, build, provision) used to sign
``pychestrate.example.com/0.6.0`` into its envelopes as the issuer and
``https://pychestrate.example.com/api/v1/runs/<id>/progress`` /
``.../summary`` as the forwarding URLs (E2E-32). The host was a
placeholder, and no ``summary`` route exists; the pod reports its final
result to ``results/complete``.

The public base URL now comes from ``PYCHESTRATE_PUBLIC_BASE_URL``
(settings or environment; the deploy script sets it from
``--public-hostname``). When it is unset, envelopes carry a host-less
issuer (``pychestrate/<release>``) and service-relative URLs rather
than a made-up host.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os
import re

from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse


#: Environment variable consulted when no application persona is set up.
ENV_PUBLIC_BASE_URL: str = "PYCHESTRATE_PUBLIC_BASE_URL"

#: Issuer name used when no public base URL is configured.
DEFAULT_ISSUER_NAME: str = "pychestrate"

#: Release text used when the service version cannot be read.
UNKNOWN_RELEASE: str = "unknown"

#: The REST prefix the forwarding URLs live under.
API_PREFIX: str = "/api/v1"

_LOGGER = logging.getLogger("pychestrate.public_endpoint")

_POETRY_VERSION_PATTERN = re.compile(r"""^version\s*=\s*["']([^"']+)["']""", re.MULTILINE)
_MAX_PARENT_LEVELS: int = 10

_RELEASE_CACHE = {"release": None}


def _configured_public_base_url() -> str:
    """
        :returns: The raw configured value (settings or environment), or
                  an empty string.
    """
    from ccai.errors.exceptions import SemanticError

    configured = None
    try:
        from ccai.thisapp.wellknown import ThisApplicationSingleton
        from ccai.pychestrate.webservice.pychestrate_variables import (
            PychestrateVariablesDesc,
        )

        # Resolve against the current application instance, forgetting
        # any cached value so environment changes are honored (see
        # backup.locations for why the accessor is not used directly).
        var_desc = PychestrateVariablesDesc.PYCHESTRATE_PUBLIC_BASE_URL
        this_app = ThisApplicationSingleton()
        this_app.forget_variable(var_desc)
        configured = this_app.get_variable_value(var_desc)
    except SemanticError:
        configured = None

    if configured is None or len(str(configured).strip()) == 0:
        configured = os.environ.get(ENV_PUBLIC_BASE_URL, "")

    rtnval = str(configured).strip()
    return rtnval


def public_docs_url(address: str) -> str:
    """
        A documentation address as the catalog should publish it: a
        service-relative path (``/docs/extensions/...``) becomes absolute when
        the service knows its public address, so a caller outside a browser
        (``pyc plugin api``, a script) gets a link that opens. Anything else
        (an extension's own external address, an empty value) is unchanged.

        :param address: The ``docs_url`` a protocol or extension declares.

        :returns: The address to publish.
    """
    if not address.startswith("/"):
        return address
    try:
        base = resolve_public_base_url()
    except Exception:  # noqa: BLE001 -- the catalog must build without a base URL
        base = None
    if base is None:
        return address
    return base + address


def resolve_public_base_url() -> Optional[str]:
    """
        The configured public base URL without a trailing slash, e.g.
        ``https://pychestrate.lab.internal``.

        :returns: The base URL, or None when unset or not an absolute
                  ``http(s)`` URL (a malformed value is logged and
                  ignored rather than signed into envelopes).
    """
    raw = _configured_public_base_url().rstrip("/")
    if len(raw) == 0:
        return None

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or len(parsed.netloc) == 0:
        _LOGGER.warning(
            "pychestrate.public_endpoint.ignored_malformed_base_url value=%r "
            "(expected an absolute http(s) URL such as https://pychestrate.lab.internal)",
            raw,
        )
        return None

    rtnval = raw
    return rtnval


def service_release() -> str:
    """
        The service version from the checkout's ``pyproject.toml``,
        read once.

        :returns: Version text, or :data:`UNKNOWN_RELEASE`.
    """
    cached = _RELEASE_CACHE["release"]
    if cached is not None:
        return cached

    release = UNKNOWN_RELEASE
    current = Path(__file__).resolve().parent
    for _level in range(_MAX_PARENT_LEVELS):
        candidate = current / "pyproject.toml"
        if candidate.is_file():
            try:
                match = _POETRY_VERSION_PATTERN.search(candidate.read_text(encoding="utf-8"))
            except OSError:
                match = None
            if match is not None:
                release = match.group(1)
            break
        if current.parent == current:
            break
        current = current.parent

    _RELEASE_CACHE["release"] = release
    rtnval = release
    return rtnval


def service_issuer() -> str:
    """
        The envelope issuer: ``<public host>/<release>``, or
        ``pychestrate/<release>`` when no public base URL is configured.

        :returns: Issuer text.
    """
    base_url = resolve_public_base_url()
    name = DEFAULT_ISSUER_NAME
    if base_url is not None:
        name = urlparse(base_url).netloc
    rtnval = "{}/{}".format(name, service_release())
    return rtnval


def run_forwarding_urls(*, run_id: str) -> Tuple[str, str]:
    """
        The URLs a pod reports a run's progress and final result to:
        absolute under the public base URL, or service-relative paths
        when none is configured.

        :param run_id: Run UUID.

        :returns: ``(progress_url, summary_url)``; the summary URL is
                  the ``results/complete`` route.
    """
    base_url = resolve_public_base_url() or ""
    run_path = "{}{}/runs/{}".format(base_url, API_PREFIX, run_id)
    rtnval = ("{}/progress".format(run_path), "{}/results/complete".format(run_path))
    return rtnval


def run_forwarding_info(*, run_id: str):
    """
        The envelope's forwarding block for a run
        (:func:`run_forwarding_urls`, bearer auth).

        :param run_id: Run UUID.

        :returns: :class:`~jobs.envelope.schema.JobForwardingInfo`.
    """
    from ccai.pychestrate.webservice.jobs.envelope.schema import JobForwardingInfo

    progress_url, summary_url = run_forwarding_urls(run_id=run_id)
    rtnval = JobForwardingInfo(progress_url=progress_url, summary_url=summary_url, auth_method="bearer")
    return rtnval


__all__ = [
    "DEFAULT_ISSUER_NAME",
    "ENV_PUBLIC_BASE_URL",
    "public_docs_url",
    "resolve_public_base_url",
    "run_forwarding_info",
    "run_forwarding_urls",
    "service_issuer",
    "service_release",
]
