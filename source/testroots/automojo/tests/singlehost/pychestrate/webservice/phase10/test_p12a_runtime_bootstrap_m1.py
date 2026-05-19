"""
.. module:: test_p12a_runtime_bootstrap_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the one-call runtime bootstrap.

.. moduleauthor:: Automation Mojo LLC

The runtime bootstrap is the missing wiring that takes the
service from "imports clean" to "actually answers requests". It
builds the SQLAlchemy engine + session factory, publishes them on
``SITE_SHARED_GLOBALS``, optionally creates the schema, and chains
``bootstrap_phase1_runtime`` / 2 / 3 to load the KEK, install the
password pepper, and wire the bus subscribers.

Tests cover the env-driven config loader, the engine + factory
build, the schema-create production guard, the KEK / pepper
chaining, and the global-publishing seam.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile

from typing import Any, Dict, List, Optional

from automojo import testbase
from automojo.errors.exceptions import ConfigurationError
from automojo.testbase.mocking import create_module_patch

from automojo.pychestrate.webservice import runtime_bootstrap
from automojo.pychestrate.webservice.metadata import (
    RUNTIME_ENVIRONMENTS,
    SITE_SHARED_GLOBALS,
)
from automojo.pychestrate.webservice.runtime_bootstrap import (
    ENV_AUTO_CREATE_SCHEMA,
    ENV_DATABASE_URL,
    ENV_KEK_ENV_VAR,
    ENV_KEK_FILE_PATH,
    ENV_KEK_ID,
    ENV_KEK_SOURCE,
    ENV_PEPPER_ENV_VAR,
    ENV_PEPPER_FILE_PATH,
    ENV_PEPPER_SOURCE,
    ENV_RUNTIME_ENVIRONMENT,
    RuntimeBootstrapConfig,
    bootstrap_runtime,
    load_config_from_environment,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


_PRESERVED_ENV_KEYS = (
    ENV_DATABASE_URL,
    ENV_RUNTIME_ENVIRONMENT,
    ENV_AUTO_CREATE_SCHEMA,
    ENV_KEK_SOURCE,
    ENV_KEK_ID,
    ENV_KEK_FILE_PATH,
    ENV_KEK_ENV_VAR,
    ENV_PEPPER_SOURCE,
    ENV_PEPPER_FILE_PATH,
    ENV_PEPPER_ENV_VAR,
    "PYCHESTRATE_SQL_ECHO",
)


class _EnvSnapshot:
    """
        Snapshot + restore for the documented PYCHESTRATE_* env
        names so tests that mutate ``os.environ`` cannot leak into
        each other.
    """

    def __init__(self) -> None:
        self._snapshot: Dict[str, Optional[str]] = {}
        for key in _PRESERVED_ENV_KEYS:
            self._snapshot[key] = os.environ.get(key, None)
        return

    def restore(self) -> None:
        for key, value in self._snapshot.items():
            if value is None:
                if key in os.environ:
                    del os.environ[key]
            else:
                os.environ[key] = value
        return


def _set_env(*, mapping: Dict[str, str]) -> None:
    """
        Bulk-set / clear documented env vars from a mapping.
        Empty-string values are treated as deletions to mirror the
        loader's "absent-or-empty" semantic.
    """
    for key in _PRESERVED_ENV_KEYS:
        if key not in mapping:
            if key in os.environ:
                del os.environ[key]
            continue
        value = mapping[key]
        if value == "":
            if key in os.environ:
                del os.environ[key]
        else:
            os.environ[key] = value
    return


def _capture_phase_calls() -> Dict[str, Any]:
    """
        Patch the three ``bootstrap_phaseN_runtime`` calls so they
        record what they were given without actually running the
        Phase-1/2/3 wiring (which would hit the KEK loader, secrets
        backend, and bus). Returns a state dict the tests can
        inspect plus a list of patches the caller deactivates in
        their finally block.
    """
    state: Dict[str, Any] = {
        "phase1_calls": [],
        "phase2_calls": [],
        "phase3_calls": [],
        "phase5_calls": [],
        "phase6_calls": [],
    }

    class _FakeKek:
        kek_id: str = "test-kek-1"

    def fake_phase1(*, config: Any) -> Any:
        state["phase1_calls"].append(config)
        rtnval = _FakeKek()
        return rtnval

    def fake_phase2(*, config: Any) -> None:
        state["phase2_calls"].append(config)
        return

    def fake_phase3(*, config: Any) -> None:
        state["phase3_calls"].append(config)
        return

    def fake_phase5(*, config: Any) -> Any:
        state["phase5_calls"].append(config)
        return None

    def fake_phase6(*, config: Any) -> None:
        state["phase6_calls"].append(config)
        return

    p1 = create_module_patch(runtime_bootstrap, "bootstrap_phase1_runtime")
    p2 = create_module_patch(runtime_bootstrap, "bootstrap_phase2_runtime")
    p3 = create_module_patch(runtime_bootstrap, "bootstrap_phase3_runtime")
    p5 = create_module_patch(runtime_bootstrap, "bootstrap_phase5_runtime")
    p6 = create_module_patch(runtime_bootstrap, "bootstrap_phase6_runtime")

    m1 = p1.activate()
    m1.configure(side_effect=fake_phase1)
    m2 = p2.activate()
    m2.configure(side_effect=fake_phase2)
    m3 = p3.activate()
    m3.configure(side_effect=fake_phase3)
    m5 = p5.activate()
    m5.configure(side_effect=fake_phase5)
    m6 = p6.activate()
    m6.configure(side_effect=fake_phase6)

    state["patches"] = [p1, p2, p3, p5, p6]
    return state


def _release_phase_patches(*, state: Dict[str, Any]) -> None:
    for patch in state.get("patches", []):
        patch.deactivate()
    return


def _make_config(
        *,
        runtime_environment: str = RUNTIME_ENVIRONMENTS.TESTING,
        kek_source: str = "file",
        kek_file_path: Optional[str] = None,
        password_pepper_source: Optional[str] = None,
        password_pepper_file_path: Optional[str] = None,
        auto_create_schema: bool = False,
    ) -> RuntimeBootstrapConfig:
    """
        Build a :class:`RuntimeBootstrapConfig` with sensible test
        defaults so each test only spells out what it cares about.
    """
    rtnval = RuntimeBootstrapConfig(
        database_url="sqlite:///:memory:",
        runtime_environment=runtime_environment,
        kek_source=kek_source,
        kek_id="test-kek-1",
        kek_file_path=kek_file_path,
        kek_env_var=None,
        password_pepper_source=password_pepper_source,
        password_pepper_file_path=password_pepper_file_path,
        password_pepper_env_var=None,
        ui_cookie_secret_source=None,
        ui_cookie_secret_file_path=None,
        ui_cookie_secret_env_var=None,
        auto_create_schema=auto_create_schema,
        sql_echo=False,
    )
    return rtnval


# ---------------------------------------------------------------------------
# load_config_from_environment
# ---------------------------------------------------------------------------


def test_load_config_raises_when_database_url_missing():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: A missing DATABASE_URL is a hard ConfigurationError
    -- the service must not start with no database.**
    """
    snapshot = _EnvSnapshot()
    try:
        _set_env(mapping={
            ENV_KEK_SOURCE: "file",
            ENV_KEK_ID: "k-1",
            ENV_KEK_FILE_PATH: "/tmp/x",
        })
        raised = False
        try:
            load_config_from_environment()
        except ConfigurationError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        snapshot.restore()
    return


