"""
.. module:: test_p26p_projects_repository_credentials_e2e_m1
    :platform: Darwin, Linux, Unix
    :synopsis: End-to-end tests for private repositories: the credential
               secret is read from the secrets vault and handed to git
               (PRJ-11).

.. moduleauthor:: Code Craft AI LLC

Repository credentials were never applied: the repository pages built
their manager without any way to read secrets, so git always ran
anonymously and only public repositories worked. These tests drive the
real app against a private repository served on 127.0.0.1 with basic
authentication (:mod:`_git_http_server`), with the token stored in the
secrets vault.

The vault's access rules decide who may use a secret: a repository can
only be saved with, and tested or fetched with, a secret the signed-in
user can read.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import uuid

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    SeededAdmin,
    ensure_app,
    ensure_seeded_admin,
    ensure_seeded_user,
    logged_in_cookies,
    login_as,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._git_http_server import (
    PrivateGitServer,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    get_page,
    open_db_session,
    post_form,
)


_GIT_USER: str = "x-access-token"


@contextmanager
def _isolated_git_config() -> Iterator[None]:
    """
        Keep the developer's own git configuration (credential helpers,
        URL rewrites) out of the git commands the app runs.
    """
    saved = {key: os.environ.get(key) for key in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return


def _ensure_active_kek() -> None:
    """
        The vault encrypts with the process's active KEK; other suites
        reset it, so install a test KEK when none is active.
    """
    from ccai.pychestrate.webservice.secrets.kek_loader import (  # noqa: E402
        KekHandle,
        get_active_kek,
        set_active_kek,
    )
    from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes  # noqa: E402
    try:
        get_active_kek()
    except Exception:
        set_active_kek(kek=KekHandle(
            kek_id="prj11-test-kek", key_material=SecretBytes(b"K" * 32), source="test",
        ))
    return


def _put_secret(
        *, owner: SeededAdmin, value: str, personal: bool = False
    ) -> str:
    """
        Store ``value`` in the secrets vault as ``owner``: an organization
        secret, or ``owner``'s personal secret when ``personal``.

        :returns: The new secret's reference.
    """
    from ccai.pychestrate.webservice.secrets import secrets_service  # noqa: E402
    from ccai.pychestrate.webservice.secrets.models import SecretScopeKind  # noqa: E402
    from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes  # noqa: E402
    from ccai.pychestrate.webservice.secrets.secrets_aspects import (  # noqa: E402
        build_default_aspects,
    )
    from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind  # noqa: E402
    from ccai.pychestrate.webservice.security.auth.session_service import (  # noqa: E402
        AuthPrincipal,
    )

    _ensure_active_kek()
    secret_ref = "ci/prj11-{}".format(uuid.uuid4().hex[:10])
    db_session = open_db_session()
    try:
        secrets_service.put_secret(
            db_session=db_session,
            principal=AuthPrincipal(
                user_id=owner.user_id, session_id="", provider_kind=AuthProviderKind.LOCAL,
                provider_name="local",
            ),
            secret_ref=secret_ref,
            plaintext=SecretBytes(value.encode("utf-8")),
            aspects=build_default_aspects(),
            scope_kind=SecretScopeKind.USER if personal else SecretScopeKind.ORG,
            scope_ref=owner.user_id if personal else None,
            owner_user_id=owner.user_id,
        )
        db_session.commit()
    finally:
        db_session.close()
    return secret_ref


def _developer(*, project_id: int) -> SeededAdmin:
    """
        A fresh user with no system role, added to the project as a
        developer.
    """
    from ccai.pychestrate.core.orm import ProjectMember  # noqa: E402

    user = ensure_seeded_user(login="prj11-dev-{}".format(uuid.uuid4().hex[:8]))
    db_session = open_db_session()
    try:
        db_session.add(ProjectMember(
            project_id=project_id, user_id=uuid.UUID(user.user_id), role="developer",
        ))
        db_session.commit()
    finally:
        db_session.close()
    return user


def _create_repository(
        *, wsgi_app: Any, cookies: Dict[str, str], project_id: int, url: str,
        secret_ref: Optional[str]
    ) -> Any:
    """
        Submit the repository create form (HTTPS access token when
        ``secret_ref`` is given, otherwise no authentication).
    """
    rtnval = post_form(
        wsgi_app=wsgi_app,
        path="/projects/{}/repositories/create".format(project_id),
        cookies=cookies,
        fields={
            "name": "private-{}".format(uuid.uuid4().hex[:6]),
            "url": url,
            "auth_type": "https_token" if secret_ref is not None else "none",
            "credential_secret_ref": secret_ref or "",
            "default_branch": "main",
            "description": "",
        },
    )
    return rtnval


def _repository_id(response: Any) -> int:
    location = response.header("Location") or ""
    if response.status_code not in (302, 303) or "/repositories/" not in location:
        raise AssertionError(
            "repository create did not redirect to the repository: {} {} {}".format(
                response.status_code, location, response.text[:300]
            )
        )
    rtnval = int(location.rstrip("/").split("/")[-1])
    return rtnval


def _run_action(
        *, wsgi_app: Any, cookies: Dict[str, str], project_id: int, repository_id: int,
        action: str
    ) -> str:
    """
        POST the repository's ``test`` or ``fetch`` action and return the
        page it redirects to (which shows the flash).
    """
    response = post_form(
        wsgi_app=wsgi_app,
        path="/projects/{}/repositories/{}/{}".format(project_id, repository_id, action),
        cookies=cookies,
        fields={},
    )
    location = response.header("Location") or ""
    page = get_page(wsgi_app=wsgi_app, path=location, cookies=cookies)
    return page.text


def _admin_setup(*, prefix: str) -> Dict[str, Any]:
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    project_id = create_project_via_ui(wsgi_app=handle.wsgi_app, cookies=cookies, prefix=prefix)
    rtnval = {
        "wsgi_app": handle.wsgi_app,
        "cookies": cookies,
        "project_id": project_id,
        "admin": ensure_seeded_admin(),
    }
    return rtnval


def test_a_private_repository_passes_the_connection_test_with_the_vault_token():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: a repository using HTTPS access token authentication
    passes "Test connection" against a private repository: the token is
    read from the secrets vault and sent to the server.**
    """
    setup = _admin_setup(prefix="prj11-test")
    token = "tok-" + uuid.uuid4().hex
    server = PrivateGitServer(username=_GIT_USER, password=token)
    try:
        with _isolated_git_config():
            secret_ref = _put_secret(owner=setup["admin"], value=token)
            repository_id = _repository_id(_create_repository(
                wsgi_app=setup["wsgi_app"], cookies=setup["cookies"],
                project_id=setup["project_id"], url=server.url, secret_ref=secret_ref,
            ))
            page = _run_action(
                wsgi_app=setup["wsgi_app"], cookies=setup["cookies"],
                project_id=setup["project_id"], repository_id=repository_id, action="test",
            )
    finally:
        server.close()

    testbase.assert_equal("Repository connectivity test successful." in page, True)
    return


