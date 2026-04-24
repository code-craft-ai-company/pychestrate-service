"""
.. module:: test_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the Phase-1 runtime bootstrap helper.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import tempfile

from automojo import testbase

from automojo.pychestrate.webservice.extensions.bootstrap import (
    Phase1BootstrapConfig,
    bootstrap_phase1_runtime,
    register_phase1_builtin_extensions,
)
from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
    list_resource_extensions,
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.messaging.event_bus import reset_for_testing as reset_event_bus
from automojo.pychestrate.webservice.projects.metadata_registry import (
    reset_for_testing as reset_projects_metadata_registry,
)
from automojo.pychestrate.webservice.secrets.kek_loader import (
    get_active_kek,
    reset_active_kek_for_testing,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    get_active_pepper,
    reset_active_pepper_for_testing,
)

from automojo.pychestrate.webservice.audit.extensions.event_type import AuditEventTypeExtension


def test_register_phase1_builtin_extensions_covers_every_feature():
    """
    **Feature: 0.5-extension-host**
    **Property: register_phase1_builtin_extensions populates every
    factory registry + resource-extension category consumed by Layer 1.**
    """
    reset_registry_for_testing()
    reset_event_bus()
    reset_projects_metadata_registry()
    register_phase1_builtin_extensions()

    factory_names = [
        "user_directory_source",
        "auth_provider",
        "secrets_backend",
        "audit_sink",
        "feature_flag_backend",
    ]
    for name in factory_names:
        impls = list_factory_implementations(factory_protocol_name=name)
        testbase.assert_equal(len(impls) >= 1, True)

    audit_kinds = list_resource_extensions(base_class=AuditEventTypeExtension)
    testbase.assert_equal(len(audit_kinds) >= 4, True)
    return


def test_bootstrap_phase1_runtime_end_to_end():
    """
    **Feature: 0.5-extension-host**
    **Property: bootstrap_phase1_runtime loads the KEK, registers every
    Phase-1 extension, installs the pepper, and returns the loaded
    KekHandle.**
    """
    reset_registry_for_testing()
    reset_event_bus()
    reset_projects_metadata_registry()
    reset_active_kek_for_testing()
    reset_active_pepper_for_testing()

    fd, kek_path = tempfile.mkstemp(prefix="phase1-bootstrap-kek-")
    os.close(fd)
    try:
        with open(kek_path, "wb") as handle:
            handle.write(b"A" * 32)

        config = Phase1BootstrapConfig(
            kek_source="file",
            kek_file_path=kek_path,
            kek_env_var=None,
            kek_id="bootstrap-test-kek",
            password_pepper=SecretBytes(b"bootstrap-test-pepper-bytes"),
            session_factory=None,
        )
        kek = bootstrap_phase1_runtime(config=config)

        testbase.assert_equal(kek.kek_id, "bootstrap-test-kek")
        testbase.assert_equal(get_active_kek().kek_id, "bootstrap-test-kek")
        testbase.assert_equal(
            get_active_pepper().reveal(),
            b"bootstrap-test-pepper-bytes",
        )

        # Extension registry populated.
        impls = list_factory_implementations(factory_protocol_name="audit_sink")
        testbase.assert_equal(len(impls) >= 1, True)
    finally:
        os.remove(kek_path)
    return