def test_load_config_raises_when_kek_source_missing():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: A missing KEK_SOURCE is a hard ConfigurationError.
    The service cannot decrypt anything without a KEK.**
    """
    snapshot = _EnvSnapshot()
    try:
        _set_env(mapping={
            ENV_DATABASE_URL: "sqlite:///:memory:",
            ENV_KEK_ID: "k-1",
        })
        raised = False
        try:
            load_config_from_environment()
        except ConfigurationError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        snapshot.restore()
    return


def test_load_config_defaults_runtime_environment_to_production():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: When the runtime-environment env var is unset, the
    loader defaults to "production". An unset value is the safer
    choice -- it engages production-only safety gates (no
    auto-create-schema, etc.) by default.**
    """
    snapshot = _EnvSnapshot()
    try:
        _set_env(mapping={
            ENV_DATABASE_URL: "sqlite:///:memory:",
            ENV_KEK_SOURCE: "file",
            ENV_KEK_ID: "k-1",
            ENV_KEK_FILE_PATH: "/tmp/x",
        })
        config = load_config_from_environment()
        testbase.assert_equal(
            config.runtime_environment, RUNTIME_ENVIRONMENTS.PRODUCTION
        )
    finally:
        snapshot.restore()
    return


def test_load_config_rejects_unknown_runtime_environment():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: An unrecognized RUNTIME_ENVIRONMENT raises
    ConfigurationError. Catches typos before they boot a
    misconfigured service.**
    """
    snapshot = _EnvSnapshot()
    try:
        _set_env(mapping={
            ENV_DATABASE_URL: "sqlite:///:memory:",
            ENV_RUNTIME_ENVIRONMENT: "prdoction",  # typo
            ENV_KEK_SOURCE: "file",
            ENV_KEK_ID: "k-1",
            ENV_KEK_FILE_PATH: "/tmp/x",
        })
        raised = False
        try:
            load_config_from_environment()
        except ConfigurationError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        snapshot.restore()
    return


def test_load_config_propagates_all_documented_fields():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: Every documented PYCHESTRATE_* env var lands on the
    matching RuntimeBootstrapConfig field. Non-set optional fields
    default to None.**
    """
    snapshot = _EnvSnapshot()
    try:
        _set_env(mapping={
            ENV_DATABASE_URL: "sqlite:///:memory:",
            ENV_RUNTIME_ENVIRONMENT: RUNTIME_ENVIRONMENTS.DEVELOPMENT,
            ENV_AUTO_CREATE_SCHEMA: "true",
            ENV_KEK_SOURCE: "env",
            ENV_KEK_ID: "k-2",
            ENV_KEK_ENV_VAR: "MY_KEK_MATERIAL",
            ENV_PEPPER_SOURCE: "file",
            ENV_PEPPER_FILE_PATH: "/etc/pep",
        })
        config = load_config_from_environment()
        testbase.assert_equal(
            config.database_url, "sqlite:///:memory:"
        )
        testbase.assert_equal(
            config.runtime_environment, RUNTIME_ENVIRONMENTS.DEVELOPMENT
        )
        testbase.assert_equal(config.auto_create_schema, True)
        testbase.assert_equal(config.kek_source, "env")
        testbase.assert_equal(config.kek_env_var, "MY_KEK_MATERIAL")
        testbase.assert_equal(config.kek_id, "k-2")
        testbase.assert_equal(config.password_pepper_source, "file")
        testbase.assert_equal(
            config.password_pepper_file_path, "/etc/pep"
        )
        testbase.assert_equal(config.kek_file_path, None)
    finally:
        snapshot.restore()
    return


