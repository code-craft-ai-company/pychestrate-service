"""
.. module:: tests.singlehost.pychestrate.webservice.phase10._e2e_harness
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared end-to-end test harness for the consumer UI
               (tier-1 + tier-2 + future tiers).

.. moduleauthor:: Code Craft AI LLC

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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import io
import re
import os
import sys
import tempfile
import urllib.parse
import uuid

from http.cookies import SimpleCookie
from typing import Any, Callable, Dict, List, Optional, Tuple

# Importing this module pulls every model side-effect import that
# registers tables on ``PychestratePhase1Base.metadata`` -- without
# this pull the auto-create-schema step would only build the
# Phase-1 core tables and the resources / projects FKs would
# dangle.
import ccai.pychestrate.webservice.extensions.bootstrap  # noqa: F401

from ccai.pychestrate.webservice.metadata import (
    RUNTIME_ENVIRONMENTS,
    SITE_DIRECTORIES,
    SITE_SHARED_GLOBALS,
)
from ccai.pychestrate.webservice.runtime_bootstrap import (
    RuntimeBootstrapConfig,
    bootstrap_runtime,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    register_config_routes,
)
from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    register_projects_routes,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    register_resources_routes,
)
from ccai.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
    csrf,
)
from ccai.pychestrate.webservice.webinterface.foundation.static_files import (
    register_static_routes,
)
from ccai.pychestrate.webservice.webinterface.foundation.templating import (
    build_jinja_environment,
    install_template_globals,
    discover_blueprint_template_paths,
    set_default_environment,
)
from ccai.pychestrate.webservice.webinterface.foundation.url_for import (
    get_registry_snapshot,
    install_url_for_global,
    register_endpoint,
)
from ccai.pychestrate.webservice.webinterface.site_shell.shell_document import (
    get_shell_template_search_path,
)
from ccai.webworks.wsgi.application import create_wsgi_application


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

# Snapshot of the runtime globals published during the one-time
# bootstrap. Some tests (e.g. runtime-bootstrap / infra-port suites)
# intentionally null ``SITE_SHARED_GLOBALS`` entries in their teardown;
# because ``ensure_app`` caches the app singleton and never re-publishes,
# a later test that acquires the cached app would otherwise find the
# globals cleared and 500 on any session-reading handler. The snapshot
# lets ``ensure_app`` re-assert the published globals on every call so
# the authenticated E2E flows are order-independent.
_RUNTIME_GLOBALS_SNAPSHOT: Optional[Dict[str, Any]] = None

# Snapshot of the url_for endpoint registry captured after the one-time
# app build. The infra-port suite's ``_reset_global_state`` clears the
# registry (and the default jinja environment) in teardown, so without a
# restore a later test that builds a URL or renders the site shell fails
# with a KeyError / TemplateNotFound. ``ensure_app`` restores both.
_URL_FOR_REGISTRY_SNAPSHOT: Optional[Dict[str, str]] = None


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
    # Site-shell template directory -- carries the shell document host
    # page (``site_shell/shell_document.html``) that authenticated
    # views render through. Production's ``install_web_ui_templating``
    # appends this; mirror it here so authenticated dashboards resolve
    # the shell template instead of raising TemplateNotFound (500).
    shell_template_path = get_shell_template_search_path()
    template_paths = list(template_paths) + [shell_template_path]
    environment = build_jinja_environment(
        template_search_paths=template_paths,
    )
    install_template_globals(environment=environment)
    set_default_environment(environment=environment)
    return


def _clear_thisapp_singleton_for_test() -> None:
    """
        Reset ``ccai.thisapp.wellknown.THISAPPLICATION_SINGLETON``
        to ``None`` so the upcoming ``establish_webapp_persona``
        call inside :mod:`app_pychestrate_main` does not bail with
        :class:`SemanticError`.

        ``testbase`` itself calls :func:`establish_app_persona` at
        run init -- that sets ``THISAPPLICATION_SINGLETON`` to a
        :class:`ThisApplication` instance. When the consumer-UI
        e2e harness later imports :mod:`app_pychestrate_main`,
        webworks' :func:`establish_webapp_persona` checks
        ``THISAPPLICATION_SINGLETON is None`` and raises if it
        already holds a :class:`ThisApplication`. The two
        personas are not compatible (testbase wants a generic
        app for results bookkeeping; webworks wants a
        :class:`WebApplication` for WSGI dispatch), so we clear
        the testbase-installed singleton just-in-time and let
        webworks install its own.

        Idempotent.
    """
    from ccai.thisapp import wellknown  # noqa: E402

    wellknown.SINGLETON_LOCK.acquire()
    try:
        wellknown.THISAPPLICATION_SINGLETON = None
    finally:
        wellknown.SINGLETON_LOCK.release()
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
        the persona, so we reuse that singleton. Before the
        import we clear the testbase-installed
        :class:`ThisApplication` singleton so webworks'
        :func:`establish_webapp_persona` does not fail its
        "singleton must be unset" precondition.
    """
    _clear_thisapp_singleton_for_test()
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


