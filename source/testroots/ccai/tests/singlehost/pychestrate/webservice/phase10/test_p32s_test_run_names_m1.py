"""
.. module:: test_p32s_test_run_names_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A test run is listed under its test's name, not a UUID (ORC-11).

.. moduleauthor:: Code Craft AI LLC

The dispatch envelope named a test run after its catalog entry's *id* (the orchestrator
read the display name from ``raw_metadata``, where it is not), so every test run in the
Runs list was a UUID. New runs are now dispatched under the entry's display name, and the
runs API names an older run (whose envelope holds the id) from the catalog when it can.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from ccai import testbase

from ccai.pychestrate.webservice.orchestration.test.catalog import catalog as test_catalog
from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import ImporterEntryPayload
from ccai.pychestrate.webservice.runs.restapi.v1 import runs_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


PROJECT = "00000000-0000-4000-8000-0000000000c1"


def _entry(session: object, *, key: str, display_name: str) -> str:
    view = test_catalog.upsert_entry(
        db_session=session, project_id=PROJECT, importer_tag="testbase-project",
        payload=ImporterEntryPayload(
            entry_key=key, display_name=display_name, description="", required_capability_tags=(),
            param_schema={}, raw_metadata={"runner_kind": "testbase"},
        ),
    )
    return str(view.entry_id)


def test_a_run_named_by_its_catalog_id_is_named_from_the_catalog():
    """
    **Feature: run names (ORC-11)**
    **Property: an envelope name that is the entry's id (or no name) becomes the entry's display
    name; a name the envelope really carries is kept; an id that is no catalog entry, an entry with
    no display name, a job id that is not a UUID (a build id) and no job id at all leave the name as
    it was.**
    """
    _engine, session = build_in_memory_session()
    named = _entry(session, key="named", display_name="Nightly regression")
    nameless = _entry(session, key="nameless", display_name="")
    unknown = str(uuid.uuid4())

    def _name(job_id, job_name):
        return runs_routes._readable_job_name(db_session=session, job_id=job_id, job_name=job_name)

    testbase.assert_equal(
        (
            _name(named, named), _name(named, None), _name(named, "Custom name"),
            _name(unknown, unknown), _name(nameless, nameless), _name("17", "17"), _name(None, None),
        ),
        ("Nightly regression", "Nightly regression", "Custom name", unknown, nameless, "17", None),
    )
    return
