"""
.. module:: test_p31d_adm_enrollment_project_picker_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Minting an enrollment token picks a project by name
               instead of typing a UUID the UI never shows
               (audit ADM-10).

.. moduleauthor:: Code Craft AI LLC

The mint form asked for a "Project ID" UUID. Web-UI projects have
integer ids, so the only visible id ("1") crashed the mint with an
internal error, while a made-up UUID for a project that does not exist
was accepted. The form now offers a picker of real projects (web-UI
projects under the UUID the run pipeline uses for them, REST projects
under their own UUID), validates the choice server-side, keeps what
the admin typed on errors, and calls the second field what it is: the
pod label.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import uuid

from ccai import testbase

from ccai.pychestrate.webservice.orchestration.rpa.packet import (
    canonical_project_uuid,
)

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    get,
    open_db_session,
    post_form,
    unique_name,
)


def _create_ui_project(*, cookies) -> tuple:
    from ccai.pychestrate.core.orm import Project  # noqa: E402

    name = unique_name(prefix="enrollproj")
    response = post_form(
        path="/projects/create",
        fields={"name": name, "description": "ADM-10 probe", "metadata": ""},
        cookies=cookies,
    )
    testbase.assert_equal(response.status_code, 303)
    db_session = open_db_session()
    try:
        row = db_session.query(Project).filter(Project.name == name).first()
        project_id = int(row.id)
    finally:
        db_session.close()
    rtnval = (name, project_id)
    return rtnval


def _create_api_project() -> tuple:
    from ccai.pychestrate.webservice.projects.models import (  # noqa: E402
        Project,
        ProjectState,
    )

    slug = unique_name(prefix="apiproj")
    project_uuid = uuid.uuid4()
    db_session = open_db_session()
    try:
        db_session.add(Project(
            project_id=project_uuid,
            slug=slug,
            display_name="API {}".format(slug),
            description="",
            state=ProjectState.ACTIVE,
            extension_fields={},
        ))
        db_session.commit()
    finally:
        db_session.close()
    rtnval = ("API {}".format(slug), str(project_uuid))
    return rtnval


def _tokens_for_pod(*, pod_name: str) -> list:
    from ccai.pychestrate.webservice.clients.models import (  # noqa: E402
        EnrollmentToken,
    )
    db_session = open_db_session()
    try:
        rows = (
            db_session.query(EnrollmentToken)
            .filter(EnrollmentToken.pod_name == pod_name)
            .all()
        )
        rtnval = [str(row.project_id) for row in rows]
    finally:
        db_session.close()
    return rtnval


def test_mint_form_offers_a_web_ui_project_under_its_run_uuid():
    """
    **Feature: enrollment project picker (ADM-10)**
    **Property: a web-UI project appears in the picker by name, with
    the UUID the run pipeline uses for it as the submitted value.**
    """
    cookies = admin_cookies()
    name, project_id = _create_ui_project(cookies=cookies)
    response = get(path="/admin/enrollment-tokens", cookies=cookies)
    marker = 'value="{}"'.format(canonical_project_uuid(str(project_id)))
    position = response.text.find(marker)
    testbase.assert_true(position > 0, "web-UI project not offered")
    option_html = response.text[position:position + 200]
    testbase.assert_true(">{}</option>".format(name) in option_html, option_html)
    return


def test_mint_form_offers_an_api_project_under_its_own_uuid():
    """
    **Feature: enrollment project picker (ADM-10)**
    **Property: an active REST-registry project appears in the picker
    with its own UUID as the value.**
    """
    cookies = admin_cookies()
    label, project_uuid = _create_api_project()
    response = get(path="/admin/enrollment-tokens", cookies=cookies)
    testbase.assert_true(
        'value="{}"'.format(project_uuid) in response.text, "API project not offered"
    )
    testbase.assert_true(label in response.text, "API project label missing")
    return


def test_mint_refuses_a_web_ui_integer_id():
    """
    **Feature: enrollment project picker (ADM-10)**
    **Property: submitting the web-UI integer id ("1") is refused with
    a field error instead of an internal error, and no token is
    created.**
    """
    cookies = admin_cookies()
    _create_ui_project(cookies=cookies)
    pod_name = unique_name(prefix="pod")
    response = post_form(
        path="/admin/enrollment-tokens/mint",
        fields={"project_id": "1", "pod_name": pod_name, "one_shot": "1"},
        cookies=cookies,
    )
    testbase.assert_equal(response.status_code, 400)
    testbase.assert_true(
        "That project does not exist" in response.text, response.text[:1500]
    )
    testbase.assert_equal(_tokens_for_pod(pod_name=pod_name), [])
    return


def test_mint_refuses_an_unknown_uuid():
    """
    **Feature: enrollment project picker (ADM-10)**
    **Property: a well-formed UUID of a project that does not exist is
    refused and no token is created.**
    """
    cookies = admin_cookies()
    pod_name = unique_name(prefix="pod")
    response = post_form(
        path="/admin/enrollment-tokens/mint",
        fields={"project_id": str(uuid.uuid4()), "pod_name": pod_name, "one_shot": "1"},
        cookies=cookies,
    )
    testbase.assert_equal(response.status_code, 400)
    testbase.assert_equal(_tokens_for_pod(pod_name=pod_name), [])
    return


def test_refused_mint_keeps_the_pod_label():
    """
    **Feature: enrollment project picker (ADM-10)**
    **Property: after a refused mint the form still carries the pod
    label the admin typed.**
    """
    cookies = admin_cookies()
    pod_name = unique_name(prefix="keep-pod")
    response = post_form(
        path="/admin/enrollment-tokens/mint",
        fields={"project_id": "", "pod_name": pod_name, "one_shot": "1"},
        cookies=cookies,
    )
    testbase.assert_equal(response.status_code, 400)
    testbase.assert_true(
        'value="{}"'.format(pod_name) in response.text, "pod label was cleared"
    )
    return


def test_mint_with_a_picked_project_scopes_the_token_to_it():
    """
    **Feature: enrollment project picker (ADM-10)**
    **Property: minting with a picked web-UI project stores the token
    under that project's run UUID and shows the one-time secret.**
    """
    cookies = admin_cookies()
    _name, project_id = _create_ui_project(cookies=cookies)
    expected_uuid = canonical_project_uuid(str(project_id))
    pod_name = unique_name(prefix="pod")
    response = post_form(
        path="/admin/enrollment-tokens/mint",
        fields={"project_id": expected_uuid, "pod_name": pod_name, "one_shot": "1"},
        cookies=cookies,
    )
    testbase.assert_equal(response.status_code, 200)
    testbase.assert_true("Shown once" in response.text, "no one-time secret panel")
    testbase.assert_equal(_tokens_for_pod(pod_name=pod_name), [expected_uuid])
    return


def test_token_table_names_the_project():
    """
    **Feature: enrollment project picker (ADM-10)**
    **Property: the token list shows the project's name in the row,
    not only its UUID.**
    """
    cookies = admin_cookies()
    name, project_id = _create_ui_project(cookies=cookies)
    pod_name = unique_name(prefix="pod")
    post_form(
        path="/admin/enrollment-tokens/mint",
        fields={
            "project_id": canonical_project_uuid(str(project_id)),
            "pod_name": pod_name,
            "one_shot": "1",
        },
        cookies=cookies,
    )
    response = get(path="/admin/enrollment-tokens", cookies=cookies)
    row_start = response.text.find("<td>{}</td>".format(pod_name))
    testbase.assert_true(row_start > 0, "token row missing")
    row_html = response.text[max(0, row_start - 400):row_start]
    testbase.assert_true(html.escape(name) in row_html, row_html)
    return


class _Savepoint:
    def commit(self) -> None:
        return

    def rollback(self) -> None:
        return


class _QueryResult:
    def __init__(self, *, rows=None, error=None) -> None:
        self._rows = rows or []
        self._error = error
        return

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        if self._error is not None:
            raise self._error
        return list(self._rows)


class _RegistryBehindSession:
    """
        A session whose web-UI project table answers and whose REST
        project registry table is behind the models (a database that
        has not run the latest migration).
    """

    def begin_nested(self) -> _Savepoint:
        return _Savepoint()

    def query(self, *entities):
        from sqlalchemy.exc import OperationalError  # noqa: E402

        from ccai.pychestrate.webservice.projects.models import Project as ApiProject  # noqa: E402
        if entities and entities[0] is ApiProject:
            return _QueryResult(error=OperationalError(
                "SELECT ...", {}, Exception("no such column: projects_projects.legacy_proj_id")
            ))
        return _QueryResult(rows=[(7, "Lab Seven")])


def test_a_project_registry_behind_its_migration_does_not_break_the_page():
    """
    **Feature: enrollment project picker (ADM-10)**
    **Property: when the REST project registry cannot be read, the
    picker still offers the web-UI projects instead of failing the
    token page.**
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_enrollment import (  # noqa: E402
        _list_project_choices,
    )
    choices = _list_project_choices(db_session=_RegistryBehindSession())
    testbase.assert_equal(
        [(choice.label, choice.value) for choice in choices],
        [("Lab Seven", canonical_project_uuid("7"))],
    )
    return