def _capture_runtime_globals_snapshot() -> None:
    """
        Record the runtime globals published by the one-time
        bootstrap so :func:`ensure_app` can re-assert them on later
        calls even after another test nulled them in teardown.
    """
    global _RUNTIME_GLOBALS_SNAPSHOT, _URL_FOR_REGISTRY_SNAPSHOT
    _RUNTIME_GLOBALS_SNAPSHOT = {
        "DATABASE_ENGINE": SITE_SHARED_GLOBALS.DATABASE_ENGINE,
        "DATABASE_SESSION_FACTORY": SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY,
        "UI_COOKIE_SECRET": SITE_SHARED_GLOBALS.UI_COOKIE_SECRET,
    }
    _URL_FOR_REGISTRY_SNAPSHOT = get_registry_snapshot()
    return


def _reassert_url_for_registry() -> None:
    """
        Re-populate the url_for endpoint registry from the snapshot if
        a prior test's teardown cleared it, so template ``url_for``
        lookups keep resolving.
    """
    if _URL_FOR_REGISTRY_SNAPSHOT is None:
        return
    current = get_registry_snapshot()
    if len(current) >= len(_URL_FOR_REGISTRY_SNAPSHOT):
        return
    for endpoint, pattern in _URL_FOR_REGISTRY_SNAPSHOT.items():
        register_endpoint(endpoint=endpoint, pattern=pattern)
    return


def _reassert_runtime_globals() -> None:
    """
        Re-publish the snapshotted runtime globals onto
        ``SITE_SHARED_GLOBALS``. Restores any entry a prior test's
        teardown cleared so the cached app's session-reading handlers
        keep working regardless of test execution order.
    """
    if _RUNTIME_GLOBALS_SNAPSHOT is None:
        return
    snap = _RUNTIME_GLOBALS_SNAPSHOT

    # Self-healing: capture the latest VALID value (so the snapshot
    # tracks the StaticPool engine the ``ensure_shared_in_memory_db_pool``
    # swap installs after the initial bootstrap), and restore only when
    # a prior test's teardown cleared the live global.
    if SITE_SHARED_GLOBALS.DATABASE_ENGINE is not None:
        snap["DATABASE_ENGINE"] = SITE_SHARED_GLOBALS.DATABASE_ENGINE
    elif snap["DATABASE_ENGINE"] is not None:
        SITE_SHARED_GLOBALS.DATABASE_ENGINE = snap["DATABASE_ENGINE"]

    if SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY is not None:
        snap["DATABASE_SESSION_FACTORY"] = (
            SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
        )
    elif snap["DATABASE_SESSION_FACTORY"] is not None:
        SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = (
            snap["DATABASE_SESSION_FACTORY"]
        )

    secret = SITE_SHARED_GLOBALS.UI_COOKIE_SECRET
    if secret is not None and len(secret) >= 32:
        snap["UI_COOKIE_SECRET"] = secret
    elif snap["UI_COOKIE_SECRET"] is not None:
        SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = snap["UI_COOKIE_SECRET"]
    return


