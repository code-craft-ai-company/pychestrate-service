"""
.. module:: test_p32x_form_examples_are_valid_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: What a form shows as its example is something the service accepts (ORC-17).

.. moduleauthor:: Code Craft AI LLC

Two bundle forms offered examples the service refused: the release form asked for a free-text
component and showed ``agent-runtime`` (the API accepts ``service`` and ``agent``), and the pipeline form's
example document had ``stages: []``. The release form now offers exactly the API's components, and the
pipeline example is a document the service loads. Both are read out of the shipped bundle source and checked
against the service itself, so an example cannot drift into being wrong again.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import re

from typing import List

from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.messaging.event_bus import reset_for_testing as reset_event_bus
from ccai.pychestrate.webservice.ops.release.models import ReleaseChannel, ReleaseComponent
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    PipelineDocumentInvalidError,
    load_from_source,
    register_builtin_extensions,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


JS_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir, os.pardir,
    "site", "ccai", "pychestrate", "webservice", "webinterface", "static", "javascript",
)

PROJECT = "00000000-0000-4000-8000-0000000000d1"


def _source(bundle: str, name: str) -> str:
    return open(os.path.join(JS_ROOT, bundle, name), encoding="utf-8").read()


def _js_list(source: str, constant: str) -> List[str]:
    match = re.search(r"const " + constant + r" = \[(.*?)\];", source, re.S)
    testbase.assert_true(match is not None, constant + " not found")
    return re.findall(r'"([^"]+)"', match.group(1))


def _component_values(source: str) -> List[str]:
    """The API values in RELEASE_COMPONENTS (each is ``{ value: "...", label: "..." }``)."""
    match = re.search(r"const RELEASE_COMPONENTS = \[(.*?)\];", source, re.S)
    testbase.assert_true(match is not None, "RELEASE_COMPONENTS not found")
    return re.findall(r'value:\s*"([^"]+)"', match.group(1))


def _load(document: str) -> None:
    reset_registry_for_testing()
    reset_event_bus()
    register_builtin_extensions()
    _engine, session = build_in_memory_session()
    load_from_source(db_session=session, project_id=PROJECT, commit_sha="a" * 40, filename="pipeline.yaml", document_bytes=document.encode("utf-8"))
    return


def test_the_release_form_offers_exactly_the_components_the_api_accepts():
    """
    **Feature: form examples are valid (ORC-17)**
    **Property: the components the publish form offers are the API's ``ReleaseComponent`` values and
    its channels are the ``ReleaseChannel`` values, in order; ``agent-runtime`` is not offered or shown.**
    """
    source = _source("pyc-ops-bundle", "release-channels-view.js")

    testbase.assert_equal(
        (
            _component_values(source), _js_list(source, "RELEASE_CHANNEL_VALUES"), "agent-runtime" in source,
        ),
        ([member.value for member in ReleaseComponent], [member.value for member in ReleaseChannel], False),
    )
    return


def test_the_pipeline_form_example_is_a_document_the_service_accepts():
    """
    **Feature: form examples are valid (ORC-17)**
    **Property: the example document the Define a pipeline form shows loads without error; the one it
    showed before (an empty ``stages`` list) is refused, which is why it was changed.**
    """
    source = _source("pyc-pipelines-bundle", "pipelines-list-view.js")
    match = re.search(r'"placeholder",\s*(?://[^\n]*\n\s*)?("name: example[^\n]*")\s*\)', source)
    testbase.assert_true(match is not None, "placeholder not found")
    example = json.loads(match.group(1))
    _load(example)

    refused = False
    try:
        _load("name: example\nschema_version: 1\nstages: []")
    except PipelineDocumentInvalidError:
        refused = True

    testbase.assert_equal((example.startswith("name: example\nschema_version: 1\nstages:\n  - id: build"), refused), (True, True))
    return
