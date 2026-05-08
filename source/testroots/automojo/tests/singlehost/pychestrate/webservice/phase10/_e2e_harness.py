"""
.. module:: tests.singlehost.pychestrate.webservice.phase10._e2e_harness
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared end-to-end test harness for the consumer UI
               (tier-1 + tier-2 + future tiers).

.. moduleauthor:: Automation Mojo LLC

The phase-10 e2e tests boot the *real* webworks app from
:mod:`app_pychestrate_main`, register the consumer-UI route
surface, advance the lifecycle to ``INFRASTRUCTURE_READY``, and
drive the resulting WSGI callable from raw PEP-3333 environs.
This module owns the bootstrap + driver scaffolding so every
e2e test module shares one cached app singleton (the webworks
persona is process-global -- only one persona per interpreter).

Layout:

* **Bootstrap singleton** -- :func:`ensure_app` lazily writes a
  test KEK file, runs :func:`bootstrap_runtime` against an
  in-memory SQLite DB, publishes a deterministic UI cookie
  secret, installs the templating environment, registers the
  consumer-UI route registrars, and wraps the result in a
  ``WSGIApplication``. Cached -- subsequent calls are free.
* **WSGI driver** -- :func:`drive_request` builds a PEP-3333
  environ from method / path / cookies / body, runs the WSGI
  callable, and returns a :class:`WsgiResponse` with cookie
  parsing, header lookup, and ``.text`` body decoding.
* **Schema-shape compatibility shims** -- the legacy
  ``PychestrateModelBase`` models declare BigInteger
  primary keys (which SQLite refuses to autoincrement) and
  store ``DateTime(timezone=True)`` columns that round-trip
  naive on SQLite. :func:`patch_legacy_pk_columns_for_sqlite`
  + :func:`patch_utc_now_for_sqlite_tz_compat` paper over
  both, so authenticated tests can use the legacy
  :class:`SecurityManager` against an in-memory DB. See
  :ref:`12-00-consumer-ui-auth-stack` for context.
* **DB-pool swap** --
  :func:`ensure_shared_in_memory_db_pool` rebuilds the
  bootstrap-published engine on top of
  :class:`sqlalchemy.pool.StaticPool` so every checkout
  shares a single in-memory database (default ``NullPool``
  hands out per-checkout fresh DBs, fragmenting writes).
* **Auth seed** -- :func:`ensure_seeded_admin` creates an
  admin :class:`User` + werkzeug-hashed
  :class:`PasswordHistory` row for tests that need to log in.
* **Cookie + login helpers** --
  :func:`decode_session_cookie` /
  :func:`login_via_post` / :func:`logged_in_cookies` /
  :func:`extract_csrf_token_from_cookies`.

Helpers prefixed with a leading underscore inside this module
are internal; the public surface is everything without an
underscore (``ensure_app``, ``drive_request``,
``WsgiResponse``, etc.). Test modules import what they need
by name.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import os
import sys
import tempfile
import uuid

from http.cookies import SimpleCookie
from typing import Any, Callable, Dict, List, Optional, Tuple

# Importing this module pulls every model side-effect import that
# registers tables on ``PychestratePhase1Base.metadata`` -- without
# this pull the auto-create-schema step would only build the
# Phase-1 core tables and the resources / projects FKs would
# dangle.
import automojo.pychestrate.webservice.extensions.bootstrap  # noqa: F401

from automojo.pychestrate.webservice.metadata import (
    RUNTIME_ENVIRONMENTS,
    SITE_DIRECTORIES,
    SITE_SHARED_GLOBALS,
)
from automojo.pychestrate.webservice.runtime_bootstrap import (
    RuntimeBootstrapConfig,
    bootstrap_runtime,
)
from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
    register_config_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    register_projects_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    register_resources_routes,
)
from automojo.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
    csrf,
)
from automojo.pychestrate.webservice.webinterface.foundation.static_files import (
    register_static_routes,
)
from automojo.pychestrate.webservice.webinterface.foundation.templating import (
    build_jinja_environment,
    discover_blueprint_template_paths,
    set_default_environment,
)
from automojo.pychestrate.webservice.webinterface.foundation.url_for import (
    install_url_for_global,
)
from automojo.webworks.wsgi.application import create_wsgi_application


TEST_UI_COOKIE_SECRET: bytes = b"\x00" * 32


# ---------------------------------------------------------------------------
# Bootstrap singleton
# ---------------------------------------------------------------------------


class TestAppHandle:
    """
        Holds the bootstrapped WSGI app + the temporary KEK file
        path used during the bootstrap.
    """

    def __init__(self, *, wsgi_app: Any, kek_file_path: str) -> None:
        self.wsgi_app: Any = wsgi_app
        self.kek_file_path: str = kek_file_path
        return


_APP_HANDLE: Optional[TestAppHandle] = None


def _write_test_kek_file() -> str:
    """
        Emit a 32-byte KEK to a tempfile and return its path.
    """
    fd, path = tempfile.mkstemp(prefix="pych-e2e-kek-", suffix=".bin")
    try:
        os.write(fd, b"\x42" * 32)
    finally:
        os.close(fd)
    return path


def _bootstrap_runtime_for_tests(*, kek_file_path: str) -> None:
    """
        One-call runtime bootstrap with test-friendly defaults:
        in-memory SQLite, schema auto-create, file-source KEK,
        no password pepper, deterministic UI cookie secret.
    """
    config = RuntimeBootstrapConfig(
        database_url="sqlite:///:memory:",
        runtime_environment=RUNTIME_ENVIRONMENTS.TESTING,
        kek_source="file",
        kek_id="e2e-test-kek",
        kek_file_path=kek_file_path,
        kek_env_var=None,
        password_pepper_source=None,
        password_pepper_file_path=None,
        password_pepper_env_var=None,
        ui_cookie_secret_source=None,
        ui_cookie_secret_file_path=None,
        ui_cookie_secret_env_var=None,
        auto_create_schema=True,
        sql_echo=False,
    )
    bootstrap_runtime(config=config)
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = TEST_UI_COOKIE_SECRET
    return


def _install_test_templating() -> None:
    """
        Mirror ``app_pychestrate_main.install_web_ui_templating``.
    """
    template_paths = discover_blueprint_template_paths(
        blueprints_root=SITE_DIRECTORIES.DIR_BLUEPRINTS,
    )
    if len(template_paths) == 0:
        template_paths = [SITE_DIRECTORIES.DIR_BLUEPRINTS]
    environment = build_jinja_environment(
        template_search_paths=template_paths,
    )
    install_url_for_global(environment=environment)
    set_default_environment(environment=environment)
    return


def _build_consumer_ui_test_app() -> Any:
    """
        Reuse the production ``app`` singleton from
        :mod:`app_pychestrate_main`, install templating, register
        the three consumer-UI registrars + static-files
        registrar, advance the lifecycle, and wrap with the
        production ``build_wsgi_compat_dispatch`` shim.

        ``establish_webapp_persona`` is process-global; importing
        ``app_pychestrate_main`` establishes ``"pychestrate"`` as
        the persona, so we reuse that singleton.
    """
    from app_pychestrate_main import (  # noqa: E402
        app,
        build_wsgi_compat_dispatch,
    )
    _install_test_templating()
    register_static_routes(
        app=app,
        url_prefix="/static",
        static_root=SITE_DIRECTORIES.DIR_STATIC,
    )
    register_config_routes(app=app)
    register_resources_routes(app=app)
    register_projects_routes(app=app)
    app.startup()
    rtnval = create_wsgi_application(
        config={"handler": build_wsgi_compat_dispatch(app=app)}
    )
    return rtnval


def ensure_app() -> TestAppHandle:
    """
        Lazy module-level singleton: bootstrap the runtime + build
        the WSGI app once, return the cached handle on subsequent
        calls. Idempotent across tests + across test modules.
    """
    global _APP_HANDLE
    if _APP_HANDLE is not None:
        return _APP_HANDLE
    kek_path = _write_test_kek_file()
    _bootstrap_runtime_for_tests(kek_file_path=kek_path)
    wsgi_app = _build_consumer_ui_test_app()
    _APP_HANDLE = TestAppHandle(
        wsgi_app=wsgi_app, kek_file_path=kek_path
    )
    return _APP_HANDLE


# ---------------------------------------------------------------------------
# In-process WSGI driver
# ---------------------------------------------------------------------------


class WsgiResponse:
    """
        Captured response from a single :func:`drive_request`
        call.
    """

    def __init__(
            self,
            *,
            status_code: int,
            headers: List[Tuple[str, str]],
            body: bytes
        ) -> None:
        self.status_code: int = status_code
        self.headers: List[Tuple[str, str]] = headers
        self.body: bytes = body
        return

    def header(self, name: str) -> Optional[str]:
        """
            Case-insensitive single-header lookup. Returns the
            first matching header value or ``None``.
        """
        lowered = name.lower()
        for key, value in self.headers:
            if key.lower() == lowered:
                return value
        return None

    def collect_set_cookies(self) -> Dict[str, str]:
        """
            Parse every ``Set-Cookie`` header into a mapping.
        """
        rtnval: Dict[str, str] = {}
        for key, value in self.headers:
            if key.lower() != "set-cookie":
                continue
            jar = SimpleCookie()
            jar.load(value)
            for cookie_name, morsel in jar.items():
                rtnval[cookie_name] = morsel.value
        return rtnval

    @property
    def text(self) -> str:
        try:
            rtnval = self.body.decode("utf-8")
        except UnicodeDecodeError:
            rtnval = self.body.decode("latin-1")
        return rtnval


def drive_request(
        *,
        wsgi_app: Any,
        method: str,
        path: str,
        query_string: str = "",
        body: bytes = b"",
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None
    ) -> WsgiResponse:
    """
        Drive a single PEP-3333 WSGI request against the supplied
        app and return a :class:`WsgiResponse`.
    """
    body_stream = io.BytesIO(body)
    environ: Dict[str, Any] = {
        "REQUEST_METHOD": method.upper(),
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "SERVER_NAME": "test.invalid",
        "SERVER_PORT": "80",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "SCRIPT_NAME": "",
        "wsgi.input": body_stream,
        "wsgi.errors": sys.stderr,
        "wsgi.url_scheme": "http",
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "wsgi.version": (1, 0),
        "CONTENT_LENGTH": str(len(body)) if len(body) > 0 else "",
    }
    if cookies is not None and len(cookies) > 0:
        cookie_header = "; ".join(
            "{}={}".format(name, value) for name, value in cookies.items()
        )
        environ["HTTP_COOKIE"] = cookie_header
    if headers is not None:
        for name, value in headers.items():
            normalized = "HTTP_" + name.upper().replace("-", "_")
            environ[normalized] = value
        if "Content-Type" in headers:
            environ["CONTENT_TYPE"] = headers["Content-Type"]
        if "content-type" in headers:
            environ["CONTENT_TYPE"] = headers["content-type"]

    captured: Dict[str, Any] = {}

    def _start_response(
            status: str,
            response_headers: List[Tuple[str, str]],
            exc_info: Any = None
        ) -> Any:
        captured["status"] = status
        captured["headers"] = response_headers

        def _writer(chunk: bytes) -> None:
            return None

        return _writer

    body_chunks: List[bytes] = []
    iterator = wsgi_app(environ, _start_response)
    try:
        for chunk in iterator:
            if chunk is not None and len(chunk) > 0:
                body_chunks.append(chunk)
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            close()

    status_code = int(captured["status"].split(" ", 1)[0])
    body_bytes = b"".join(body_chunks)
    rtnval = WsgiResponse(
        status_code=status_code,
        headers=captured["headers"],
        body=body_bytes,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Legacy-schema SQLite compatibility shims
# (see userguide/12-00-consumer-ui-auth-stack.rst for context)
# ---------------------------------------------------------------------------


def patch_utc_now_for_sqlite_tz_compat() -> None:
    """
        SQLAlchemy's ``DateTime(timezone=True)`` columns
        round-trip through SQLite as naive datetimes (SQLite has
        no native tz support). The legacy
        :meth:`SecurityManager.validate_token` compares
        ``session.expires_at`` (naive on read-back) against
        ``utc_now()`` (timezone-aware) and raises ``TypeError``,
        which the handler swallows as "session invalid".

        Monkey-patch :func:`utc_now` on the security_manager and
        defaults modules to return naive UTC. Idempotent.
    """
    from datetime import datetime, timezone  # noqa: E402
    from automojo.pychestrate.core import defaults as _defaults  # noqa: E402
    from automojo.pychestrate.core.managers import (  # noqa: E402
        security_manager as _sm,
    )

    def naive_utc_now() -> datetime:
        rtnval = datetime.now(timezone.utc).replace(tzinfo=None)
        return rtnval

    if getattr(_defaults.utc_now, "__name__", "") != "naive_utc_now":
        _defaults.utc_now = naive_utc_now
    if getattr(_sm.utc_now, "__name__", "") != "naive_utc_now":
        _sm.utc_now = naive_utc_now
    return


def patch_legacy_pk_columns_for_sqlite() -> None:
    """
        Walk every table on both metadata trees and rewrite any
        single-column ``BigInteger`` autoincrement primary key to
        plain ``Integer`` plus the SQLite ``autoincrement`` table
        option, so the emitted DDL is
        ``INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT`` (which
        SQLite *does* autoincrement) instead of
        ``BIGINT NOT NULL, PRIMARY KEY (...)``. Idempotent.
    """
    import sqlalchemy as sa  # noqa: E402

    from automojo.pychestrate.core.orm import (  # noqa: E402
        PychestrateModelBase,
    )
    from automojo.pychestrate.webservice.persistence.schema import (  # noqa: E402
        PychestratePhase1Base,
    )

    metadatas = (
        PychestrateModelBase.metadata,
        PychestratePhase1Base.metadata,
    )
    for metadata in metadatas:
        for table in metadata.tables.values():
            pk_cols = list(table.primary_key.columns)
            if len(pk_cols) != 1:
                continue
            pk = pk_cols[0]
            if not pk.autoincrement:
                continue
            current_type = pk.type
            if type(current_type) is sa.Integer:
                continue
            if not isinstance(current_type, sa.BigInteger):
                continue
            pk.type = sa.Integer()
            table.dialect_options["sqlite"]["autoincrement"] = True
    return


def ensure_shared_in_memory_db_pool() -> None:
    """
        ``sqlite:///:memory:`` defaults to ``NullPool``, which
        gives every checkout a fresh connection -- and in SQLite
        each connection has its own in-memory database. Swap the
        bootstrap-published engine for one that uses
        :class:`sqlalchemy.pool.StaticPool` so every checkout
        shares a single in-memory connection, and re-create both
        metadata trees on the new engine.
    """
    import sqlalchemy as sa  # noqa: E402
    from sqlalchemy.pool import StaticPool  # noqa: E402
    from sqlalchemy.orm import sessionmaker  # noqa: E402

    from automojo.pychestrate.webservice.persistence.schema import (  # noqa: E402
        PychestratePhase1Base,
    )
    from automojo.pychestrate.core.orm import (  # noqa: E402
        PychestrateModelBase,
    )

    engine = SITE_SHARED_GLOBALS.DATABASE_ENGINE
    if engine is None:
        return
    pool_cls_name = type(engine.pool).__name__
    if pool_cls_name == "StaticPool":
        return
    if "memory" not in str(engine.url):
        return

    patch_legacy_pk_columns_for_sqlite()
    patch_utc_now_for_sqlite_tz_compat()

    new_engine = sa.create_engine(
        str(engine.url),
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    PychestratePhase1Base.metadata.create_all(new_engine)
    PychestrateModelBase.metadata.create_all(new_engine)

    new_factory = sessionmaker(bind=new_engine, expire_on_commit=False)
    SITE_SHARED_GLOBALS.DATABASE_ENGINE = new_engine
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = new_factory
    return


# ---------------------------------------------------------------------------
# Auth seed
# ---------------------------------------------------------------------------


E2E_ADMIN_LOGIN: str = "e2e-admin"
E2E_ADMIN_PASSWORD: str = "e2e-admin-secret-1!"
E2E_ADMIN_EMAIL: str = "e2e-admin@example.invalid"


class SeededAdmin:
    """
        Bookkeeping handle for the seeded admin user.
    """

    def __init__(
            self, *, user_id: str, login: str, password: str
        ) -> None:
        self.user_id: str = user_id
        self.login: str = login
        self.password: str = password
        return


_SEEDED_ADMIN: Optional[SeededAdmin] = None


def ensure_seeded_admin() -> SeededAdmin:
    """
        Create an admin :class:`User` + werkzeug-hashed
        :class:`PasswordHistory` row once, return the cached
        handle on subsequent calls. Triggers
        :func:`ensure_app` + :func:`ensure_shared_in_memory_db_pool`
        on first invocation so the legacy auth schema exists
        before the seed runs.
    """
    global _SEEDED_ADMIN
    if _SEEDED_ADMIN is not None:
        return _SEEDED_ADMIN

    ensure_app()
    ensure_shared_in_memory_db_pool()

    from werkzeug.security import generate_password_hash  # noqa: E402
    from automojo.pychestrate.core.orm import (  # noqa: E402
        PasswordHistory,
        User,
    )

    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    db_session = factory()
    try:
        existing = (
            db_session.query(User)
            .filter(User.login == E2E_ADMIN_LOGIN)
            .first()
        )
        if existing is not None:
            _SEEDED_ADMIN = SeededAdmin(
                user_id=str(existing.id),
                login=E2E_ADMIN_LOGIN,
                password=E2E_ADMIN_PASSWORD,
            )
            return _SEEDED_ADMIN

        user = User(
            id=uuid.uuid4(),
            first_name="E2E",
            last_name="Admin",
            display_name="E2E Admin",
            email=E2E_ADMIN_EMAIL,
            login=E2E_ADMIN_LOGIN,
            ownertag="e2e",
            status="active",
            roles="admin",
            authtype="internal",
        )
        db_session.add(user)
        db_session.flush()

        password_hash = generate_password_hash(E2E_ADMIN_PASSWORD)
        history = PasswordHistory(
            user_id=user.id,
            password_hash=password_hash,
        )
        db_session.add(history)
        db_session.commit()

        _SEEDED_ADMIN = SeededAdmin(
            user_id=str(user.id),
            login=E2E_ADMIN_LOGIN,
            password=E2E_ADMIN_PASSWORD,
        )
        return _SEEDED_ADMIN
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cookie + login helpers
# ---------------------------------------------------------------------------


def decode_session_cookie(*, cookie_value: str) -> Dict[str, Any]:
    """
        Verify a session cookie's HMAC and return the decoded
        payload (or ``None`` on tampered / malformed input).
    """
    rtnval = cookie_session.verify_session_payload(
        cookie_value=cookie_value,
        secret=TEST_UI_COOKIE_SECRET,
    )
    return rtnval


def extract_csrf_token_from_cookies(
        *, cookies: Dict[str, str]
    ) -> Optional[str]:
    """
        Pull the CSRF token out of the signed session cookie
        payload. Returns ``None`` when the session cookie is
        missing / unverifiable.
    """
    cookie_value = cookies.get(cookie_session.COOKIE_NAME, None)
    if cookie_value is None:
        return None
    payload = decode_session_cookie(cookie_value=cookie_value)
    if payload is None:
        return None
    rtnval = payload.get(csrf.SESSION_KEY, None)
    return rtnval


def login_via_post(
        *, wsgi_app: Any, login: str, password: str
    ) -> Tuple[WsgiResponse, Dict[str, str]]:
    """
        POST credentials to ``/config/login`` and return
        ``(response, cookies)`` -- ``cookies`` is empty on
        failure.
    """
    body = (
        "username={username}&password={password}".format(
            username=login, password=password
        )
    ).encode("utf-8")
    response = drive_request(
        wsgi_app=wsgi_app,
        method="POST",
        path="/config/login",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    cookies = response.collect_set_cookies()
    return (response, cookies)


def logged_in_cookies(*, wsgi_app: Any) -> Dict[str, str]:
    """
        Convenience: seed the admin user, POST login, return the
        cookie jar. Raises :class:`AssertionError` when the login
        response is not 303.
    """
    admin = ensure_seeded_admin()
    response, cookies = login_via_post(
        wsgi_app=wsgi_app, login=admin.login, password=admin.password
    )
    if response.status_code != 303:
        raise AssertionError(
            "expected login POST to 303 -- got {} ({})".format(
                response.status_code, response.text[:120]
            )
        )
    return cookies


# ---------------------------------------------------------------------------
# RBAC seeding (legacy ``SystemRole`` / ``Permission`` rows)
# ---------------------------------------------------------------------------


# Permission strings used by the consumer UI's
# ``_require_permission_or_redirect`` calls. Tier-3 tests seed
# the ones they need; the values track the constants in the
# production handlers so tests catch any rename drift.
PERMISSION_RESOURCES_MANAGE: str = "resources.manage"
PERMISSION_USERS_MANAGE: str = "users.manage"
PERMISSION_VARIABLES_MANAGE: str = "variables.manage"


def grant_permissions_to_role(
        *, role_name: str, permission_names: List[str]
    ) -> None:
    """
        Idempotently create :class:`SystemRole` + the listed
        :class:`Permission` rows and the many-to-many bindings
        between them. Used by tests that need a role with a
        known permission set.

        :param role_name: Role to create / update.
        :param permission_names: Permission names to ensure
                                 exist + are bound to the role.
    """
    from automojo.pychestrate.core.orm import (  # noqa: E402
        Permission,
        SystemRole,
    )
    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    db_session = factory()
    try:
        role = (
            db_session.query(SystemRole)
            .filter(SystemRole.name == role_name)
            .first()
        )
        if role is None:
            role = SystemRole(
                name=role_name,
                description="seeded by e2e harness",
                is_system=False,
            )
            db_session.add(role)
            db_session.flush()

        for perm_name in permission_names:
            perm = (
                db_session.query(Permission)
                .filter(Permission.name == perm_name)
                .first()
            )
            if perm is None:
                perm = Permission(
                    name=perm_name,
                    description="seeded by e2e harness",
                )
                db_session.add(perm)
                db_session.flush()
            if perm not in role.permissions:
                role.permissions.append(perm)

        db_session.commit()
    finally:
        try:
            db_session.close()
        except Exception:
            pass
    return


_ADMIN_ROLE_PERMISSIONS: List[str] = [
    PERMISSION_RESOURCES_MANAGE,
    PERMISSION_USERS_MANAGE,
    PERMISSION_VARIABLES_MANAGE,
]


def ensure_seeded_admin_role() -> None:
    """
        Idempotently ensure the legacy ``"admin"`` SystemRole has
        the consumer-UI's three top-level admin permissions
        (resources.manage / users.manage / variables.manage).
        Tests that exercise admin-gated routes call this once.
    """
    grant_permissions_to_role(
        role_name="admin",
        permission_names=_ADMIN_ROLE_PERMISSIONS,
    )
    return


# ---------------------------------------------------------------------------
# Viewer user seed (a non-admin login for permission-denied tests)
# ---------------------------------------------------------------------------


E2E_VIEWER_LOGIN: str = "e2e-viewer"
E2E_VIEWER_PASSWORD: str = "e2e-viewer-secret-1!"
E2E_VIEWER_EMAIL: str = "e2e-viewer@example.invalid"


_SEEDED_VIEWER: Optional[SeededAdmin] = None


def ensure_seeded_viewer() -> SeededAdmin:
    """
        Seed a non-admin user (login ``e2e-viewer``, role
        ``viewer`` -- which the harness deliberately does NOT
        grant any admin permissions) and return a
        :class:`SeededAdmin` handle. Cached.

        Tier-3 tests use this user to exercise the
        permission-denied branches of admin-gated handlers:
        the user can log in (so they get past the
        ``require_login_or_redirect`` guard) but
        :func:`SecurityManager.check_permission` returns
        ``False`` for any admin-tier permission, so the handler
        redirects with a "permission denied" flash.
    """
    global _SEEDED_VIEWER
    if _SEEDED_VIEWER is not None:
        return _SEEDED_VIEWER

    ensure_app()
    ensure_shared_in_memory_db_pool()

    from werkzeug.security import generate_password_hash  # noqa: E402
    from automojo.pychestrate.core.orm import (  # noqa: E402
        PasswordHistory,
        User,
    )

    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    db_session = factory()
    try:
        existing = (
            db_session.query(User)
            .filter(User.login == E2E_VIEWER_LOGIN)
            .first()
        )
        if existing is not None:
            _SEEDED_VIEWER = SeededAdmin(
                user_id=str(existing.id),
                login=E2E_VIEWER_LOGIN,
                password=E2E_VIEWER_PASSWORD,
            )
            return _SEEDED_VIEWER

        user = User(
            id=uuid.uuid4(),
            first_name="E2E",
            last_name="Viewer",
            display_name="E2E Viewer",
            email=E2E_VIEWER_EMAIL,
            login=E2E_VIEWER_LOGIN,
            ownertag="e2e",
            status="active",
            roles="viewer",
            authtype="internal",
        )
        db_session.add(user)
        db_session.flush()

        password_hash = generate_password_hash(E2E_VIEWER_PASSWORD)
        history = PasswordHistory(
            user_id=user.id,
            password_hash=password_hash,
        )
        db_session.add(history)
        db_session.commit()

        _SEEDED_VIEWER = SeededAdmin(
            user_id=str(user.id),
            login=E2E_VIEWER_LOGIN,
            password=E2E_VIEWER_PASSWORD,
        )
        return _SEEDED_VIEWER
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def login_as(*, wsgi_app: Any, user: SeededAdmin) -> Dict[str, str]:
    """
        Convenience: POST credentials for an arbitrary seeded
        user, return the cookie jar. Raises on non-303
        responses.
    """
    response, cookies = login_via_post(
        wsgi_app=wsgi_app, login=user.login, password=user.password
    )
    if response.status_code != 303:
        raise AssertionError(
            "expected login POST for {} to 303 -- got {} ({})".format(
                user.login, response.status_code,
                response.text[:120]
            )
        )
    return cookies


__all__ = [
    "TEST_UI_COOKIE_SECRET",
    "TestAppHandle",
    "WsgiResponse",
    "ensure_app",
    "drive_request",
    "patch_utc_now_for_sqlite_tz_compat",
    "patch_legacy_pk_columns_for_sqlite",
    "ensure_shared_in_memory_db_pool",
    "E2E_ADMIN_LOGIN",
    "E2E_ADMIN_PASSWORD",
    "E2E_ADMIN_EMAIL",
    "SeededAdmin",
    "ensure_seeded_admin",
    "decode_session_cookie",
    "extract_csrf_token_from_cookies",
    "login_via_post",
    "logged_in_cookies",
    "PERMISSION_RESOURCES_MANAGE",
    "PERMISSION_USERS_MANAGE",
    "PERMISSION_VARIABLES_MANAGE",
    "grant_permissions_to_role",
    "ensure_seeded_admin_role",
    "E2E_VIEWER_LOGIN",
    "E2E_VIEWER_PASSWORD",
    "E2E_VIEWER_EMAIL",
    "ensure_seeded_viewer",
    "login_as",
]
