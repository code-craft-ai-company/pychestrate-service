"""
.. module:: test_local_flow
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-authentication local_flow + pluggable hasher + backoff.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid as uuidmod

from automojo import testbase

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.core.defaults import utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
    register_factory_implementation,
    reset_registry_for_testing,
    unregister_factory_implementation,
)
from automojo.pychestrate.webservice.identity.users.models import IdentityUser, UserStatus
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.exceptions import AuthenticationError
from automojo.pychestrate.webservice.security.auth.factories.password_hasher import (
    EncodedHash,
    PasswordHasherProtocol,
    resolve_hasher_for_hashing,
    resolve_hasher_for_verifying,
)
from automojo.pychestrate.webservice.security.auth.factories.stdlib_scrypt_hasher import (
    SCRYPT_ALGORITHM_NAME,
    StdlibScryptPasswordHasher,
)
from automojo.pychestrate.webservice.security.auth.local_flow import (
    hash_password,
    reset_backoff_for_testing,
    verify_local_credentials,
)
from automojo.pychestrate.webservice.security.auth.models import AuthLocalCredentials
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _install_pepper() -> None:
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"phase1-test-pepper-material"))
    reset_backoff_for_testing()
    return


def _insert_user_with_credentials(
        *,
        session,
        password: str,
        status: UserStatus = UserStatus.ACTIVE
    ) -> str:
    user_id = str(uuidmod.uuid4())
    session.add(IdentityUser(
        user_id=user_id,
        login_name="verifier-user",
        primary_email="verifier@example.com",
        display_name="Verifier",
        status=status,
        provisioning_source="local",
        external_id=None,
        timezone="UTC",
    ))
    session.flush()

    hash_bytes, params = hash_password(password=password)
    session.add(AuthLocalCredentials(
        user_id=user_id,
        argon2id_hash=hash_bytes,
        algo_params=params,
        must_rotate_after=None,
        last_changed_at=utc_now(),
    ))
    session.commit()
    return user_id


def test_stdlib_scrypt_hasher_registered_by_default():
    """
    **Feature: 1-authentication + 0.5-extension-host**
    **Property: reset_phase1_runtime() registers StdlibScryptPasswordHasher
    as the default password_hasher implementation.**
    """
    reset_phase1_runtime()
    impls = list_factory_implementations(factory_protocol_name="password_hasher")
    testbase.assert_equal(len(impls) >= 1, True)
    testbase.assert_equal(StdlibScryptPasswordHasher in impls, True)
    return


def test_resolve_hasher_for_hashing_returns_registered():
    """
    **Feature: 1-authentication**
    **Property: resolve_hasher_for_hashing returns the stdlib reference
    when no other hasher is registered.**
    """
    reset_phase1_runtime()
    hasher = resolve_hasher_for_hashing()
    testbase.assert_equal(hasher.algorithm_name(), SCRYPT_ALGORITHM_NAME)
    return


def test_resolve_hasher_for_hashing_raises_when_empty():
    """
    **Feature: 1-authentication**
    **Property: resolve_hasher_for_hashing raises ConfigurationError when
    no hasher is registered.**
    """
    reset_registry_for_testing()
    raised = False
    try:
        resolve_hasher_for_hashing()
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    reset_phase1_runtime()
    return


def test_stdlib_scrypt_round_trip():
    """
    **Feature: 1-authentication**
    **Property: StdlibScryptPasswordHasher.hash_password produces an
    encoded hash that verify_password accepts for the same password
    and rejects for a different one.**
    """
    _install_pepper()
    reset_phase1_runtime()

    pepper = SecretBytes(b"phase1-test-pepper-material")
    encoded = StdlibScryptPasswordHasher.hash_password(
        password="correct-horse-battery-staple",
        pepper=pepper,
    )
    testbase.assert_equal(encoded.algorithm_name, SCRYPT_ALGORITHM_NAME)
    testbase.assert_equal(
        encoded.encoded_bytes.startswith(SCRYPT_ALGORITHM_NAME.encode("ascii") + b"$"),
        True,
    )

    ok = StdlibScryptPasswordHasher.verify_password(
        encoded_hash=encoded.encoded_bytes,
        password="correct-horse-battery-staple",
        pepper=pepper,
    )
    testbase.assert_equal(ok, True)

    wrong = StdlibScryptPasswordHasher.verify_password(
        encoded_hash=encoded.encoded_bytes,
        password="wrong-password",
        pepper=pepper,
    )
    testbase.assert_equal(wrong, False)
    return


def test_stdlib_scrypt_verify_rejects_malformed_encoded_hash():
    """
    **Feature: 1-authentication**
    **Property: verify_password returns False for a malformed or
    unrelated encoded_hash rather than raising.**
    """
    _install_pepper()
    reset_phase1_runtime()

    pepper = SecretBytes(b"phase1-test-pepper-material")
    rtnval = StdlibScryptPasswordHasher.verify_password(
        encoded_hash=b"not-a-real-encoded-hash",
        password="anything",
        pepper=pepper,
    )
    testbase.assert_equal(rtnval, False)
    return


def test_verify_unknown_algorithm_raises_configuration_error():
    """
    **Feature: 1-authentication + 0.5-extension-host**
    **Property: resolve_hasher_for_verifying raises ConfigurationError
    when algo_params references an algorithm name that is not registered.**
    """
    reset_phase1_runtime()
    raised = False
    try:
        resolve_hasher_for_verifying(algorithm_name="argon2id-not-registered")
    except ConfigurationError as xcpt:
        raised = True
        testbase.assert_equal("argon2id-not-registered" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_verify_without_db_session_raises():
    """
    **Feature: 1-authentication**
    **Property: verify_local_credentials refuses to run without a session.**
    """
    _install_pepper()
    reset_phase1_runtime()

    raised = False
    try:
        verify_local_credentials(
            login_name="anyone",
            password="anything",
            mfa_code=None,
            source_ip="1.2.3.4",
            db_session=None,
        )
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_verify_rejects_missing_login_or_password():
    """
    **Feature: 1-authentication**
    **Property: Empty login_name or password is rejected as
    AuthenticationError before any DB / hasher work.**
    """
    _install_pepper()
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        verify_local_credentials(
            login_name="",
            password="anything",
            mfa_code=None,
            source_ip="1.2.3.4",
            db_session=session,
        )
    except AuthenticationError:
        raised = True
    testbase.assert_equal(raised, True)

    raised = False
    try:
        verify_local_credentials(
            login_name="someone",
            password="",
            mfa_code=None,
            source_ip="1.2.3.4",
            db_session=session,
        )
    except AuthenticationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_verify_unknown_user_raises_authentication_error():
    """
    **Feature: 1-authentication**
    **Property: Unknown login_name raises AuthenticationError.**
    """
    _install_pepper()
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        verify_local_credentials(
            login_name="nobody",
            password="irrelevant",
            mfa_code=None,
            source_ip="1.2.3.4",
            db_session=session,
        )
    except AuthenticationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_verify_matches_correct_password():
    """
    **Feature: 1-authentication**
    **Property: Verification succeeds for the correct password through
    the registry-resolved hasher.**
    """
    _install_pepper()
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_user_with_credentials(
        session=session, password="correct-horse-battery",
    )

    result = verify_local_credentials(
        login_name="verifier-user",
        password="correct-horse-battery",
        mfa_code=None,
        source_ip="1.2.3.4",
        db_session=session,
    )
    testbase.assert_equal(result.user_id, user_id)
    return


def test_verify_wrong_password_triggers_backoff():
    """
    **Feature: 1-authentication**
    **Property: Repeated failures trigger the backoff window so further
    attempts are rejected without invoking the hasher.**
    """
    _install_pepper()
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    _insert_user_with_credentials(session=session, password="real-password")

    for _ in range(2):
        raised = False
        try:
            verify_local_credentials(
                login_name="verifier-user",
                password="bogus",
                mfa_code=None,
                source_ip="9.9.9.9",
                db_session=session,
            )
        except AuthenticationError:
            raised = True
        testbase.assert_equal(raised, True)

    raised = False
    try:
        verify_local_credentials(
            login_name="verifier-user",
            password="real-password",
            mfa_code=None,
            source_ip="9.9.9.9",
            db_session=session,
        )
    except AuthenticationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_verify_rejects_inactive_user():
    """
    **Feature: 1-authentication**
    **Property: A DEACTIVATED identity user cannot authenticate even
    with the correct password.**
    """
    _install_pepper()
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    _insert_user_with_credentials(
        session=session,
        password="x-wing-pilot",
        status=UserStatus.DEACTIVATED,
    )

    raised = False
    try:
        verify_local_credentials(
            login_name="verifier-user",
            password="x-wing-pilot",
            mfa_code=None,
            source_ip="7.7.7.7",
            db_session=session,
        )
    except AuthenticationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_higher_priority_hasher_overrides_default_for_new_hashes():
    """
    **Feature: 1-authentication + 0.5-extension-host**
    **Property: A hasher registered at a lower PRECEDENCE resolves
    ahead of the in-tree stdlib hasher for new hashes. Legacy rows
    tagged with the stdlib algorithm_name continue to verify through
    the stdlib hasher.**
    """
    _install_pepper()
    reset_phase1_runtime()

    class _FixtureHasher(PasswordHasherProtocol):
        factory_protocol_name: str = "password_hasher"
        protocol_schema_version: int = 1
        PRECEDENCE: int = 500

        @classmethod
        def algorithm_name(cls) -> str:
            return "phase1-fixture-hasher"

        @classmethod
        def hash_password(cls, *, password, pepper):
            rtnval = EncodedHash(
                encoded_bytes=b"fixture:" + password.encode("utf-8"),
                algorithm_name="phase1-fixture-hasher",
                algo_params={"algorithm": "phase1-fixture-hasher"},
            )
            return rtnval

        @classmethod
        def verify_password(cls, *, encoded_hash, password, pepper):
            rtnval = encoded_hash == b"fixture:" + password.encode("utf-8")
            return rtnval

    register_factory_implementation(implementation=_FixtureHasher)
    try:
        hash_bytes, params = hash_password(password="demo")
        testbase.assert_equal(params["algorithm"], "phase1-fixture-hasher")
        testbase.assert_equal(hash_bytes, b"fixture:demo")

        pepper = SecretBytes(b"phase1-test-pepper-material")
        stdlib_encoded = StdlibScryptPasswordHasher.hash_password(
            password="demo", pepper=pepper,
        )
        matched = StdlibScryptPasswordHasher.verify_password(
            encoded_hash=stdlib_encoded.encoded_bytes,
            password="demo",
            pepper=pepper,
        )
        testbase.assert_equal(matched, True)
    finally:
        unregister_factory_implementation(implementation=_FixtureHasher)
    return
