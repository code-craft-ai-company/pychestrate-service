"""
.. module:: test_p26d_launcher_job_loop_provisioning_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The documented launchers provision everything the job
               loop needs (LD-02).

.. moduleauthor:: Code Craft AI LLC

``development/dev-up`` staged no envelope signing key (every dispatch
failed) and ``development/run-staging-gunicorn`` staged no enrollment
CA (every pod enrollment answered 503); neither staged the presign
secret a multi-worker deploy needs. These tests read the launcher
scripts (they are never run here) and check each one generates and
exports every job-loop prerequisite, and that the alpha deploy points
nginx at the CA the service signs pod certificates with.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from typing import List

from ccai import testbase


_JOB_LOOP_EXPORTS = (
    "PYCHESTRATE_ENVELOPE_SIGNING_KEY_SOURCE",
    "PYCHESTRATE_ENVELOPE_SIGNING_KEY_ID",
    "PYCHESTRATE_ENVELOPE_SIGNING_KEY_FILE_PATH",
    "PYCHESTRATE_ENROLLMENT_CA_SOURCE",
    "PYCHESTRATE_ENROLLMENT_CA_FILE_PATH",
    "PYCHESTRATE_ENROLLMENT_CA_ID",
    "PYCHESTRATE_RESULT_PRESIGN_SECRET",
)


def _repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    rtnval = os.path.normpath(os.path.join(here, "..", "..", "..", "..", "..", "..", "..", ".."))
    return rtnval


def _read(relative_path: str) -> str:
    with open(os.path.join(_repo_root(), relative_path), "r", encoding="utf-8") as handle:
        rtnval = handle.read()
    return rtnval


def _missing_exports(script: str) -> List[str]:
    text = _read(script)
    rtnval = [name for name in _JOB_LOOP_EXPORTS if re.search(r"^export {}=".format(name), text, re.M) is None]
    return rtnval


def test_dev_up_exports_every_job_loop_prerequisite():
    """
    **Feature: launchers provision the job loop (LD-02)**
    **Property: development/dev-up exports the envelope signing key, the
    enrollment CA and the presign secret variables.**
    """
    testbase.assert_equal(_missing_exports("development/dev-up"), [])
    return


def test_staging_launcher_exports_every_job_loop_prerequisite():
    """
    **Feature: launchers provision the job loop (LD-02)**
    **Property: development/run-staging-gunicorn exports the envelope
    signing key, the enrollment CA and the presign secret variables.**
    """
    testbase.assert_equal(_missing_exports("development/run-staging-gunicorn"), [])
    return


def test_launchers_generate_the_enrollment_ca_certificate_for_nginx():
    """
    **Feature: launchers provision the job loop (LD-02)**
    **Property: both launchers write the enrollment CA's certificate on
    its own (dev.enrollment-ca.crt) for a TLS terminator to trust.**
    """
    found = ["dev.enrollment-ca.crt" in _read(script)
             for script in ("development/dev-up", "development/run-staging-gunicorn")]
    testbase.assert_equal(found, [True, True])
    return


def test_staging_launcher_supports_provision_only():
    """
    **Feature: launchers provision the job loop (LD-02)**
    **Property: run-staging-gunicorn accepts --provision-only, which
    exits after generating secrets and before exec'ing gunicorn.**
    """
    text = _read("development/run-staging-gunicorn")
    provision_exit = text.find('if [[ "${PROVISION_ONLY}" == "true" ]]; then')
    gunicorn_exec = text.find('exec "${GUNICORN}"')
    testbase.assert_equal(
        ("--provision-only)" in text, 0 <= provision_exit < gunicorn_exec),
        (True, True),
    )
    return


def test_alpha_deploy_points_nginx_at_the_enrollment_ca_certificate():
    """
    **Feature: nginx trusts the enrollment CA (E2E-04)**
    **Property: the alpha deploy's default ssl_client_certificate is the
    enrollment CA certificate the staging launcher writes, and the deploy
    provisions it before configuring nginx.**
    """
    text = _read("deployment/deploy-alpha-to-host.sh")
    testbase.assert_equal(
        (".cache/dev-secrets/dev.enrollment-ca.crt" in text,
         "development/run-staging-gunicorn --provision-only" in text),
        (True, True),
    )
    return


def test_alpha_deploy_forwards_hyphenated_certificate_headers_only():
    """
    **Feature: pod certificate identity through nginx (E2E-03)**
    **Property: the rendered nginx config forwards X-Client-Cert-CN and
    X-Client-Cert-Verify in both proxy locations and no longer uses the
    underscore header names gunicorn drops.**
    """
    text = _read("deployment/deploy-alpha-to-host.sh")
    testbase.assert_equal(
        (text.count("proxy_set_header X-Client-Cert-CN"), text.count("proxy_set_header X-Client-Cert-Verify"),
         "proxy_set_header SSL_CLIENT_S_DN_CN" in text),
        (2, 2, False),
    )
    return