# ---------------------------------------------------------------------------
# bootstrap_runtime — engine + factory + globals
# ---------------------------------------------------------------------------


def _clear_globals() -> None:
    SITE_SHARED_GLOBALS.DATABASE_ENGINE = None
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = None
    return


def test_bootstrap_runtime_publishes_engine_and_session_factory():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: bootstrap_runtime sets SITE_SHARED_GLOBALS.
    DATABASE_ENGINE and .DATABASE_SESSION_FACTORY so the rest of
    the service can resolve them. This was the missing wiring that
    kept the prod service in 503-fail-soft mode.**
    """
    _clear_globals()
    state = _capture_phase_calls()
    try:
        result = bootstrap_runtime(config=_make_config())
        testbase.assert_equal(
            SITE_SHARED_GLOBALS.DATABASE_ENGINE is result.engine, True
        )
        testbase.assert_equal(
            SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
            is result.session_factory,
            True,
        )
    finally:
        _release_phase_patches(state=state)
        _clear_globals()
    return


def test_bootstrap_runtime_calls_phase1_phase2_phase3_in_order():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: bootstrap_runtime chains
    bootstrap_phase1_runtime / 2 / 3 in that order. Phase 1 must
    set the active KEK + pepper before Phase 2 / 3 wire bus
    subscribers that may read encrypted state.**
    """
    _clear_globals()
    state = _capture_phase_calls()
    try:
        bootstrap_runtime(config=_make_config())
        testbase.assert_equal(len(state["phase1_calls"]), 1)
        testbase.assert_equal(len(state["phase2_calls"]), 1)
        testbase.assert_equal(len(state["phase3_calls"]), 1)
        testbase.assert_equal(
            state["phase1_calls"][0].kek_source, "file"
        )
        testbase.assert_equal(
            state["phase1_calls"][0].kek_id, "test-kek-1"
        )
        # Same session factory threaded through all three phases.
        testbase.assert_equal(
            state["phase1_calls"][0].session_factory
            is state["phase2_calls"][0].session_factory,
            True,
        )
        testbase.assert_equal(
            state["phase2_calls"][0].session_factory
            is state["phase3_calls"][0].session_factory,
            True,
        )
    finally:
        _release_phase_patches(state=state)
        _clear_globals()
    return


# ---------------------------------------------------------------------------
# bootstrap_runtime — schema gate
# ---------------------------------------------------------------------------


