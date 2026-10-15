"""
.. module:: test_variables_one_store_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The Admin Variables pages and the runtime read and write one store (audit ADM-08, ``specs/model-convergence.md`` section 8).

.. moduleauthor:: Code Craft AI LLC

The pages wrote the legacy ``global_variables`` table, which nothing in the runtime reads, so a variable created there did nothing and one set through the API never
appeared there. They now manage the SYSTEM-scope bindings the runtime resolves, with their description, default and history in the same store, and the migration copies
what the legacy table held.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import importlib.util
import json
import os
import re
import uuid

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.core.orm import GlobalVariable, GlobalVariableHistory, PychestrateModelBase
from ccai.pychestrate.webservice.variables import service as variable_service
from ccai.pychestrate.webservice.variables.restapi.v1 import variables_routes
from ccai.pychestrate.webservice.variables.models import VariableBinding, VariableBindingHistory, VariableScope, VariableValueType
from ccai.pychestrate.webservice.variables.system_store import SystemVariableStore

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import ensure_seeded_admin


def _name(prefix: str) -> str:
    return "{}.{}".format(prefix, uuid.uuid4().hex[:8])


def _resolve(name: str) -> Any:
    session = adm.open_db_session()
    try:
        return variable_service.resolve_effective(
            db_session=session, name=name, project_id=None, pipeline_id=None, job_id=None, dereference_secrets=False,
        )
    finally:
        session.close()


def _text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_a_variable_created_on_the_page_is_the_one_the_runtime_resolves():
    """
    **Feature: one variables store (ADM-08)**
    **Property: a variable created on Admin, Variables resolves through the effective-value service the runtime and ``/api/v1/variables/effective`` use, with the typed
    value (an integer is an integer, JSON is JSON); it is a SYSTEM binding with its description and default; changing it on the page changes what resolves, and deleting
    it makes it unresolved.**
    """
    cookies = adm.admin_cookies()
    count, flag, doc = _name("ui.page.count"), _name("ui.page.flag"), _name("ui.page.doc")
    for name, var_type, value, default, description in (
        (count, "integer", "42", "7", "How many"), (flag, "boolean", "true", "", ""), (doc, "json", '{"b": 2, "a": [1]}', "", "A document"),
    ):
        adm.post_form(path="/admin/variables/create", cookies=cookies, fields={
            "name": name, "var_type": var_type, "value": value, "default_value": default, "description": description,
        })
    first = (_resolve(count), _resolve(flag), _resolve(doc))
    adm.post_form(path="/admin/variables/{}/edit".format(count), cookies=cookies, fields={"value": "43", "description": "How many, now"})
    changed = _resolve(count)
    session = adm.open_db_session()
    try:
        row = session.query(VariableBinding).filter(VariableBinding.name == count).first()
        stored = (row.scope.value, row.scope_id, row.value_type.value, row.value_text, row.description, row.default_value_text, row.created_at is not None)
    finally:
        session.close()
    adm.post_form(path="/admin/variables/{}/delete".format(count), cookies=cookies, fields={})
    gone = _resolve(count)

    testbase.assert_equal(
        (first, changed, stored, gone),
        ((42, True, {"a": [1], "b": 2}), 43, ("SYSTEM", "", "INTEGER", "43", "How many, now", "7", True), None),
    )
    return


def test_a_variable_set_through_the_api_service_appears_on_the_page_with_its_history():
    """
    **Feature: one variables store (ADM-08)**
    **Property: a SYSTEM variable set through the variables service (what ``PUT /api/v1/variables/system//<name>`` does) is listed on the page with its value, and its
    History shows each change with the old and the new value and who made it, including the removal, whichever way it was made (service or page).**
    """
    cookies = adm.admin_cookies()
    admin = ensure_seeded_admin().user_id
    name = _name("ui.api.limit")
    session = adm.open_db_session()
    try:
        for value in (10, 20):
            variable_service.set_variable(
                db_session=session, scope=VariableScope.SYSTEM, scope_id="", name=name, value=value, value_type=VariableValueType.INTEGER, actor_user_id=admin,
            )
    finally:
        session.close()
    adm.post_form(path="/admin/variables/{}/edit".format(name), cookies=cookies, fields={"value": "30", "description": ""})
    listing = _text(adm.get(path="/admin/variables", cookies=cookies, query={"search": name}).text)
    detail = _text(adm.get(path="/admin/variables/{}".format(name), cookies=cookies).text)
    adm.post_form(path="/admin/variables/{}/delete".format(name), cookies=cookies, fields={})
    history = _text(adm.get(path="/admin/variables/{}/history".format(name), cookies=cookies).text)

    session = adm.open_db_session()
    try:
        rows = session.query(VariableBindingHistory).filter(VariableBindingHistory.name == name).order_by(VariableBindingHistory.changed_at).all()
        changes = [(row.old_value_text, row.new_value_text, str(row.changed_by_user_id).replace("-", "") == admin.replace("-", "")) for row in rows]
    finally:
        session.close()

    testbase.assert_equal(
        (name in listing, "30" in detail, changes),
        (True, True, [(None, "10", True), ("10", "20", True), ("20", "30", True), ("30", None, True)]),
    )
    testbase.assert_equal(history.count(name) >= 1, True)
    return


def test_a_secret_reference_variable_set_through_the_api_is_listed_and_keeps_its_type_when_edited():
    """
    **Feature: one variables store (ADM-08)**
    **Property: a SECRET_REF variable (the API has it, the page never offered it) is listed as text and keeps its type when its value is changed on the page.**
    """
    cookies = adm.admin_cookies()
    name = _name("ui.api.secretref")
    session = adm.open_db_session()
    try:
        variable_service.set_variable(
            db_session=session, scope=VariableScope.SYSTEM, scope_id="", name=name, value="secret://one", value_type=VariableValueType.SECRET_REF, actor_user_id=None,
        )
    finally:
        session.close()
    listed = name in adm.get(path="/admin/variables", cookies=cookies, query={"search": name}).text
    adm.post_form(path="/admin/variables/{}/edit".format(name), cookies=cookies, fields={"value": "secret://two", "description": ""})
    session = adm.open_db_session()
    try:
        row = session.query(VariableBinding).filter(VariableBinding.name == name).first()
        kept = (row.value_type.value, row.value_text)
    finally:
        session.close()

    testbase.assert_equal((listed, kept), (True, ("SECRET_REF", "secret://two")))
    return


def _load_migration() -> Any:
    root = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(root, "alembic", "versions")) and root != os.path.dirname(root):
        root = os.path.dirname(root)
    versions = os.path.join(root, "alembic", "versions")
    name = [item for item in os.listdir(versions) if "f7b2c9a4d1e6" in item][0]
    spec = importlib.util.spec_from_file_location("variables_migration", os.path.join(versions, name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migrate(*, with_existing_binding: str = "") -> Tuple[Dict[str, Any], List[Tuple[str, str, str]]]:
    """Run the migration on a database as it was before it: the old bindings table and the legacy variables with some history."""
    engine = sa.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    PychestrateModelBase.metadata.create_all(engine, tables=[GlobalVariable.__table__, GlobalVariableHistory.__table__])
    with engine.begin() as connection:
        connection.execute(sa.text(
            "CREATE TABLE variables_variable_bindings (binding_id CHAR(32) NOT NULL PRIMARY KEY, scope VARCHAR(8) NOT NULL, scope_id VARCHAR(64) NOT NULL, "
            "name VARCHAR(128) NOT NULL, value_type VARCHAR(10) NOT NULL, value_text TEXT, set_by_user_id CHAR(32), set_at DATETIME NOT NULL, "
            "CONSTRAINT uq_variables_scope_name UNIQUE (scope, scope_id, name))"
        ))
        connection.execute(sa.text(
            "INSERT INTO variables_variable_bindings VALUES ('a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1', 'SYSTEM', '', 'already.there', 'STRING', 'api-set', NULL, '2026-09-01 10:00:00')"
        ))
    maker = sessionmaker(bind=engine)
    session = maker()
    user = uuid.uuid4()
    made = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    later = datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc)
    session.add_all([
        GlobalVariable(id=1, name="legacy.count", value_json="12", var_type="integer", description="How many", default_value_json="5", created_at=made, updated_at=later, updated_by_id=user),
        GlobalVariable(id=2, name="legacy.text", value_json='"hello"', var_type="string", description="", default_value_json=None, created_at=made, updated_at=made),
        GlobalVariable(id=3, name="legacy.doc", value_json='{"b":1,"a":[2]}', var_type="json", description="Doc", default_value_json=None, created_at=made, updated_at=made),
        GlobalVariable(id=4, name="legacy.flag", value_json="true", var_type="boolean", description="", default_value_json=None, created_at=made, updated_at=made),
        GlobalVariable(id=5, name="already.there", value_json='"legacy-value"', var_type="string", description="old", default_value_json=None, created_at=made, updated_at=made),
    ])
    session.add_all([
        GlobalVariableHistory(variable_id=1, variable_name="legacy.count", old_value_json=None, new_value_json="10", changed_by_id=user, changed_at=made),
        GlobalVariableHistory(variable_id=1, variable_name="legacy.count", old_value_json="10", new_value_json="12", changed_by_id=user, changed_at=later),
        GlobalVariableHistory(variable_id=99, variable_name="legacy.gone", old_value_json='"x"', new_value_json=None, changed_by_id=None, changed_at=later),
        GlobalVariableHistory(variable_id=5, variable_name="already.there", old_value_json=None, new_value_json='"legacy-value"', changed_by_id=None, changed_at=made),
    ])
    session.commit()
    session.close()

    migration = _load_migration()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
    with engine.connect() as connection:
        columns = [column["name"] for column in sa.inspect(connection).get_columns("variables_variable_bindings")]
        rows = {
            row["name"]: dict(row) for row in connection.execute(sa.text(
                "SELECT name, value_type, value_text, description, default_value_text, created_at, set_at, set_by_user_id FROM variables_variable_bindings ORDER BY name"
            )).mappings().all()
        }
        history = [(row[0], row[1], row[2]) for row in connection.execute(sa.text(
            "SELECT name, old_value_text, new_value_text FROM variables_binding_history ORDER BY changed_at, name"
        )).fetchall()]
    rows["_columns"] = columns
    return rows, history


def test_the_migration_copies_the_legacy_variables_and_their_history_and_leaves_a_variable_the_api_already_set():
    """
    **Feature: one variables store (ADM-08)**
    **Property: the migration adds the new columns and the history table, copies each legacy variable (value as the modern store's text, type, description, default,
    created and changed times, who) and its history, copies the history of a variable that no longer exists, and neither copies a legacy variable whose name the modern
    store already has a SYSTEM binding for nor its history.**
    """
    rows, history = _migrate()

    testbase.assert_equal(
        (
            sorted(set(rows["_columns"]) & {"description", "default_value_text", "created_at"}),
            [(rows[n]["value_type"], rows[n]["value_text"], rows[n]["description"], rows[n]["default_value_text"]) for n in ("legacy.count", "legacy.text", "legacy.doc", "legacy.flag")],
            rows["already.there"]["value_text"], rows["already.there"]["created_at"] is not None,
            str(rows["legacy.count"]["created_at"])[:10], str(rows["legacy.count"]["set_at"])[:10], rows["legacy.count"]["set_by_user_id"] is not None,
            history,
        ),
        (
            ["created_at", "default_value_text", "description"],
            [("INTEGER", "12", "How many", "5"), ("STRING", "hello", "", None), ("JSON", '{"a": [2], "b": 1}', "Doc", None), ("BOOLEAN", "true", "", None)],
            "api-set", True, "2026-08-01", "2026-08-02", True,
            [(("legacy.count"), None, "10"), ("legacy.count", "10", "12"), ("legacy.gone", '"x"', None)],
        ),
    )
    return


def _put(name: str, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    session = adm.open_db_session()
    try:
        request = SimpleNamespace(
            path="/api/v1/variables/system//{}".format(name), path_params={"scope": "system", "scope_id": "", "name": name}, db_session=session,
            actor_user_id=ensure_seeded_admin().user_id, query_params={}, json=lambda: body,
        )
        response = variables_routes.handle_set_variable(request)
    finally:
        session.close()
    return response.status_code, json.loads(response.body.decode("utf-8"))


def test_the_api_can_describe_a_variable_and_the_description_is_kept_and_shown_on_the_page():
    """
    **Feature: one variables store (ADM-08)**
    **Property: PUT with a description stores and returns it and the Admin page lists it; a later PUT without one keeps it, one with an empty string clears it, and a
    description that is not text or is over 512 characters is a 400.**
    """
    cookies = adm.admin_cookies()
    name = _name("ui.api.described")
    first = _put(name, {"value_type": "string", "value": "a", "description": "Retention in days"})
    page = _text(adm.get(path="/admin/variables", cookies=cookies, query={"search": "Retention in days"}).text)
    second = _put(name, {"value_type": "string", "value": "b"})
    cleared = _put(name, {"value_type": "string", "value": "c", "description": ""})
    bad_type = _put(name, {"value_type": "string", "value": "d", "description": 5})
    too_long = _put(name, {"value_type": "string", "value": "e", "description": "x" * 513})

    testbase.assert_equal(
        (first[0], first[1]["description"], name in page, second[1]["description"], cleared[1]["description"], bad_type[0], too_long[0]),
        (200, "Retention in days", True, "Retention in days", "", 400, 400),
    )
    return
