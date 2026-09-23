"""
.. module:: jobs.readiness
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Report whether this service instance can run the job
               execution loop, for the System Health page.

.. moduleauthor:: Code Craft AI LLC

A service can serve every page and still be unable to complete a job:
without an envelope signing key every dispatch fails, without a
client-enrollment CA no pod can enroll, without a shared presign
secret result uploads fail whenever two workers split the presign and
the upload, and without trusted client-certificate proxies no pod
request carries an identity. None of that was visible anywhere but a
single boot-log line.

:func:`describe_job_loop_readiness` inspects the live seams (nothing
is loaded or changed) and returns a System Health subsystem document:
one ``backends`` row per prerequisite, each naming the environment
variables that fix it. A missing prerequisite reports ``degraded``,
not ``error``: the service itself is healthy, and a UI- or REST-only
deployment may deliberately run without pods.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, List


STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_ERROR = "error"

#: Subsystem name / label on the System Health page.
JOB_LOOP_SUBSYSTEM_NAME = "job-loop"
JOB_LOOP_SUBSYSTEM_LABEL = "Job Execution Loop"

#: Presign secret variable (read by ``runs.restapi.v1.artifacts_routes``).
ENV_RESULT_PRESIGN_SECRET = "PYCHESTRATE_RESULT_PRESIGN_SECRET"


def _backend(*, name: str, status: str, reason: str) -> Dict[str, str]:
    rtnval = {"name": name, "status": status, "reason": reason}
    return rtnval


def _check_envelope_signing_key() -> Dict[str, str]:
    """
        Is an envelope signing key installed?
    """
    from ccai.pychestrate.webservice.jobs.envelope import signer
    from ccai.pychestrate.webservice.jobs.envelope.errors import (
        EnvelopeSigningKeyMissingError,
    )
    try:
        handle = signer.get_active_signing_key()
    except EnvelopeSigningKeyMissingError:
        rtnval = _backend(
            name="envelope-signing-key", status=STATUS_DEGRADED,
            reason=(
                "Not installed -- every dispatch fails. Set PYCHESTRATE_ENVELOPE_SIGNING_KEY_SOURCE=file,"
                " PYCHESTRATE_ENVELOPE_SIGNING_KEY_FILE_PATH (base64 Ed25519 seed) and"
                " PYCHESTRATE_ENVELOPE_SIGNING_KEY_ID."
            ),
        )
        return rtnval
    rtnval = _backend(
        name="envelope-signing-key", status=STATUS_OK,
        reason="Installed (key_id={}).".format(handle.key_id),
    )
    return rtnval


def _check_enrollment_ca() -> Dict[str, str]:
    """
        Is a client-enrollment CA installed?
    """
    from ccai.pychestrate.webservice.clients.enrollment import ca_adapter
    from ccai.pychestrate.webservice.clients.exceptions import (
        CertificateAuthorityUnavailableError,
    )
    try:
        handle = ca_adapter.get_active_ca()
    except CertificateAuthorityUnavailableError:
        rtnval = _backend(
            name="enrollment-ca", status=STATUS_DEGRADED,
            reason=(
                "Not installed -- pods cannot enroll (redeem answers 503). Set"
                " PYCHESTRATE_ENROLLMENT_CA_SOURCE=file, PYCHESTRATE_ENROLLMENT_CA_FILE_PATH (CA certificate"
                " and key in one PEM) and PYCHESTRATE_ENROLLMENT_CA_ID."
            ),
        )
        return rtnval
    rtnval = _backend(
        name="enrollment-ca", status=STATUS_OK,
        reason="Installed (ca_id={}, issuer {}).".format(handle.ca_id, handle.issuer_subject),
    )
    return rtnval


def _check_result_presign_secret() -> Dict[str, str]:
    """
        Is the result-upload presign secret shared (configured) rather
        than generated per process?
    """
    raw = os.environ.get(ENV_RESULT_PRESIGN_SECRET, "")
    if raw is not None and len(raw.strip()) > 0:
        rtnval = _backend(
            name="result-presign-secret", status=STATUS_OK,
            reason="Configured ({}).".format(ENV_RESULT_PRESIGN_SECRET),
        )
        return rtnval
    rtnval = _backend(
        name="result-presign-secret", status=STATUS_DEGRADED,
        reason=(
            "Not configured -- each worker process signs upload URLs with its own random secret, so"
            " uploads fail whenever another worker receives them. Set {}.".format(ENV_RESULT_PRESIGN_SECRET)
        ),
    )
    return rtnval


def _check_dispatch_transport() -> Dict[str, str]:
    """
        Is the pod long-poll dispatch transport published?
    """
    from ccai.pychestrate.webservice.clients.restapi.v1 import client_dispatch_routes
    transport = client_dispatch_routes.ACTIVE_LONG_POLL_TRANSPORT
    if transport is None:
        rtnval = _backend(
            name="dispatch-transport", status=STATUS_DEGRADED,
            reason="Not configured -- pods polling dispatches:next receive 503.",
        )
        return rtnval
    rtnval = _backend(
        name="dispatch-transport", status=STATUS_OK,
        reason="Long-poll queue active ({}).".format(transport.transport_name()),
    )
    return rtnval


def _check_client_certificate_proxies() -> Dict[str, str]:
    """
        Which proxies may vouch for a pod's client certificate?
    """
    from ccai.errors.exceptions import ConfigurationError
    from ccai.pychestrate.webservice.clients import mtls_identity
    try:
        policy = mtls_identity.trusted_proxy_addresses_from_environment()
    except ConfigurationError as xcpt:
        rtnval = _backend(name="client-certificate-proxies", status=STATUS_ERROR, reason=str(xcpt))
        return rtnval
    if policy.trust_any is False and len(policy.networks) == 0:
        rtnval = _backend(
            name="client-certificate-proxies", status=STATUS_DEGRADED,
            reason=(
                "{} is set but empty -- pod identity is accepted only from a TLS-terminating server"
                " that sets SSL_CLIENT_S_DN_CN.".format(mtls_identity.ENV_TRUSTED_PROXY_ADDRESSES)
            ),
        )
        return rtnval
    reason = "Trusted for {} / {}: {}.".format(
        mtls_identity.CLIENT_CERT_CN_HEADER, mtls_identity.CLIENT_CERT_VERIFY_HEADER,
        mtls_identity.describe_trusted_proxies(trusted_proxies=policy),
    )
    if policy.trust_any is True:
        reason = reason + " Any peer can assert a pod identity: safe only when nothing but the TLS terminator reaches the service."
    rtnval = _backend(name="client-certificate-proxies", status=STATUS_OK, reason=reason)
    return rtnval


def describe_job_loop_readiness() -> Dict[str, Any]:
    """
        Build the System Health subsystem document for the job
        execution loop.

        :returns: Dict with ``name``, ``label``, ``status``, ``detail``
                  and a ``backends`` list (``name`` / ``status`` /
                  ``reason`` per prerequisite).
    """
    checks = (
        _check_envelope_signing_key,
        _check_enrollment_ca,
        _check_result_presign_secret,
        _check_dispatch_transport,
        _check_client_certificate_proxies,
    )
    backends: List[Dict[str, str]] = []
    for check in checks:
        try:
            backends.append(check())
        except Exception as xcpt:  # noqa: BLE001 -- one failing probe must not hide the others
            backends.append(_backend(
                name=check.__name__.replace("_check_", "").replace("_", "-"),
                status=STATUS_ERROR,
                reason="Probe failed: {}".format(type(xcpt).__name__),
            ))

    problems = [backend for backend in backends if backend["status"] != STATUS_OK]
    if any(backend["status"] == STATUS_ERROR for backend in problems):
        status = STATUS_ERROR
    elif len(problems) > 0:
        status = STATUS_DEGRADED
    else:
        status = STATUS_OK

    if len(problems) == 0:
        detail = "Pods can enroll, receive signed jobs and upload results."
    else:
        detail = "{} of {} prerequisites missing: {}.".format(
            len(problems), len(backends), ", ".join(backend["name"] for backend in problems),
        )

    rtnval = {
        "name": JOB_LOOP_SUBSYSTEM_NAME,
        "label": JOB_LOOP_SUBSYSTEM_LABEL,
        "status": status,
        "detail": detail,
        "backends": backends,
    }
    return rtnval


__all__ = [
    "JOB_LOOP_SUBSYSTEM_LABEL",
    "JOB_LOOP_SUBSYSTEM_NAME",
    "describe_job_loop_readiness",
]
