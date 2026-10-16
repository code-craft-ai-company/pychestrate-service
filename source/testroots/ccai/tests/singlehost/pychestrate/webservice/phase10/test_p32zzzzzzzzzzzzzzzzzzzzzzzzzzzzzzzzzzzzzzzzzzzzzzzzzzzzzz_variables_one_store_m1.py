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
import time
import uuid

from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.pool import StaticPool

from ccai import testbase

from ccai.pychestrate.core.orm import PychestrateModelBase, VariableType
from ccai.pychestrate.webservice.variables import cache as variable_cache
from ccai.pychestrate.webservice.variables import service as variable_service
from ccai.pychestrate.webservice.variables.restapi.v1 import variables_routes
from ccai.pychestrate.webservice.variables.models import VariableBinding, VariableBindingHistory, VariableScope, VariableValueType
from ccai.pychestrate.webservice.variables.system_store import SystemVariableCreateRequest, SystemVariableStore

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


def test_get_value_gives_the_default_for_a_variable_that_is_not_set_and_the_typed_value_for_one_that_is():
    """
    **Feature: one variables store (ADM-08)**
    **Property: ``get_value`` returns the default it is given (``None`` when none is) for a name that is not set, whatever the default's type, and the stored value with its type
    (an integer stays an integer, a JSON document stays a document) for one that is.**
    """
    session = adm.open_db_session()
    count, document, missing = _name("ui.value.count"), _name("ui.value.doc"), _name("ui.value.absent")
    try:
        store = SystemVariableStore(session)
        store.create_variable(SystemVariableCreateRequest(name=count, value=7, var_type=VariableType.INTEGER))
        store.create_variable(SystemVariableCreateRequest(name=document, value={"a": [1, 2]}, var_type=VariableType.JSON))
        observed = (
            store.get_value(count, default="x"), store.get_value(document), store.get_value(missing), store.get_value(missing, default=5),
            store.get_value(missing, default=[1, 2]), store.get_value(missing, default={"k": "v"}), store.get_value(missing, default=False),
        )
        store.delete_variable(count)
        store.delete_variable(document)
    finally:
        session.close()
    testbase.assert_equal(observed, (7, {"a": [1, 2]}, None, 5, [1, 2], {"k": "v"}, False))
    return


def test_the_project_managers_fallback_reads_the_system_variables_the_pages_and_the_runtime_share():
    """
    **Feature: one variables store (ADM-08)**
    **Property: ``ProjectManager.resolve_variable`` falls back to the SYSTEM-scope variable of that name (it read the legacy table, which is gone): a variable made on the page
    resolves through it, a project variable of the same name wins, and after the variable is deleted it resolves to nothing.**
    """
    from ccai.pychestrate.core.managers.project_manager import ProjectManager

    name = _name("ui.fallback.limit")
    session = adm.open_db_session()
    try:
        SystemVariableStore(session).create_variable(SystemVariableCreateRequest(name=name, value=15, var_type=VariableType.INTEGER))
        manager = ProjectManager(session)
        found = manager.resolve_variable(987654, name)
        SystemVariableStore(session).delete_variable(name)
        gone = manager.resolve_variable(987654, name)
    finally:
        session.close()
    testbase.assert_equal((found, gone), (15, None))
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
    with engine.begin() as connection:
        # The legacy tables as they were when the migration ran (their ORM classes are gone).
        connection.execute(sa.text(
            "CREATE TABLE global_variables (gvar_id INTEGER NOT NULL PRIMARY KEY, gvar_name VARCHAR(128) NOT NULL, gvar_value_json TEXT, gvar_type VARCHAR(16) NOT NULL, "
            "gvar_description TEXT, gvar_default_value_json TEXT, gvar_created_at DATETIME NOT NULL, gvar_updated_at DATETIME NOT NULL, gvar_updated_by_id BLOB)"
        ))
        connection.execute(sa.text(
            "CREATE TABLE global_variable_history (gvarhist_id INTEGER NOT NULL PRIMARY KEY, gvarhist_variable_id INTEGER NOT NULL, gvarhist_variable_name VARCHAR(128) NOT NULL, "
            "gvarhist_old_value_json TEXT, gvarhist_new_value_json TEXT, gvarhist_changed_by_id BLOB, gvarhist_changed_at DATETIME NOT NULL)"
        ))
        connection.execute(sa.text(
            "CREATE TABLE variables_variable_bindings (binding_id CHAR(32) NOT NULL PRIMARY KEY, scope VARCHAR(8) NOT NULL, scope_id VARCHAR(64) NOT NULL, "
            "name VARCHAR(128) NOT NULL, value_type VARCHAR(10) NOT NULL, value_text TEXT, set_by_user_id CHAR(32), set_at DATETIME NOT NULL, "
            "CONSTRAINT uq_variables_scope_name UNIQUE (scope, scope_id, name))"
        ))
        connection.execute(sa.text(
            "INSERT INTO variables_variable_bindings VALUES ('a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1', 'SYSTEM', '', 'already.there', 'STRING', 'api-set', NULL, '2026-09-01 10:00:00')"
        ))
    user = uuid.uuid4().bytes  # the legacy tables stored user ids as 16 raw bytes on SQLite
    made = "2026-08-01 09:00:00"
    later = "2026-08-02 09:00:00"
    variables = [
        (1, "legacy.count", "12", "integer", "How many", "5", made, later, user),
        (2, "legacy.text", '"hello"', "string", "", None, made, made, None),
        (3, "legacy.doc", '{"b":1,"a":[2]}', "json", "Doc", None, made, made, None),
        (4, "legacy.flag", "true", "boolean", "", None, made, made, None),
        (5, "already.there", '"legacy-value"', "string", "old", None, made, made, None),
    ]
    history_rows = [
        (1, 1, "legacy.count", None, "10", user, made),
        (2, 1, "legacy.count", "10", "12", user, later),
        (3, 99, "legacy.gone", '"x"', None, None, later),
        (4, 5, "already.there", None, '"legacy-value"', None, made),
    ]
    with engine.begin() as connection:
        for row in variables:
            connection.execute(sa.text("INSERT INTO global_variables VALUES (:a, :b, :c, :d, :e, :f, :g, :h, :i)"), dict(zip("abcdefghi", row)))
        for row in history_rows:
            connection.execute(sa.text("INSERT INTO global_variable_history VALUES (:a, :b, :c, :d, :e, :f, :g)"), dict(zip("abcdefg", row)))

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