def test_fetch_records_the_latest_commit_of_a_private_repository():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: "Fetch" on a private repository records the commit its
    default branch points at.**
    """
    from ccai.pychestrate.core.orm import ProjectRepository  # noqa: E402

    setup = _admin_setup(prefix="prj11-fetch")
    token = "tok-" + uuid.uuid4().hex
    server = PrivateGitServer(username=_GIT_USER, password=token)
    try:
        with _isolated_git_config():
            secret_ref = _put_secret(owner=setup["admin"], value=token)
            repository_id = _repository_id(_create_repository(
                wsgi_app=setup["wsgi_app"], cookies=setup["cookies"],
                project_id=setup["project_id"], url=server.url, secret_ref=secret_ref,
            ))
            _run_action(
                wsgi_app=setup["wsgi_app"], cookies=setup["cookies"],
                project_id=setup["project_id"], repository_id=repository_id, action="fetch",
            )
        db_session = open_db_session()
        try:
            recorded = db_session.query(ProjectRepository).filter(
                ProjectRepository.id == repository_id
            ).one().last_commit_sha
        finally:
            db_session.close()
        expected = server.head_sha
    finally:
        server.close()

    testbase.assert_equal(recorded, expected)
    return


def test_a_rejected_token_is_explained_without_revealing_it():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: when the server refuses the token, the page says the
    credentials were refused and never shows the token.**
    """
    setup = _admin_setup(prefix="prj11-refused")
    wrong_token = "wrong-" + uuid.uuid4().hex
    server = PrivateGitServer(username=_GIT_USER, password="right-" + uuid.uuid4().hex)
    try:
        with _isolated_git_config():
            secret_ref = _put_secret(owner=setup["admin"], value=wrong_token)
            repository_id = _repository_id(_create_repository(
                wsgi_app=setup["wsgi_app"], cookies=setup["cookies"],
                project_id=setup["project_id"], url=server.url, secret_ref=secret_ref,
            ))
            page = _run_action(
                wsgi_app=setup["wsgi_app"], cookies=setup["cookies"],
                project_id=setup["project_id"], repository_id=repository_id, action="test",
            )
    finally:
        server.close()

    testbase.assert_equal(
        ("refused the credentials" in page, wrong_token in page), (True, False)
    )
    return


