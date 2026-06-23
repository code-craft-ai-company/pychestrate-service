"""
.. module:: test_p12a2_test_mode_admin_seed_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the PYCHESTRATE_TEST_MODE admin-credential
               injection added to the runtime bootstrap.

.. moduleauthor:: Code Craft AI LLC

Test mode is OFF by default. When an operator sets
``PYCHESTRATE_TEST_MODE`` in a non-production environment the bootstrap
seeds / resets a known admin credential so the live-deploy test suites
authenticate deterministically. These tests cover:

* the env-driven loader (off by default; parsed when enabled),
* the production refusal gate,
* the missing-password gate,
* the shared :func:`seed_or_reset_test_admin` create-then-reset
  idempotency, and that a seeded credential actually authenticates
  through :func:`local_flow.verify_local_credentials`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.engine.base import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ccai import testbase
from ccai.errors.exceptions import ConfigurationError
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.security.auth.exceptions import (
    AuthenticationError,
)

from ccai.pychestrate.webservice import runtime_bootstrap
from ccai.pychestrate.webservice.extensions.bootstrap import (
    register_phase1_builtin_extensions,
)
from ccai.pychestrate.webservice.metadata import (
    RUNTIME_ENVIRONMENTS,
    SITE_SHARED_GLOBALS,
)
from ccai.pychestrate.webservice.runtime_bootstrap import (
    ENV_DATABASE_URL,
    ENV_KEK_FILE_PATH,
    ENV_KEK_ID,
    ENV_KEK_SOURCE,
    ENV_RUNTIME_ENVIRONMENT,
    ENV_TEST_ADMIN_DISPLAY_NAME,
    ENV_TEST_ADMIN_EMAIL,
    ENV_TEST_ADMIN_LOGIN,
    ENV_TEST_ADMIN_PASSWORD,
    ENV_TEST_MODE,
    RuntimeBootstrapConfig,
    bootstrap_runtime,
    load_config_from_environment,
)

from ccai.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from ccai.pychestrate.core.orm import (
    PychestrateModelBase as PychestrateLegacyCoreBase,
)
from ccai.pychestrate.webservice.identity.setup.testadmin_seeder import (
    seed_or_reset_test_admin,
)
from ccai.pychestrate.webservice.identity.users.models import (
    IdentityUser,
    UserStatus,
)
from ccai.pychestrate.webservice.security.auth import local_flow
from ccai.pychestrate.webservice.security.auth.models import (
    AuthLocalCredentials,
)
from ccai.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes


# ---------------------------------------------------------------------------
# Env snapshot / fixtures
# ---------------------------------------------------------------------------


_MANAGED_ENV_KEYS = (
    ENV_DATABASE_URL,
    ENV_RUNTIME_ENVIRONMENT,
    ENV_KEK_SOURCE,
    ENV_KEK_ID,
    ENV_KEK_FILE_PATH,
    ENV_TEST_MODE,
    ENV_TEST_ADMIN_LOGIN,
    ENV_TEST_ADMIN_EMAIL,
    ENV_TEST_ADMIN_PASSWORD,
    ENV_TEST_ADMIN_DISPLAY_NAME,
)

_TEST_PEPPER = SecretBytes(b"\x17" * 32)


class _EnvSnapshot:
    """
        Snapshot + restore of the env vars this module mutates so a
        test cannot leak ``os.environ`` state into a sibling.
    """

    def __init__(self) -> None:
        import os

        self._snapshot: Dict[str, Optional[str]] = {}
        for key in _MANAGED_ENV_KEYS:
            self._snapshot[key] = os.environ.get(key, None)
        return

    def restore(self) -> None:
        import os

        for key, value in self._snapshot.items():
            if value is None:
                if key in os.environ:
                    del os.environ[key]
            else:
                os.environ[key] = value
        return


def _set_env(*, mapping: Dict[str, str]) -> None:
    """
        Set exactly the keys in ``mapping`` and delete every other
        managed key so each loader test starts from a known baseline.

        :param mapping: Env vars to set for this test.

        :returns: None.
    """
    import os

    for key in _MANAGED_ENV_KEYS:
        if key in mapping:
            os.environ[key] = mapping[key]
        else:
            if key in os.environ:
                del os.environ[key]
    return


def _make_config(
        *,
        runtime_environment: str = RUNTIME_ENVIRONMENTS.TESTING,
        test_mode: bool = False,
        test_admin_login: Optional[str] = "admin",
        test_admin_email: Optional[str] = "admin@example.com",
        test_admin_password: Optional[str] = None,
        test_admin_display_name: Optional[str] = "Test Admin",
    ) -> RuntimeBootstrapConfig:
    """
        Build a :class:`RuntimeBootstrapConfig` for the gate tests with a
        dummy KEK file path (the phase patches never read it) and a
        memory database.

        :param runtime_environment: Runtime environment string.
        :param test_mode: Whether to enable test mode.
        :param test_admin_login: Seeded admin login.
        :param test_admin_email: Seeded admin email.
        :param test_admin_password: Seeded admin password.
        :param test_admin_display_name: Seeded admin display name.

        :returns: A configured :class:`RuntimeBootstrapConfig`.
    """
    rtnval = RuntimeBootstrapConfig(
        database_url="sqlite:///:memory:",
        runtime_environment=runtime_environment,
        kek_source="file",
        kek_id="test-kek-1",
        kek_file_path="/tmp/unused-kek",
        kek_env_var=None,
        password_pepper_source=None,
        password_pepper_file_path=None,
        password_pepper_env_var=None,
        ui_cookie_secret_source=None,
        ui_cookie_secret_file_path=None,
        ui_cookie_secret_env_var=None,
        auto_create_schema=False,
        sql_echo=False,
        test_mode=test_mode,
        test_admin_login=test_admin_login,
        test_admin_email=test_admin_email,
        test_admin_password=test_admin_password,
        test_admin_display_name=test_admin_display_name,
    )
    return rtnval


def _patch_phases() -> List[Any]:
    """
        Patch the five ``bootstrap_phaseN_runtime`` calls to no-ops so a
        gate test exercises only the seeding gate, not the real KEK /
        bus / scheduler wiring.

        :returns: The list of active patches for the caller to release.
    """
    class _FakeKek:
        kek_id: str = "test-kek-1"

    def fake_phase1(*, config: Any) -> Any:
        rtnval = _FakeKek()
        return rtnval

    def fake_phase_void(*, config: Any) -> None:
        return None

    plan: List[Tuple[str, Any]] = [
        ("bootstrap_phase1_runtime", fake_phase1),
        ("bootstrap_phase2_runtime", fake_phase_void),
        ("bootstrap_phase3_runtime", fake_phase_void),
        ("bootstrap_phase5_runtime", fake_phase_void),
        ("bootstrap_phase6_runtime", fake_phase_void),
    ]

    patches: List[Any] = []
    for attr_name, side_effect in plan:
        patch = create_module_patch(runtime_bootstrap, attr_name)
        mock = patch.activate()
        mock.configure(side_effect=side_effect)
        patches.append(patch)

    rtnval = patches
    return rtnval


def _release_phases(*, patches: List[Any]) -> None:
    for patch in patches:
        patch.deactivate()
    return


def _clear_globals() -> None:
    SITE_SHARED_GLOBALS.DATABASE_ENGINE = None
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = None
    return


def _build_memory_db() -> Tuple[Engine, Any]:
    """
        Build a single-connection in-memory SQLite engine with both the
        modern Phase-1 and the legacy core-ORM schemas created, plus a
        session factory bound to it. The ``StaticPool`` keeps every
        session on the same connection so ``:memory:`` data persists
        across sessions within the test.

        :returns: ``(engine, session_factory)``.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    PychestratePhase1Base.metadata.create_all(engine)
    PychestrateLegacyCoreBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    rtnval = (engine, session_factory)
    return rtnval