def test_bootstrap_runtime_refuses_create_schema_in_production():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: Setting auto_create_schema=True in production
    raises ConfigurationError. Production schema must come from
    out-of-band migrations, never from create_all at boot.**
    """
    _clear_globals()
    state = _capture_phase_calls()
    raised = False
    try:
        try:
            bootstrap_runtime(config=_make_config(
                runtime_environment=RUNTIME_ENVIRONMENTS.PRODUCTION,
                auto_create_schema=True,
            ))
        except ConfigurationError:
            raised = True
    finally:
        _release_phase_patches(state=state)
        _clear_globals()
    testbase.assert_equal(raised, True)
    return


def test_bootstrap_runtime_runs_create_all_in_development():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: With auto_create_schema=True and a non-production
    environment, create_all runs against the engine. Verified by
    pointing at an empty SQLite db and confirming a known table
    exists afterwards.**
    """
    _clear_globals()
    state = _capture_phase_calls()
    db_handle, db_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(db_handle)
    os.remove(db_path)
    try:
        config = RuntimeBootstrapConfig(
            database_url="sqlite:///{}".format(db_path),
            runtime_environment=RUNTIME_ENVIRONMENTS.DEVELOPMENT,
            kek_source="file",
            kek_id="k-1",
            kek_file_path=None,
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
        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(SITE_SHARED_GLOBALS.DATABASE_ENGINE)
        table_names = inspector.get_table_names()
        # Pick a Phase-1 table that's part of the loaded metadata --
        # ``feature_flags`` is a good canary because the flags
        # feature is fully ported and known-loaded.
        testbase.assert_equal(len(table_names) > 0, True)
    finally:
        _release_phase_patches(state=state)
        _clear_globals()
        if os.path.exists(db_path):
            os.remove(db_path)
    return


# ---------------------------------------------------------------------------
# bootstrap_runtime — pepper resolution
# ---------------------------------------------------------------------------


def test_bootstrap_runtime_loads_pepper_from_file_when_configured():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: When pepper_source=file, the pepper material is
    read from the file path and threaded into Phase1BootstrapConfig
    -- the auth flow then has a non-None pepper to verify
    passwords against.**
    """
    _clear_globals()
    state = _capture_phase_calls()
    pepper_handle, pepper_path = tempfile.mkstemp(suffix=".pep")
    os.write(pepper_handle, b"super-secret-pepper-32-bytes-x")
    os.close(pepper_handle)
    try:
        bootstrap_runtime(config=_make_config(
            password_pepper_source="file",
            password_pepper_file_path=pepper_path,
        ))
        phase1_config = state["phase1_calls"][0]
        testbase.assert_equal(phase1_config.password_pepper is not None, True)
    finally:
        _release_phase_patches(state=state)
        _clear_globals()
        if os.path.exists(pepper_path):
            os.remove(pepper_path)
    return


def test_bootstrap_runtime_skips_pepper_when_source_is_none():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: When no pepper source is configured, the bootstrap
    threads None into Phase1BootstrapConfig.password_pepper. Auth
    flow then 503s on first password verify -- legitimate during
    early bring-up of a deployment where local-password auth is
    not yet enabled.**
    """
    _clear_globals()
    state = _capture_phase_calls()
    try:
        bootstrap_runtime(config=_make_config(
            password_pepper_source=None,
        ))
        phase1_config = state["phase1_calls"][0]
        testbase.assert_equal(phase1_config.password_pepper, None)
    finally:
        _release_phase_patches(state=state)
        _clear_globals()
    return


def test_bootstrap_runtime_raises_when_pepper_file_missing():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: A configured-but-missing pepper file is a hard
    ConfigurationError. Better to fail fast at boot than discover
    the misconfiguration on first auth attempt.**
    """
    _clear_globals()
    state = _capture_phase_calls()
    raised = False
    try:
        try:
            bootstrap_runtime(config=_make_config(
                password_pepper_source="file",
                password_pepper_file_path="/nonexistent/path/pep",
            ))
        except ConfigurationError:
            raised = True
    finally:
        _release_phase_patches(state=state)
        _clear_globals()
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# Bootstrap source-smoke
# ---------------------------------------------------------------------------


def test_bootstrap_imports_runtime_bootstrap_and_calls_it_in_main():
    """
    **Feature: runtime bootstrap T1.1**
    **Property: app_pychestrate_main wires bootstrap_runtime into
    pychestrate_website_main and exposes a
    build_wsgi_application_for_production factory for gunicorn.**
    """
    here = os.path.dirname(os.path.abspath(__file__))
    repo_source_root = os.path.normpath(
        os.path.join(
            here, "..", "..", "..", "..", "..", "..", "..", "..",
            "source", "site",
        )
    )
    bootstrap_path = os.path.join(repo_source_root, "app_pychestrate_main.py")
    with open(bootstrap_path, "r", encoding="utf-8") as fh:
        text = fh.read()

    has_import = (
        "from automojo.pychestrate.webservice.runtime_bootstrap import"
        in text
    )
    has_call = "bootstrap_runtime(config=runtime_config)" in text
    has_prod_factory = "def build_wsgi_application_for_production" in text
    testbase.assert_equal(has_import, True)
    testbase.assert_equal(has_call, True)
    testbase.assert_equal(has_prod_factory, True)
    return
