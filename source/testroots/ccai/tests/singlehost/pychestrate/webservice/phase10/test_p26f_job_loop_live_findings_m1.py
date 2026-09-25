"""
.. module:: test_p26f_job_loop_live_findings_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression tests for defects a live pod-to-service job
               run against the alpha host turned up.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any

from ccai import testbase

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import (
    TestCatalogEntrySnapshot,
)
from ccai.pychestrate.webservice.orchestration.test.factories.testbase_runner import (
    TestbaseRunnerKind,
)
from ccai.pychestrate.webservice.wsgi_dispatch import build_wsgi_compat_dispatch


def _snapshot(*, raw_metadata: Any) -> TestCatalogEntrySnapshot:
    rtnval = TestCatalogEntrySnapshot(
        entry_id="ent-1",
        canonical_digest="d" * 64,
        required_capability_tags=(),
        param_schema={},
        runner_kind="testbase",
        raw_metadata=raw_metadata,
    )
    return rtnval


def test_trigger_without_includes_uses_the_catalog_entry_includes():
    """
    **Feature: test-run trigger (live E2E finding)**
    **Property: a trigger that names no includes runs the ones the
    catalog entry was imported with, as root already does.**
    """
    snapshot = _snapshot(raw_metadata={"includes": ["ccai.tests.a"], "root": "/srv/tests"})

    params = TestbaseRunnerKind.build_envelope_params(snapshot=snapshot, inputs={})

    testbase.assert_equal(params["includes"], ["ccai.tests.a"])
    testbase.assert_equal(params["root"], "/srv/tests")
    return


def test_trigger_includes_override_the_catalog_entry():
    """
    **Feature: test-run trigger**
    **Property: includes given in the trigger win over the entry's.**
    """
    snapshot = _snapshot(raw_metadata={"includes": ["ccai.tests.a"]})

    params = TestbaseRunnerKind.build_envelope_params(
        snapshot=snapshot, inputs={"includes": ["ccai.tests.b"]})

    testbase.assert_equal(params["includes"], ["ccai.tests.b"])
    return


def test_trigger_with_no_includes_anywhere_is_rejected():
    """
    **Feature: test-run trigger**
    **Property: with includes in neither the trigger nor the entry, the
    runner rejects the inputs.**
    """
    raised = None
    try:
        TestbaseRunnerKind.validate_inputs(snapshot=_snapshot(raw_metadata={}), inputs={})
    except SemanticError as xcpt:
        raised = xcpt

    testbase.assert_true(raised is not None)
    return


class _RaisingDispatcher:
    def dispatch(self, request: Any) -> Any:
        raise SemanticError("escaped the route")


class _FakeApp:
    dispatcher = _RaisingDispatcher()


class _Request:
    method = "POST"
    path = "/api/v1/projects/p/test-runs"


def test_unhandled_exception_answers_500_instead_of_hanging():
    """
    **Feature: WSGI dispatch (live E2E finding)**
    **Property: an exception that escapes the webworks dispatcher is
    answered with a problem+json 500; it used to reach the WSGI server,
    which never answered, and the client waited out its timeout.**
    """
    handler = build_wsgi_compat_dispatch(app=_FakeApp())
    response = handler(_Request())

    testbase.assert_equal(response.status_code, 500)
    return