# ---------------------------------------------------------------------------
# load_config_from_environment — test-mode fields
# ---------------------------------------------------------------------------


def test_load_config_test_mode_defaults_off():
    """
    **Feature: runtime test-mode admin injection**
    **Property: With no PYCHESTRATE_TEST_MODE in the environment the
    loader resolves test_mode=False and no admin password. Test mode
    must never engage unless the operator explicitly opts in.**
    """
    snapshot = _EnvSnapshot()
    try:
        _set_env(mapping={
            ENV_DATABASE_URL: "sqlite:///:memory:",
            ENV_RUNTIME_ENVIRONMENT: RUNTIME_ENVIRONMENTS.DEVELOPMENT,
            ENV_KEK_SOURCE: "file",
            ENV_KEK_ID: "k-1",
            ENV_KEK_FILE_PATH: "/tmp/x",
        })
        config = load_config_from_environment()
        testbase.assert_equal(config.test_mode, False)
        testbase.assert_equal(config.test_admin_password, None)
    finally:
        snapshot.restore()
    return


def test_load_config_test_mode_parses_enabled_with_admin_fields():
    """
    **Feature: runtime test-mode admin injection**
    **Property: When PYCHESTRATE_TEST_MODE=true and the admin vars are
    present the loader lands test_mode=True plus the login / email /
    password / display-name onto the matching config fields.**
    """
    snapshot = _EnvSnapshot()
    try:
        _set_env(mapping={
            ENV_DATABASE_URL: "sqlite:///:memory:",
            ENV_RUNTIME_ENVIRONMENT: RUNTIME_ENVIRONMENTS.TESTING,
            ENV_KEK_SOURCE: "file",
            ENV_KEK_ID: "k-1",
            ENV_KEK_FILE_PATH: "/tmp/x",
            ENV_TEST_MODE: "true",
            ENV_TEST_ADMIN_LOGIN: "qa-admin",
            ENV_TEST_ADMIN_EMAIL: "qa@example.com",
            ENV_TEST_ADMIN_PASSWORD: "QaPassw0rd!!",
            ENV_TEST_ADMIN_DISPLAY_NAME: "QA Admin",
        })
        config = load_config_from_environment()
        testbase.assert_equal(config.test_mode, True)
        testbase.assert_equal(config.test_admin_login, "qa-admin")
        testbase.assert_equal(config.test_admin_email, "qa@example.com")
        testbase.assert_equal(config.test_admin_password, "QaPassw0rd!!")
        testbase.assert_equal(config.test_admin_display_name, "QA Admin")
    finally:
        snapshot.restore()
    return