def _resolve_in(session: Any, name: str) -> Any:
    return variable_service.resolve_effective(db_session=session, name=name, project_id=None, pipeline_id=None, job_id=None, dereference_secrets=False)


def _change_behind_the_cache(session: Any, name: str, text: str) -> None:
    """What another worker's write looks like to this one: the row changes, and this process's cache is not told."""
    session.query(VariableBinding).filter(VariableBinding.name == name).update({"value_text": text})
    session.commit()


def test_a_cached_value_expires_so_a_change_made_in_another_worker_is_seen():
    """
    **Feature: one variables store (ADM-08)**
    **Property: the resolution cache is per process and the service runs several workers, so a value another worker changed was served from the old cache entry for ever;
    an entry now expires after the configured time (a change made behind the cache's back is served until then, and seen after it), a change made through this worker is
    seen at once, and 0 turns the cache off.**
    """
    from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session

    old = os.environ.get(variable_cache.TTL_ENV_VAR)
    try:
        os.environ[variable_cache.TTL_ENV_VAR] = "0.3"
        variable_cache.reset_for_testing()
        _engine, session = build_in_memory_session()
        variable_service.set_variable(db_session=session, scope=VariableScope.SYSTEM, scope_id="", name="shared", value="one", value_type=VariableValueType.STRING, actor_user_id=None)
        first = _resolve_in(session, "shared")
        _change_behind_the_cache(session, "shared", "two")
        within = _resolve_in(session, "shared")
        time.sleep(0.45)
        after = _resolve_in(session, "shared")
        variable_service.set_variable(db_session=session, scope=VariableScope.SYSTEM, scope_id="", name="shared", value="three", value_type=VariableValueType.STRING, actor_user_id=None)
        own_write = _resolve_in(session, "shared")

        os.environ[variable_cache.TTL_ENV_VAR] = "0"
        variable_cache.reset_for_testing()
        _resolve_in(session, "shared")
        _change_behind_the_cache(session, "shared", "four")
        cache_off = _resolve_in(session, "shared")
        session.close()
    finally:
        if old is None:
            os.environ.pop(variable_cache.TTL_ENV_VAR, None)
        else:
            os.environ[variable_cache.TTL_ENV_VAR] = old
        variable_cache.reset_for_testing()

    testbase.assert_equal((first, within, after, own_write, cache_off), ("one", "one", "two", "three", "four"))
    return


def test_the_cache_lifetime_setting_falls_back_to_the_default_when_it_is_not_a_number():
    """
    **Feature: one variables store (ADM-08)**
    **Property: the lifetime is the environment variable when it is a non-negative number, 5 seconds when unset, empty, negative or not a number.**
    """
    old = os.environ.get(variable_cache.TTL_ENV_VAR)
    answers = []
    try:
        for value in (None, "", "2.5", "0", "-3", "soon"):
            if value is None:
                os.environ.pop(variable_cache.TTL_ENV_VAR, None)
            else:
                os.environ[variable_cache.TTL_ENV_VAR] = value
            answers.append(variable_cache.ttl_seconds())
    finally:
        if old is None:
            os.environ.pop(variable_cache.TTL_ENV_VAR, None)
        else:
            os.environ[variable_cache.TTL_ENV_VAR] = old

    testbase.assert_equal(answers, [5.0, 5.0, 2.5, 0.0, 5.0, 5.0])
    return
