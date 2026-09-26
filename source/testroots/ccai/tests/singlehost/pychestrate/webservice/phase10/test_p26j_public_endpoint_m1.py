"""
.. module:: test_p26j_public_endpoint_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The envelope issuer and forwarding URLs come from the
               configured public base URL, never a placeholder host (E2E-32).

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Optional

from ccai import testbase

from ccai.pychestrate.webservice import public_endpoint


def _with_base_url(value: Optional[str], func):
    previous = os.environ.get(public_endpoint.ENV_PUBLIC_BASE_URL)
    if value is None:
        os.environ.pop(public_endpoint.ENV_PUBLIC_BASE_URL, None)
    else:
        os.environ[public_endpoint.ENV_PUBLIC_BASE_URL] = value
    try:
        rtnval = func()
    finally:
        if previous is None:
            os.environ.pop(public_endpoint.ENV_PUBLIC_BASE_URL, None)
        else:
            os.environ[public_endpoint.ENV_PUBLIC_BASE_URL] = previous
    return rtnval


def _snapshot():
    rtnval = (
        public_endpoint.service_issuer(),
        public_endpoint.run_forwarding_urls(run_id="run-1"),
    )
    return rtnval


def test_configured_base_url_names_the_issuer_and_absolute_urls():
    """
    **Feature: public endpoint (E2E-32)**
    **Property: with PYCHESTRATE_PUBLIC_BASE_URL set (trailing slash
    and all), the issuer is ``<host>/<release>`` and the forwarding URLs
    are absolute under it; the summary URL is results/complete.**
    """
    issuer, urls = _with_base_url("https://pyc.lab.internal/", _snapshot)
    release = public_endpoint.service_release()
    testbase.assert_equal(
        (issuer, urls),
        ("pyc.lab.internal/{}".format(release),
         ("https://pyc.lab.internal/api/v1/runs/run-1/progress",
          "https://pyc.lab.internal/api/v1/runs/run-1/results/complete")),
    )
    return


def test_unset_or_malformed_base_url_uses_no_host():
    """
    **Feature: public endpoint (E2E-32)**
    **Property: with no base URL, or one that is not an absolute
    http(s) URL, the issuer carries no host and the forwarding URLs are
    service-relative -- no placeholder host is ever signed.**
    """
    release = public_endpoint.service_release()
    expected = (
        "pychestrate/{}".format(release),
        ("/api/v1/runs/run-1/progress", "/api/v1/runs/run-1/results/complete"),
    )
    outcomes = [
        _with_base_url(None, _snapshot),
        _with_base_url("", _snapshot),
        _with_base_url("pyc.lab.internal", _snapshot),
        _with_base_url("ftp://pyc.lab.internal", _snapshot),
    ]
    testbase.assert_equal(outcomes, [expected] * 4)
    return


def test_service_release_reads_the_checkout_version():
    """
    **Feature: public endpoint (E2E-32)**
    **Property: the release is the pyproject version, not a hard-coded
    string.**
    """
    release = public_endpoint.service_release()
    testbase.assert_equal(
        (release != public_endpoint.UNKNOWN_RELEASE, release != "0.6.0"),
        (True, True),
    )
    return


def test_no_orchestrator_signs_a_placeholder_host():
    """
    **Feature: public endpoint (E2E-32)**
    **Property: the orchestrators no longer carry the
    pychestrate.example.com placeholder.**
    """
    from ccai.pychestrate.webservice.orchestration.build import service as build_service
    from ccai.pychestrate.webservice.orchestration.infra.runs import service as provision_service
    from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service
    from ccai.pychestrate.webservice.orchestration.test import orchestrator as test_orchestrator

    offenders = []
    for module in (build_service, provision_service, rpa_service, test_orchestrator):
        with open(module.__file__, "r", encoding="utf-8") as fh:
            if "pychestrate.example.com" in fh.read():
                offenders.append(module.__name__)
    testbase.assert_equal(offenders, [])
    return