def test_load_config_test_mode_admin_login_defaults_to_admin():
    """
    **Feature: runtime test-mode admin injection**
    **Property: When test mode is on but the login is not overridden the
    loader resolves the documented default login "admin" and email
    "admin@example.com" rather than None.**
    """
    snapshot = _EnvSnapshot()
    try:
        _set_env(mapping={
            ENV_DATABASE_URL: "sqlite:///:memory:",
            ENV_RUNTIME_ENVIRONMENT: RUNTIME_ENVIRONMENTS.TESTING,
            ENV_KEK_SOURCE: "file",
            ENV_KEK_ID: "k-1",
            ENV_KEK_FILE_PATH: "/tmp/x",
            ENV_TEST_MODE: "1",
            ENV_TEST_ADMIN_PASSWORD: "AnyPassw0rd!!",
        })
        config = load_config_from_environment()
        testbase.assert_equal(config.test_admin_login, "admin")
        testbase.assert_equal(
            config.test_admin_email, "admin@example.com"
        )
    finally:
        snapshot.restore()
    return


# ---------------------------------------------------------------------------
# bootstrap_runtime — seeding gate
# ---------------------------------------------------------------------------


def test_bootstrap_refuses_test_mode_in_production():
    """
    **Feature: runtime test-mode admin injection**
    **Property: Setting test_mode=True with a production runtime
    environment raises ConfigurationError. Test mode injects a backdoor
    admin from the environment and must never run on a production
    instance.**
    """
    _clear_globals()
    patches = _patch_phases()
    raised = False
    try:
        try:
            bootstrap_runtime(config=_make_config(
                runtime_environment=RUNTIME_ENVIRONMENTS.PRODUCTION,
                test_mode=True,
                test_admin_password="DoesNotMatter!!",
            ))
        except ConfigurationError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        _release_phases(patches=patches)
        _clear_globals()
    return


def test_bootstrap_test_mode_requires_a_password():
    """
    **Feature: runtime test-mode admin injection**
    **Property: test_mode=True in a non-production environment with no
    admin password raises ConfigurationError rather than seeding an
    admin with an empty / unknown credential.**
    """
    _clear_globals()
    patches = _patch_phases()
    raised = False
    try:
        try:
            bootstrap_runtime(config=_make_config(
                runtime_environment=RUNTIME_ENVIRONMENTS.TESTING,
                test_mode=True,
                test_admin_password=None,
            ))
        except ConfigurationError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        _release_phases(patches=patches)
        _clear_globals()
    return


def test_bootstrap_test_mode_off_does_not_raise_without_password():
    """
    **Feature: runtime test-mode admin injection**
    **Property: With test_mode=False the missing-password guard never
    fires -- the default boot path is unaffected by the new gate.**
    """
    _clear_globals()
    patches = _patch_phases()
    try:
        result = bootstrap_runtime(config=_make_config(
            runtime_environment=RUNTIME_ENVIRONMENTS.TESTING,
            test_mode=False,
            test_admin_password=None,
        ))
        testbase.assert_true(result is not None)
    finally:
        _release_phases(patches=patches)
        _clear_globals()
    return


