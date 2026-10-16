"""
.. module:: test_p32c_pod_job_contract_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: What the service sends a pod is what the contract says (E2E-14).

.. moduleauthor:: Code Craft AI LLC

A valid REST test run was refused by the pod ("needs params.test_root") because
the service sent ``root``, and the pod's progress tag ("testbase") differed from
the service's ("testbase-v1"). The pod side was fixed; nothing kept the two
sides in step. ``specs/contracts/pod-job-contract.json`` records the ``params``
the test runner produces for given catalog metadata and trigger inputs, and the
progress format tag. These tests check the service against it; the
``pychestrate-client`` repository holds an identical copy and checks the pod
against it (``test_service_contract.py``). When the client checkout sits next to
this one, a test also checks the two copies are identical.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from typing import Any, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.ingest.progress.factories.testbase_v1 import (
    TESTBASE_V1_FORMAT_TAG,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import (
    TestCatalogEntrySnapshot,
)
from ccai.pychestrate.webservice.jobs.envelope import canonical as envelope_canonical
from ccai.pychestrate.webservice.jobs.envelope.schema import JobSourceRef
from ccai.pychestrate.webservice.orchestration.build.service import BuildRunInputs, build_params_for
from ccai.pychestrate.webservice.orchestration.test.factories.testbase_runner import (
    TestbaseRunnerKind,
)


CLIENT_COPY = os.path.join(
    "source", "testroots", "ccai", "tests", "pychestrate", "client", "contracts", "pod-job-contract.json",
)


def _repo_root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "specs")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return current


def _contract() -> Dict[str, Any]:
    with open(os.path.join(_repo_root(), "specs", "contracts", "pod-job-contract.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _client_copy() -> Optional[Dict[str, Any]]:
    path = os.path.join(os.path.dirname(_repo_root()), "pychestrate-client", CLIENT_COPY)
    if os.path.isfile(path) is False:
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def test_the_test_runner_produces_exactly_the_params_the_contract_records():
    """
    **Feature: one contract for both sides (E2E-14)**
    **Property: for each case in the contract, the testbase runner turns the
    catalog entry's metadata and the trigger's inputs into the recorded params
    (``root``, ``includes``, ``extras`` and ``runner``), so a renamed key fails here
    until the contract, and with it the pod, is changed on purpose.**
    """
    contract = _contract()
    produced: Dict[str, Any] = {}
    for case in contract["test_run_envelope_params"]:
        snapshot = TestCatalogEntrySnapshot(
            entry_id="ent-1", canonical_digest="d" * 64, required_capability_tags=(), param_schema={},
            runner_kind="testbase", raw_metadata=case["catalog_entry_metadata"],
        )
        produced[case["name"]] = TestbaseRunnerKind.build_envelope_params(snapshot=snapshot, inputs=case["trigger_inputs"])

    testbase.assert_equal(
        (len(contract["test_run_envelope_params"]) >= 2, produced),
        (True, {case["name"]: case["params"] for case in contract["test_run_envelope_params"]}),
    )
    return


def test_the_build_trigger_produces_exactly_the_params_and_source_block_the_contract_records():
    """
    **Feature: one contract for both sides (E2E-14)**
    **Property: for each build case in the contract, the params a build trigger puts in the envelope (runner kind, ``runner_inputs`` with the make ``targets``, the environment, and a
    ``git_url``, ``git_ref`` or ``source_dir`` the inputs name) and the envelope's ``source`` block for a source integration (kind, url, ref, integration id, and a credentials
    *reference*, never a credential) are the recorded ones, so a renamed key fails here until the contract, and with it the pod, is changed on purpose.**
    """
    contract = _contract()
    digest = contract["build_envelope_digest"]
    produced: Dict[str, Any] = {}
    for case in contract["build_envelope_params"]:
        trigger = case["trigger"]
        params = build_params_for(inputs=BuildRunInputs(runner_kind=trigger["runner_kind"], runner_inputs=trigger["runner_inputs"], env=trigger["env"]), digest=digest)
        source = JobSourceRef(**case["source_ref"]) if case["source_ref"] is not None else None
        produced[case["name"]] = {"params": params, "envelope_source": envelope_canonical._source_to_dict(source=source)}

    testbase.assert_equal(
        (len(contract["build_envelope_params"]) >= 5, produced),
        (True, {case["name"]: {"params": case["params"], "envelope_source": case["envelope_source"]} for case in contract["build_envelope_params"]}),
    )
    return


def test_the_progress_parser_is_registered_under_the_contracts_tag():
    """
    **Feature: one contract for both sides (E2E-14)**
    **Property: the service's progress parser tag equals the contract's (the
    tag the pod sends).**
    """
    testbase.assert_equal(TESTBASE_V1_FORMAT_TAG, _contract()["progress_format_tag"])
    return


def test_the_client_checkouts_copy_of_the_contract_is_the_same_file():
    """
    **Feature: one contract for both sides (E2E-14)**
    **Property: when the pychestrate-client checkout sits next to this one, its
    copy of the contract has the same content as this repository's, so the two
    repositories' tests are checking the same thing. Without the checkout there is
    nothing to compare and the test passes.**
    """
    copy = _client_copy()

    testbase.assert_equal(copy is None or copy == _contract(), True)
    return