def ensure_app() -> TestAppHandle:
    """
        Lazy module-level singleton: bootstrap the runtime + build
        the WSGI app once, return the cached handle on subsequent
        calls. Idempotent across tests + across test modules.

        On every call the bootstrap-published runtime globals are
        re-asserted onto ``SITE_SHARED_GLOBALS``, the default jinja
        environment is re-installed, and the url_for registry is
        restored -- so a prior test that nulled any of those in
        teardown cannot leave a later authenticated flow with an
        unconfigured session secret / session factory / templating
        environment.
    """
    global _APP_HANDLE
    if _APP_HANDLE is not None:
        _reassert_runtime_globals()
        _install_test_templating()
        _reassert_url_for_registry()
        return _APP_HANDLE
    kek_path = _write_test_kek_file()
    _bootstrap_runtime_for_tests(kek_file_path=kek_path)
    wsgi_app = _build_consumer_ui_test_app()
    _APP_HANDLE = TestAppHandle(
        wsgi_app=wsgi_app, kek_file_path=kek_path
    )
    _capture_runtime_globals_snapshot()
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
        no native tz support). Legacy code paths that compare a
        read-back ``expires_at`` (naive) against ``utc_now()``
        (timezone-aware) would raise ``TypeError``.

        Monkey-patch :func:`utc_now` on the core defaults module to
        return naive UTC. Idempotent.
    """
    from datetime import datetime, timezone  # noqa: E402
    from ccai.pychestrate.core import defaults as _defaults  # noqa: E402

    def naive_utc_now() -> datetime:
        rtnval = datetime.now(timezone.utc).replace(tzinfo=None)
        return rtnval

    if getattr(_defaults.utc_now, "__name__", "") != "naive_utc_now":
        _defaults.utc_now = naive_utc_now
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

    from ccai.pychestrate.core.orm import (  # noqa: E402
        PychestrateModelBase,
    )
    from ccai.pychestrate.webservice.persistence.schema import (  # noqa: E402
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

    from ccai.pychestrate.webservice.persistence.schema import (  # noqa: E402
        PychestratePhase1Base,
    )
    from ccai.pychestrate.core.orm import (  # noqa: E402
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


_TEST_PASSWORD_PEPPER: bytes = b"\x33" * 32


def ensure_pepper_for_tests() -> None:
    """
        Install a deterministic 32-byte password pepper.
        :func:`local_flow.hash_password` and
        :func:`local_flow.verify_local_credentials` both call
        :func:`get_active_pepper` and raise ``ConfigurationError``
        when no pepper has been set. The runtime bootstrap
        normally loads the pepper from operator config -- the
        test harness skips that step (no pepper source
        configured), so install one explicitly.

        Idempotent.
    """
    from ccai.pychestrate.webservice.secrets.secret_bytes import (  # noqa: E402
        SecretBytes,
    )
    from ccai.pychestrate.webservice.security.auth.pepper_loader import (  # noqa: E402
        get_active_pepper,
        set_active_pepper,
    )
    # NB: ``ccai.errors.exceptions.ConfigurationError``
    # inherits from ``BaseException`` (not ``Exception``), so a
    # plain ``except Exception`` would not catch the
    # "no pepper loaded" raise from ``get_active_pepper``.
    try:
        get_active_pepper()
        return
    except BaseException:
        pass
    set_active_pepper(pepper=SecretBytes(_TEST_PASSWORD_PEPPER))
    return


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


def _seed_user_pair(
        *,
        login: str, password: str, email: str, role_csv: str,
        first_name: str, last_name: str, display_name: str
    ) -> str:
    """
        Idempotently seed a (modern, legacy) user pair sharing
        the same UUID:

        * :class:`IdentityUser` + :class:`AuthLocalCredentials`
          on the modern Phase-1+ schema -- the auth flow
          (login / session / logout) AND the modern
          :func:`rbac_evaluator.check_permission` both read
          these.
        * :class:`User` on the legacy ``core.orm`` schema --
          still queried by some consumer-UI surfaces that
          have not yet migrated off the legacy
          :class:`UserManager` (``routes_users.py``,
          ``routes_secrets.py``, ``routes_sessions.py``).
          The ``roles`` CSV is no longer consulted by
          :meth:`check_permission` (modern RBAC reads
          ``rbac_role_bindings``), but the column is preserved
          on the legacy User row for any legacy queries that
          still examine it.

        :returns: The shared user_id (UUID string).
    """
    from ccai.pychestrate.webservice.security.auth import (  # noqa: E402
        local_flow,
    )
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityUser,
        UserStatus,
    )
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthLocalCredentials,
    )
    from ccai.pychestrate.core.orm import User  # noqa: E402

    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    db_session = factory()
    try:
        existing_modern = (
            db_session.query(IdentityUser)
            .filter(IdentityUser.login_name == login)
            .first()
        )
        if existing_modern is not None:
            return str(existing_modern.user_id)

        shared_user_id = uuid.uuid4()

        # Modern half: IdentityUser + AuthLocalCredentials. Hash
        # via ``local_flow.hash_password`` so the stored hash
        # matches what ``verify_local_credentials`` will check.
        modern_user = IdentityUser(
            user_id=shared_user_id,
            login_name=login,
            primary_email=email,
            display_name=display_name,
            status=UserStatus.ACTIVE,
            provisioning_source="local",
            external_id=None,
            timezone="UTC",
        )
        db_session.add(modern_user)
        db_session.flush()

        encoded_hash, algo_params = local_flow.hash_password(
            password=password
        )
        credentials = AuthLocalCredentials(
            user_id=shared_user_id,
            argon2id_hash=encoded_hash,
            algo_params=algo_params,
        )
        db_session.add(credentials)

        # Legacy half: User row carrying ``roles`` for the
        # consumer-UI's check_permission until RBAC migrates.
        legacy_user = User(
            id=shared_user_id,
            first_name=first_name,
            last_name=last_name,
            display_name=display_name,
            email=email,
            login=login,
            ownertag="e2e",
            status="active",
            roles=role_csv,
            authtype="internal",
        )
        db_session.add(legacy_user)
        db_session.commit()

        return str(shared_user_id)
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def ensure_seeded_admin() -> SeededAdmin:
    """
        Create an admin user with both modern (``identity_users``
        + ``auth_local_credentials``) and legacy (``user``)
        schema rows sharing the same UUID, and bind the modern
        ``"system-admin"`` role to it at SYSTEM scope.

        Every ``/admin/*`` page checks its permission server-side,
        and :func:`rbac_evaluator.check_permission` reads only
        ``rbac_role_bindings``, so without the binding the seeded
        "admin" would be refused like any other signed-in user.
    """
    global _SEEDED_ADMIN
    if _SEEDED_ADMIN is not None:
        return _SEEDED_ADMIN

    ensure_app()
    ensure_shared_in_memory_db_pool()
    ensure_pepper_for_tests()

    user_id = _seed_user_pair(
        login=E2E_ADMIN_LOGIN,
        password=E2E_ADMIN_PASSWORD,
        email=E2E_ADMIN_EMAIL,
        role_csv="admin",
        first_name="E2E",
        last_name="Admin",
        display_name="E2E Admin",
    )
    grant_role_to_user(user_id=user_id, role_name="system-admin")

    _SEEDED_ADMIN = SeededAdmin(
        user_id=user_id,
        login=E2E_ADMIN_LOGIN,
        password=E2E_ADMIN_PASSWORD,
    )
    return _SEEDED_ADMIN


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
        POST credentials to ``/login`` and return
        ``(response, cookies)`` -- ``cookies`` is empty on
        failure.

        Resets the modern :mod:`local_flow` backoff state at
        the start of each call. The backoff state machine
        accumulates failure counts per (login_name, source_ip);
        across a sweep of tests where some deliberately submit
        bad credentials, the bucket gets full and subsequent
        happy-path logins for the same user are then locked
        out with ``Too many recent failures``. The reset is a
        test-only seam and is idempotent.
    """
    from ccai.pychestrate.webservice.security.auth.local_flow import (  # noqa: E402
        reset_backoff_for_testing,
    )
    reset_backoff_for_testing()

    # The sign-in form is CSRF-gated: GET /login mints a token into
    # the anonymous session cookie and echoes it in the form. Do the
    # same round trip a browser does.
    form_cookies, csrf_token = fetch_login_form_token(wsgi_app=wsgi_app)
    body = (
        "username={username}&password={password}&csrf_token={token}".format(
            username=urllib.parse.quote_plus(login),
            password=urllib.parse.quote_plus(password),
            token=urllib.parse.quote_plus(csrf_token),
        )
    ).encode("utf-8")
    response = drive_request(
        wsgi_app=wsgi_app,
        method="POST",
        path="/login",
        body=body,
        cookies=form_cookies,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    cookies = response.collect_set_cookies()
    return (response, cookies)


_LOGIN_CSRF_PATTERN = re.compile(
    r'name="csrf_token"\s+value="([^"]*)"'
)


def fetch_login_form_token(*, wsgi_app: Any) -> Tuple[Dict[str, str], str]:
    """
        GET ``/login`` and return ``(cookies, csrf_token)`` -- the
        anonymous session cookie the form was minted against plus the
        token echoed in the hidden field.

        :param wsgi_app: The WSGI callable under test.

        :returns: Tuple of cookie dict and token string.
    """
    response = drive_request(wsgi_app=wsgi_app, method="GET", path="/login")
    cookies = response.collect_set_cookies()
    match = _LOGIN_CSRF_PATTERN.search(response.text)
    token = match.group(1) if match is not None else ""
    return (cookies, token)
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
# ``_require_permission_or_redirect`` calls. The values track the
# canonical ``system:<action>`` keys registered by the in-tree
# ``CorePermissionExtension`` pack -- tests catch any rename drift
# between the gates and the catalog.
PERMISSION_RESOURCES_MANAGE: str = "system:resources.manage"
PERMISSION_USERS_MANAGE: str = "system:users.write"
PERMISSION_VARIABLES_MANAGE: str = "system:rbac.admin"


def grant_role_to_user(
        *, user_id: str, role_name: str
    ) -> None:
    """
        Idempotently bind ``role_name`` to ``user_id`` at SYSTEM
        scope on the modern :mod:`security.rbac` schema.

        Looks up (or creates) the :class:`RbacRole` row matching
        ``role_name``, then inserts an
        :class:`RbacRoleBinding` with ``principal_kind=USER``
        and ``scope_kind=SYSTEM`` for the user. The role-to-
        permissions edges come from the in-tree
        :class:`SystemAdminRole` / :class:`AuditorRole` /
        ``Project*Role`` packs at evaluator time -- the
        evaluator reads the catalog produced by
        :func:`load_catalog_from_registry`, so the database
        only needs the role + binding rows seeded.

        :param user_id: User id (UUID string).
        :param role_name: Role name; must match a registered
                          :class:`RoleExtension` ``role_name``.
    """
    from ccai.pychestrate.webservice.security.rbac.models import (  # noqa: E402
        BindingScope,
        PrincipalKind,
        RbacRole,
        RbacRoleBinding,
        RoleSource,
    )
    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    db_session = factory()
    try:
        role = (
            db_session.query(RbacRole)
            .filter(RbacRole.role_name == role_name)
            .first()
        )
        if role is None:
            role = RbacRole(
                role_id=uuid.uuid4(),
                role_name=role_name,
                source=RoleSource.BUILTIN,
                source_name=role_name,
                description="seeded by e2e harness",
            )
            db_session.add(role)
            db_session.flush()

        principal_uuid = uuid.UUID(user_id)
        existing_binding = (
            db_session.query(RbacRoleBinding)
            .filter(
                RbacRoleBinding.role_id == role.role_id,
                RbacRoleBinding.principal_kind == PrincipalKind.USER,
                RbacRoleBinding.principal_id == principal_uuid,
                RbacRoleBinding.scope_kind == BindingScope.SYSTEM,
                RbacRoleBinding.scope_id.is_(None),
            )
            .first()
        )
        if existing_binding is None:
            binding = RbacRoleBinding(
                binding_id=uuid.uuid4(),
                role_id=role.role_id,
                principal_kind=PrincipalKind.USER,
                principal_id=principal_uuid,
                scope_kind=BindingScope.SYSTEM,
                scope_id=None,
                inherits_into_project=False,
            )
            db_session.add(binding)

        db_session.commit()
    finally:
        try:
            db_session.close()
        except Exception:
            pass
    return


def ensure_seeded_admin_role() -> None:
    """
        Idempotently bind the modern ``"system-admin"`` role to
        the seeded admin user at SYSTEM scope. The role's
        permission grants come from
        :class:`SystemAdminRole` (in-tree
        :class:`RoleExtension`); the evaluator reads them from
        the catalog at decision time, so this helper only
        seeds the role + binding rows.

        Also clears the rbac decision cache so a binding seeded
        mid-test cycle is observed by the next
        ``check_permission`` call. The cache is keyed by
        principal + permission_key + scope_id, and entries
        from a prior test (with no binding present) would
        otherwise mask the freshly seeded ALLOW.
    """
    from ccai.pychestrate.webservice.security.rbac import cache  # noqa: E402

    admin = ensure_seeded_admin()
    grant_role_to_user(
        user_id=admin.user_id, role_name="system-admin"
    )
    cache.invalidate_principal(principal_id=admin.user_id)
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
        ``require_login_or_redirect`` guard) but the modern
        :func:`rbac_evaluator.check_permission` returns
        ``allowed=False`` for any admin-tier permission (no
        :class:`RbacRoleBinding` was seeded for this user),
        so the handler redirects with a "permission denied"
        flash.
    """
    global _SEEDED_VIEWER
    if _SEEDED_VIEWER is not None:
        return _SEEDED_VIEWER

    ensure_app()
    ensure_shared_in_memory_db_pool()
    ensure_pepper_for_tests()

    user_id = _seed_user_pair(
        login=E2E_VIEWER_LOGIN,
        password=E2E_VIEWER_PASSWORD,
        email=E2E_VIEWER_EMAIL,
        role_csv="viewer",
        first_name="E2E",
        last_name="Viewer",
        display_name="E2E Viewer",
    )

    _SEEDED_VIEWER = SeededAdmin(
        user_id=user_id,
        login=E2E_VIEWER_LOGIN,
        password=E2E_VIEWER_PASSWORD,
    )
    return _SEEDED_VIEWER


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
    "fetch_login_form_token",
    "TEST_UI_COOKIE_SECRET",
    "TestAppHandle",
    "WsgiResponse",
    "ensure_app",
    "drive_request",
    "patch_utc_now_for_sqlite_tz_compat",
    "patch_legacy_pk_columns_for_sqlite",
    "ensure_shared_in_memory_db_pool",
    "ensure_pepper_for_tests",
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
    "grant_role_to_user",
    "ensure_seeded_admin_role",
    "E2E_VIEWER_LOGIN",
    "E2E_VIEWER_PASSWORD",
    "E2E_VIEWER_EMAIL",
    "ensure_seeded_viewer",
    "login_as",
]
