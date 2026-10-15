"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_rpa_one_project_key_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A project's RPA specifications and jobs are one set, whichever surface made them (``specs/project-model-bridge.md``).

.. moduleauthor:: Code Craft AI LLC

The web UI stored a project's RPA specifications and jobs under the text of its integer id and the REST surface under the project's UUID, so one project had two disjoint sets: on a real pod the jobs
list on the page said "No RPA jobs yet" while the REST surface listed three. The UI now uses the registry project's UUID, and a migration re-keys the rows it had already made.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import importlib.util
import os
import re
import uuid

from typing import Any, Dict, List, Tuple

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.webservice.orchestration.rpa.models import RpaExecutionMode, RpaJob, RpaJobStatus, RpaSpec
from ccai.pychestrate.webservice.orchestration.rpa.service import (
    RpaJobTypeInputs,
    RpaSpecInputs,
    RpaVersionInputs,
    create_spec,
    publish_version,
    register_job_type,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.projects.legacy_identity import derived_project_uuid

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm
from ccai.tests.singlehost.pychestrate.webservice.phase10 import _projects_ui_helpers as ui


def _text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _make_job_type(type_id: str) -> None:
    session = adm.open_db_session()
    try:
        register_job_type(db_session=session, inputs=RpaJobTypeInputs(type_id=type_id, display_name="Invoice import"), actor_id=None)
        publish_version(
            db_session=session, type_id=type_id,
            inputs=RpaVersionInputs(version="1.0.0", source_kind="package", source_ref="jobs==1", entrypoint={"command": ["job"]}), actor_id=None,
        )
        session.commit()
    finally:
        session.close()


def test_a_specification_and_a_job_are_one_set_on_the_page_and_through_the_service():
    """
    **Feature: one RPA project key (the project bridge)**
    **Property: a specification made on the web UI's form is stored under the registry project's UUID (not the integer's text); a specification made through the service under that UUID (as
    the REST surface does) and a job recorded under it both appear on the project's pages; the page's jobs list and spec list are what the REST surface lists.**
    """
    cookies = adm.admin_cookies()
    legacy_id = ui.create_project_via_ui(wsgi_app=adm.app(), cookies=cookies, prefix="rpakey")
    type_id = "invoice-" + uuid.uuid4().hex[:6]
    _make_job_type(type_id)
    session = adm.open_db_session()
    try:
        registry = projects_repo.get_project_by_legacy_id(db_session=session, legacy_proj_id=legacy_id)
        registry_key = str(registry.project_id)
    finally:
        session.close()

    adm.post_form(path="/projects/{}/rpa/specs/create".format(legacy_id), cookies=cookies, fields={
        "name": "from-ui", "type_id": type_id, "version_selector": "latest-active", "default_packet": "{}", "required_capabilities": "", "target_pod_id": "", "timeout_minutes": "", "description": "",
    })
    session = adm.open_db_session()
    try:
        create_spec(db_session=session, project_id=registry_key, inputs=RpaSpecInputs(name="from-api", type_id=type_id), actor_id=None)
        api_spec = session.query(RpaSpec).filter(RpaSpec.name == "from-api").first()
        session.add(RpaJob(
            job_id=str(uuid.uuid4()), project_id=registry_key, spec_id=api_spec.spec_id, spec_name="from-api", type_id=type_id, resolved_version="1.0.0",
            execution_mode=RpaExecutionMode.PROCESS, status=RpaJobStatus.SUCCEEDED, exit_code=0,
        ))
        session.commit()
        stored = sorted((row.name, row.project_id) for row in session.query(RpaSpec).filter(RpaSpec.project_id.in_([registry_key, str(legacy_id)])).all())
    finally:
        session.close()
    specs_page = _text(adm.get(path="/projects/{}/rpa/specs".format(legacy_id), cookies=cookies).body.decode("utf-8"))
    jobs_page = _text(adm.get(path="/projects/{}/rpa".format(legacy_id), cookies=cookies).body.decode("utf-8"))

    testbase.assert_equal(
        (stored, "from-ui" in specs_page and "from-api" in specs_page, "from-api" in jobs_page, "No RPA jobs yet" in jobs_page),
        ([("from-api", registry_key), ("from-ui", registry_key)], True, True, False),
    )
    return


def _load_migration() -> Any:
    root = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(root, "alembic", "versions")) and root != os.path.dirname(root):
        root = os.path.dirname(root)
    versions = os.path.join(root, "alembic", "versions")
    name = [item for item in os.listdir(versions) if "a3c5e7f9b1d2" in item][0]
    spec = importlib.util.spec_from_file_location("rpa_key_migration", os.path.join(versions, name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(statements: List[Tuple[str, Dict[str, Any]]]) -> Tuple[List[Tuple[str, str]], List[str]]:
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE projects_projects (project_id CHAR(32) NOT NULL PRIMARY KEY, slug VARCHAR(63), legacy_proj_id BIGINT)"))
        connection.execute(sa.text(
            "CREATE TABLE orch_rpa_spec (spec_id CHAR(32) NOT NULL PRIMARY KEY, project_id VARCHAR(64) NOT NULL, name VARCHAR(128) NOT NULL, created_at DATETIME, "
            "CONSTRAINT uq_orch_rpa_spec_name UNIQUE (project_id, name))"
        ))
        connection.execute(sa.text("CREATE TABLE orch_rpa_job (job_id CHAR(32) NOT NULL PRIMARY KEY, project_id VARCHAR(64) NOT NULL, spec_id CHAR(32))"))
        for sql, params in statements:
            connection.execute(sa.text(sql), params)
    migration = _load_migration()
    for _ in range(2):  # a second run changes nothing
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
    with engine.begin() as connection:
        specs = connection.execute(sa.text("SELECT name, project_id FROM orch_rpa_spec ORDER BY project_id, name")).fetchall()
        jobs = connection.execute(sa.text("SELECT project_id FROM orch_rpa_job ORDER BY job_id")).fetchall()
    return [(name, project) for name, project in specs], [row[0] for row in jobs]


def test_the_migration_rekeys_what_the_web_ui_made_and_loses_nothing():
    """
    **Feature: one RPA project key (the project bridge)**
    **Property: rows keyed by an integer id's text move to the UUID of the registry project bridged to it, or to the UUID derived from the integer when no registry row is bridged; a
    specification whose name the registry project already has is kept as "<name> (web UI)" ("... (web UI 2)" if that is taken too); rows already keyed by a UUID, and a second run, change nothing.**
    """
    bridged = str(uuid.uuid4())
    other = str(uuid.uuid4())
    spec = lambda number, project, name: ("INSERT INTO orch_rpa_spec VALUES (:id, :project, :name, '2026-10-01 10:00:0{}')".format(number), {"id": "%032x" % number, "project": project, "name": name})
    statements = [
        ("INSERT INTO projects_projects VALUES (:id, 'one', 1)", {"id": uuid.UUID(bridged).hex}),
        spec(1, bridged, "nightly"),            # made through the REST surface
        spec(2, "1", "nightly"),                # the web UI's, same name: kept, renamed
        spec(3, "1", "nightly (web UI)"),       # a name the rename would use
        spec(4, "1", "weekly"),                 # no clash
        spec(5, "2", "other"),                  # a project with no bridged registry row
        spec(6, other, "untouched"),
        ("INSERT INTO orch_rpa_job VALUES ('%032x', '1', NULL)" % 1, {}),
        ("INSERT INTO orch_rpa_job VALUES ('%032x', '2', NULL)" % 2, {}),
        ("INSERT INTO orch_rpa_job VALUES ('%032x', :other, NULL)" % 3, {"other": other}),
    ]
    specs, jobs = _run_migration(statements)

    unbridged = derived_project_uuid("2")
    testbase.assert_equal(
        (sorted(specs), jobs),
        (
            sorted([
                ("nightly", bridged), ("nightly (web UI)", bridged), ("nightly (web UI) (web UI)", bridged), ("weekly", bridged),
                ("other", unbridged), ("untouched", other),
            ]),
            [bridged, unbridged, other],
        ),
    )
    return
