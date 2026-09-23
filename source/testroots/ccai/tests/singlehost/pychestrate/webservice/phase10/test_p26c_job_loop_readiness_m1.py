"""
.. module:: test_p26c_job_loop_readiness_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The System Health "Job Execution Loop" subsystem reports
               the job loop's prerequisites (LD-02).

.. moduleauthor:: Code Craft AI LLC

Neither documented launcher could complete a job (no signing key under
dev-up, no enrollment CA under staging) and the only trace was one
boot-log line. :func:`jobs.readiness.describe_job_loop_readiness`
reports each prerequisite, and the System Health page shows it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile

from typing import Any, Callable, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.agents.factories.long_poll_transport import (
    LongPollTransport,
)
from ccai.pychestrate.webservice.clients.enrollment import ca_adapter
from ccai.pychestrate.webservice.clients.restapi.v1 import client_dispatch_routes
from ccai.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from ccai.pychestrate.webservice.jobs.readiness import describe_job_loop_readiness


_PRESIGN_ENV = "PYCHESTRATE_RESULT_PRESIGN_SECRET"
_PROXY_ENV = "PYCHESTRATE_TRUSTED_PROXY_ADDRESSES"


def _backend(document: Dict[str, Any], name: str) -> Dict[str, str]:
    for backend in document["backends"]:
        if backend["name"] == name:
            return backend
    raise AssertionError("backend {} missing from {}".format(name, document))


def _with_state(
        *,
        signing_key: bool,
        enrollment_ca: bool,
        presign_secret: Optional[str],
        transport: bool,
        trusted_proxies: Optional[str] = None
    ) -> Dict[str, Any]:
    """
        Describe the job loop with the given prerequisites in place,
        restoring every global afterwards.

        :returns: The readiness document.
    """
    saved_env = {name: os.environ.get(name) for name in (_PRESIGN_ENV, _PROXY_ENV)}
    saved_transport = client_dispatch_routes.ACTIVE_LONG_POLL_TRANSPORT
    envelope_signer.reset_for_testing()
    ca_adapter.reset_active_ca_for_testing()
    try:
        if signing_key is True:
            envelope_signer.set_active_signing_key(
                handle=envelope_signer.generate_dev_signing_key(key_id="p26c-ed25519"),
            )
        if enrollment_ca is True:
            ca_file = os.path.join(tempfile.mkdtemp(prefix="pyc-p26c-"), "ca.pem")
            with open(ca_file, "wb") as handle:
                handle.write(ca_adapter.generate_dev_ca(common_name="p26c CA"))
            ca_adapter.set_active_ca(ca=ca_adapter.load_ca_at_startup(
                source="file", file_path=ca_file, ca_id="p26c-ca",
            ))
        for name, value in ((_PRESIGN_ENV, presign_secret), (_PROXY_ENV, trusted_proxies)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        client_dispatch_routes.set_active_long_poll_transport(
            transport=LongPollTransport() if transport is True else None,
        )
        rtnval = describe_job_loop_readiness()
    finally:
        envelope_signer.reset_for_testing()
        ca_adapter.reset_active_ca_for_testing()
        client_dispatch_routes.set_active_long_poll_transport(transport=saved_transport)
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return rtnval


def _all_ready() -> Dict[str, Any]:
    rtnval = _with_state(signing_key=True, enrollment_ca=True, presign_secret="p26c-secret", transport=True)
    return rtnval


def test_job_loop_is_ok_when_every_prerequisite_is_in_place():
    """
    **Feature: job-loop readiness (LD-02)**
    **Property: with a signing key, an enrollment CA, a configured
    presign secret, the long-poll transport and loopback proxies the
    subsystem reports ok.**
    """
    document = _all_ready()
    testbase.assert_equal((document["name"], document["status"]), ("job-loop", "ok"))
    return


def test_missing_signing_key_degrades_the_job_loop():
    """
    **Feature: job-loop readiness (LD-02)**
    **Property: without an envelope signing key the subsystem is
    degraded and the signing-key row names the variables to set.**
    """
    document = _with_state(signing_key=False, enrollment_ca=True, presign_secret="s", transport=True)
    row = _backend(document, "envelope-signing-key")
    testbase.assert_equal(
        (document["status"], row["status"], "PYCHESTRATE_ENVELOPE_SIGNING_KEY_FILE_PATH" in row["reason"]),
        ("degraded", "degraded", True),
    )
    return


def test_missing_enrollment_ca_degrades_the_job_loop():
    """
    **Feature: job-loop readiness (LD-02)**
    **Property: without an enrollment CA the subsystem is degraded and
    the CA row names the variables to set.**
    """
    document = _with_state(signing_key=True, enrollment_ca=False, presign_secret="s", transport=True)
    row = _backend(document, "enrollment-ca")
    testbase.assert_equal(
        (document["status"], row["status"], "PYCHESTRATE_ENROLLMENT_CA_FILE_PATH" in row["reason"]),
        ("degraded", "degraded", True),
    )
    return


def test_unset_presign_secret_is_reported():
    """
    **Feature: job-loop readiness (LD-02)**
    **Property: a per-process random presign secret (variable unset) is
    reported as degraded -- uploads fail across workers.**
    """
    document = _with_state(signing_key=True, enrollment_ca=True, presign_secret=None, transport=True)
    testbase.assert_equal(_backend(document, "result-presign-secret")["status"], "degraded")
    return


def test_missing_dispatch_transport_is_reported():
    """
    **Feature: job-loop readiness (LD-02)**
    **Property: without the long-poll transport the dispatch-transport
    row is degraded.**
    """
    document = _with_state(signing_key=True, enrollment_ca=True, presign_secret="s", transport=False)
    testbase.assert_equal(_backend(document, "dispatch-transport")["status"], "degraded")
    return


def test_invalid_trusted_proxy_setting_is_an_error():
    """
    **Feature: job-loop readiness (LD-02)**
    **Property: an unparseable PYCHESTRATE_TRUSTED_PROXY_ADDRESSES makes
    the client-certificate-proxies row (and the subsystem) an error.**
    """
    document = _with_state(
        signing_key=True, enrollment_ca=True, presign_secret="s", transport=True,
        trusted_proxies="not-an-address",
    )
    testbase.assert_equal(
        (_backend(document, "client-certificate-proxies")["status"], document["status"]),
        ("error", "error"),
    )
    return
