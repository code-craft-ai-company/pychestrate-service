"""
.. module:: test_p10u_pods_clients_problem_json_refit_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Source-level smoke checks for the second controller refit batch.

.. moduleauthor:: Automation Mojo LLC

Flask is not installed in the test venv (long-standing), so the
controllers cannot be imported end-to-end here. The smoke checks
read the source files and assert:

* Every legacy ``<noun>_ns.abort(`` call site has been replaced.
* The ``abort_with_problem`` helper from
  :mod:`webservice.api.problem_json_flask` is now imported.
* At least one ``abort_with_problem`` call site exists in each
  refitted file.

End-to-end validation of the wire body shape lives in
:mod:`test_p10s_problem_json_flask_m1` (which exercises the
helper through the same stub-flask seam) — repeating those
assertions per controller would be noise.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from automojo import testbase


def _read_controller_source(*, relative_path: str) -> str:
    """
        Resolve a controller path relative to the repo's ``source/site``
        root and return the file contents.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    repo_source_site_root = os.path.normpath(
        os.path.join(here, "..", "..", "..", "..", "..", "..", "..", "..", "source", "site")
    )
    full = os.path.join(repo_source_site_root, relative_path)
    with open(full, "r", encoding="utf-8") as fh:
        rtnval = fh.read()
    return rtnval


# ---------------------------------------------------------------------------
# pods_controller.py
# ---------------------------------------------------------------------------

def test_pods_controller_has_zero_legacy_abort_sites():
    """
    **Feature: 8-rest-api-v1 T1.4 (pods refit)**
    **Property: pods_controller.py carries zero ``pods_ns.abort(``
    legacy call sites.**
    """
    text = _read_controller_source(
        relative_path=os.path.join(
            "automojo", "pychestrate", "webservice", "pods",
            "restapi", "v1", "pods_controller.py",
        )
    )
    testbase.assert_equal("pods_ns.abort(" in text, False)
    return


def test_pods_controller_imports_abort_with_problem():
    text = _read_controller_source(
        relative_path=os.path.join(
            "automojo", "pychestrate", "webservice", "pods",
            "restapi", "v1", "pods_controller.py",
        )
    )
    testbase.assert_equal(
        "from automojo.pychestrate.webservice.api.problem_json_flask import abort_with_problem"
        in text,
        True,
    )
    return


def test_pods_controller_has_at_least_one_abort_with_problem_site():
    text = _read_controller_source(
        relative_path=os.path.join(
            "automojo", "pychestrate", "webservice", "pods",
            "restapi", "v1", "pods_controller.py",
        )
    )
    occurrences = text.count("abort_with_problem(")
    testbase.assert_equal(occurrences > 0, True)
    return


# ---------------------------------------------------------------------------
# clients_controller.py
# ---------------------------------------------------------------------------

def test_clients_controller_has_zero_legacy_abort_sites():
    """
    **Feature: 8-rest-api-v1 T1.4 (clients refit)**
    **Property: clients_controller.py carries zero
    ``clients_ns.abort(`` legacy call sites.**
    """
    text = _read_controller_source(
        relative_path=os.path.join(
            "automojo", "pychestrate", "webservice", "clients",
            "restapi", "v1", "clients_controller.py",
        )
    )
    testbase.assert_equal("clients_ns.abort(" in text, False)
    return


def test_clients_controller_imports_abort_with_problem():
    text = _read_controller_source(
        relative_path=os.path.join(
            "automojo", "pychestrate", "webservice", "clients",
            "restapi", "v1", "clients_controller.py",
        )
    )
    testbase.assert_equal(
        "from automojo.pychestrate.webservice.api.problem_json_flask import abort_with_problem"
        in text,
        True,
    )
    return


def test_clients_controller_has_at_least_one_abort_with_problem_site():
    text = _read_controller_source(
        relative_path=os.path.join(
            "automojo", "pychestrate", "webservice", "clients",
            "restapi", "v1", "clients_controller.py",
        )
    )
    occurrences = text.count("abort_with_problem(")
    testbase.assert_equal(occurrences > 0, True)
    return


# ---------------------------------------------------------------------------
# Cross-cutting: prior-batch controllers stay refitted (regression guard)
# ---------------------------------------------------------------------------

def test_prior_batch_controllers_still_carry_zero_legacy_aborts():
    """
    **Feature: 8-rest-api-v1 T1.4 (regression guard)**
    **Property: The earlier p10s batch (flags / users / audit) does
    not regress when this PR lands — none of those files should grow
    a fresh ``<noun>_ns.abort(`` call.**
    """
    paths = [
        ("automojo/pychestrate/webservice/identity/flags/restapi/v1/flags_controller.py", "flags_ns.abort("),
        ("automojo/pychestrate/webservice/identity/users/restapi/v1/users_controller.py", "users_ns.abort("),
        ("automojo/pychestrate/webservice/audit/restapi/v1/audit_controller.py", "audit_ns.abort("),
    ]
    for relative_path, legacy_pattern in paths:
        text = _read_controller_source(relative_path=relative_path)
        testbase.assert_equal(legacy_pattern in text, False)
    return