def test_a_missing_secret_is_refused_when_the_repository_is_saved():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: saving a repository that names a secret the vault does
    not have is refused with a message naming it.**
    """
    setup = _admin_setup(prefix="prj11-missing")
    response = _create_repository(
        wsgi_app=setup["wsgi_app"], cookies=setup["cookies"], project_id=setup["project_id"],
        url="https://git.example.invalid/org/repo.git", secret_ref="ci/prj11-does-not-exist",
    )

    testbase.assert_equal(
        (response.status_code, "There is no secret named ci/prj11-does-not-exist" in response.text),
        (400, True),
    )
    return


def test_a_developer_cannot_save_a_repository_with_a_secret_they_cannot_read():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: a project developer who cannot read an organization
    secret cannot save a repository that uses it (which would make the
    server send it to a URL of their choosing).**
    """
    from ccai.pychestrate.core.orm import ProjectRepository  # noqa: E402

    setup = _admin_setup(prefix="prj11-exfil")
    secret_ref = _put_secret(owner=setup["admin"], value="prod-" + uuid.uuid4().hex)
    developer = _developer(project_id=setup["project_id"])
    cookies = login_as(wsgi_app=setup["wsgi_app"], user=developer)

    response = _create_repository(
        wsgi_app=setup["wsgi_app"], cookies=cookies, project_id=setup["project_id"],
        url="https://collector.example.invalid/steal.git", secret_ref=secret_ref,
    )
    db_session = open_db_session()
    try:
        saved = db_session.query(ProjectRepository).filter(
            ProjectRepository.project_id == setup["project_id"]
        ).count()
    finally:
        db_session.close()

    testbase.assert_equal(
        (response.status_code, "You do not have access to the secret" in response.text, saved),
        (400, True, 0),
    )
    return


def test_a_developer_who_cannot_read_the_secret_cannot_make_the_server_use_it():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: when a developer who cannot read the repository's
    secret runs "Test connection", the page explains why and the git
    server is never contacted.**
    """
    setup = _admin_setup(prefix="prj11-denied")
    token = "tok-" + uuid.uuid4().hex
    server = PrivateGitServer(username=_GIT_USER, password=token)
    try:
        with _isolated_git_config():
            secret_ref = _put_secret(owner=setup["admin"], value=token)
            repository_id = _repository_id(_create_repository(
                wsgi_app=setup["wsgi_app"], cookies=setup["cookies"],
                project_id=setup["project_id"], url=server.url, secret_ref=secret_ref,
            ))
            developer = _developer(project_id=setup["project_id"])
            cookies = login_as(wsgi_app=setup["wsgi_app"], user=developer)
            page = _run_action(
                wsgi_app=setup["wsgi_app"], cookies=cookies,
                project_id=setup["project_id"], repository_id=repository_id, action="test",
            )
        contacted = list(server.authorizations)
    finally:
        server.close()

    testbase.assert_equal(
        ("You do not have access to the secret" in page, contacted), (True, [])
    )
    return


def test_a_developer_can_use_their_own_personal_secret():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: a project developer without any system role can set up
    and test a private repository with a personal secret of their own.**
    """
    setup = _admin_setup(prefix="prj11-personal")
    token = "tok-" + uuid.uuid4().hex
    server = PrivateGitServer(username=_GIT_USER, password=token)
    try:
        with _isolated_git_config():
            developer = _developer(project_id=setup["project_id"])
            secret_ref = _put_secret(owner=developer, value=token, personal=True)
            cookies = login_as(wsgi_app=setup["wsgi_app"], user=developer)
            repository_id = _repository_id(_create_repository(
                wsgi_app=setup["wsgi_app"], cookies=cookies,
                project_id=setup["project_id"], url=server.url, secret_ref=secret_ref,
            ))
            page = _run_action(
                wsgi_app=setup["wsgi_app"], cookies=cookies,
                project_id=setup["project_id"], repository_id=repository_id, action="test",
            )
    finally:
        server.close()

    testbase.assert_equal("Repository connectivity test successful." in page, True)
    return


def test_the_secret_picker_offers_only_secrets_the_user_can_read():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: the create form suggests the developer's personal
    secret and not an organization secret they cannot read.**
    """
    setup = _admin_setup(prefix="prj11-picker")
    org_ref = _put_secret(owner=setup["admin"], value="org-" + uuid.uuid4().hex)
    developer = _developer(project_id=setup["project_id"])
    personal_ref = _put_secret(owner=developer, value="mine-" + uuid.uuid4().hex, personal=True)
    cookies = login_as(wsgi_app=setup["wsgi_app"], user=developer)

    page = get_page(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/repositories/create".format(setup["project_id"]),
        cookies=cookies,
    ).text

    testbase.assert_equal(
        ('<option value="{}">'.format(personal_ref) in page,
         '<option value="{}">'.format(org_ref) in page),
        (True, False),
    )
    return


def test_the_create_form_defaults_to_no_authentication():
    """
    **Feature: projects (PRJ-11 repository credentials)**
    **Property: the create form preselects "Public (no authentication)"
    (it used to preselect HTTPS token, so adding a public repository
    failed until the user changed it).**
    """
    setup = _admin_setup(prefix="prj11-default")

    page = get_page(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/repositories/create".format(setup["project_id"]),
        cookies=setup["cookies"],
    ).text

    testbase.assert_equal('<option value="none" selected>' in page, True)
    return