# ---------------------------------------------------------------------------
# seed_or_reset_test_admin — create / reset behavior
# ---------------------------------------------------------------------------


def test_seed_creates_active_admin_with_credentials_on_fresh_db():
    """
    **Feature: runtime test-mode admin injection**
    **Property: On a fresh database seed_or_reset_test_admin reports
    action "created" and writes an ACTIVE identity_users row plus a
    matching auth_local_credentials row.**
    """
    register_phase1_builtin_extensions()
    set_active_pepper(pepper=_TEST_PEPPER)
    engine, session_factory = _build_memory_db()
    try:
        result = seed_or_reset_test_admin(
            session_factory=session_factory,
            login="seed-create",
            email="seed-create@example.com",
            password="CreatePassw0rd!!",
            display_name="Seed Create",
        )
        testbase.assert_equal(result.action, "created")

        db_session = session_factory()
        try:
            user = (
                db_session.query(IdentityUser)
                .filter(IdentityUser.login_name == "seed-create")
                .first()
            )
            testbase.assert_true(user is not None)
            testbase.assert_equal(user.status, UserStatus.ACTIVE)

            credentials = (
                db_session.query(AuthLocalCredentials)
                .filter(AuthLocalCredentials.user_id == user.user_id)
                .first()
            )
            testbase.assert_true(credentials is not None)
        finally:
            db_session.close()
    finally:
        reset_active_pepper_for_testing()
        engine.dispose()
    return


def test_seed_is_idempotent_and_resets_existing_admin_password():
    """
    **Feature: runtime test-mode admin injection**
    **Property: A second seed call for the same login reports action
    "reset", keeps the same user_id, and the NEW password verifies
    while the OLD password no longer does -- the credential is
    deterministically reset, not duplicated.**
    """
    register_phase1_builtin_extensions()
    set_active_pepper(pepper=_TEST_PEPPER)
    local_flow.reset_backoff_for_testing()
    engine, session_factory = _build_memory_db()
    try:
        first = seed_or_reset_test_admin(
            session_factory=session_factory,
            login="seed-reset",
            email="seed-reset@example.com",
            password="FirstPassw0rd!!",
            display_name="Seed Reset",
        )
        testbase.assert_equal(first.action, "created")

        second = seed_or_reset_test_admin(
            session_factory=session_factory,
            login="seed-reset",
            email="seed-reset@example.com",
            password="SecondPassw0rd!!",
            display_name="Seed Reset",
        )
        testbase.assert_equal(second.action, "reset")
        testbase.assert_equal(second.user_id, first.user_id)

        # The new password authenticates.
        verify_session = session_factory()
        try:
            success = local_flow.verify_local_credentials(
                login_name="seed-reset",
                password="SecondPassw0rd!!",
                mfa_code=None,
                source_ip="127.0.0.1",
                db_session=verify_session,
            )
            testbase.assert_equal(success.user_id, second.user_id)
        finally:
            verify_session.close()

        # The old password no longer authenticates.
        local_flow.reset_backoff_for_testing()
        reject_session = session_factory()
        rejected = False
        try:
            local_flow.verify_local_credentials(
                login_name="seed-reset",
                password="FirstPassw0rd!!",
                mfa_code=None,
                source_ip="127.0.0.2",
                db_session=reject_session,
            )
        except AuthenticationError:
            rejected = True
        finally:
            reject_session.close()
        testbase.assert_equal(rejected, True)
    finally:
        local_flow.reset_backoff_for_testing()
        reset_active_pepper_for_testing()
        engine.dispose()
    return


def test_seed_requires_a_non_empty_password():
    """
    **Feature: runtime test-mode admin injection**
    **Property: seed_or_reset_test_admin raises ValueError when handed an
    empty password rather than writing an unusable credential.**
    """
    set_active_pepper(pepper=_TEST_PEPPER)
    engine, session_factory = _build_memory_db()
    raised = False
    try:
        try:
            seed_or_reset_test_admin(
                session_factory=session_factory,
                login="seed-empty",
                email="seed-empty@example.com",
                password="",
                display_name="Seed Empty",
            )
        except ValueError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        reset_active_pepper_for_testing()
        engine.dispose()
    return
