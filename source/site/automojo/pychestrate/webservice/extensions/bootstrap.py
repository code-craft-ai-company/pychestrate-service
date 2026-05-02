"""
.. module:: extensions.bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Phase-1 extensions at service startup.

.. moduleauthor:: Automation Mojo LLC

This module provides :func:`register_phase1_builtin_extensions` — the
canonical entry point the service bootstrap calls once at startup to
populate the extension host with the in-tree reference implementations
shipped by each Layer 1 feature. When the full ``E-extension-host``
scanner lands, this function becomes the seed-only path that runs before
on-disk discovery; the function signature stays stable.

For services that need the full Phase-1 runtime wired in one call,
:func:`bootstrap_phase1_runtime` chains extension registration with the
KEK loader, the audit bus subscriber, and the password-pepper installer.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.audit import register_builtin_extensions as audit_register
from automojo.pychestrate.webservice.audit.bus_subscriber import wire_bus_subscribers
from automojo.pychestrate.webservice.clients import (
    register_builtin_extensions as clients_register,
)
from automojo.pychestrate.webservice.identity.flags import register_builtin_extensions as flags_register
from automojo.pychestrate.webservice.identity.users import register_builtin_extensions as users_register
from automojo.pychestrate.webservice.projects import register_builtin_extensions as projects_register
from automojo.pychestrate.webservice.projects.metadata_registry import freeze_registry as projects_freeze_registry
from automojo.pychestrate.webservice.secrets import register_builtin_extensions as secrets_register
from automojo.pychestrate.webservice.secrets.kek_loader import (
    KekHandle,
    load_kek_at_startup,
    set_active_kek,
)
from automojo.pychestrate.webservice.security.auth import register_builtin_extensions as auth_register
from automojo.pychestrate.webservice.security.auth.pepper_loader import set_active_pepper
from automojo.pychestrate.webservice.security.rbac import register_builtin_extensions as rbac_register
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes

# Side-effect imports: loading every model module ensures the tables are
# registered on ``PychestratePhase1Base.metadata`` before ``create_all``
# runs (tests) or Alembic inspects the metadata (production migrations).
# Without these, a test that imports only a subset of features can fail
# with ``NoReferencedTableError`` when an FK points at a table whose
# model module was never loaded.
from automojo.pychestrate.webservice.artifacts import models as _artifacts_models  # noqa: F401
from automojo.pychestrate.webservice.audit import models as _audit_models  # noqa: F401
from automojo.pychestrate.webservice.clients import models as _clients_models  # noqa: F401
from automojo.pychestrate.webservice.extensions.sandbox import models as _extensions_sandbox_models  # noqa: F401
from automojo.pychestrate.webservice.identity.flags import models as _flags_models  # noqa: F401
from automojo.pychestrate.webservice.identity.users import models as _users_models  # noqa: F401
from automojo.pychestrate.webservice.ingest.progress import models as _ingest_progress_models  # noqa: F401
from automojo.pychestrate.webservice.ingest.result import models as _ingest_result_models  # noqa: F401
from automojo.pychestrate.webservice.maintenance import models as _maintenance_models  # noqa: F401
from automojo.pychestrate.webservice.metrics.alerts import models as _metrics_alerts_models  # noqa: F401
from automojo.pychestrate.webservice.metrics.dashboards import models as _metrics_dashboards_models  # noqa: F401
from automojo.pychestrate.webservice.metrics.slos import models as _metrics_slos_models  # noqa: F401
from automojo.pychestrate.webservice.metrics.timeseries import models as _metrics_timeseries_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.cancel import models as _jobs_cancel_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.dispatch import models as _jobs_dispatch_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.dispatch.receipt import models as _jobs_dispatch_receipt_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.envelope import models as _jobs_envelope_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.offline import models as _jobs_offline_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.reconcile import models as _jobs_reconcile_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.results import models as _jobs_results_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.run.state import models as _jobs_run_state_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.build import models as _orch_build_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.build.artifacts import models as _orch_build_artifacts_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.infra.drift import models as _orch_infra_drift_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.infra.environment import models as _orch_infra_environment_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.infra.guards import models as _orch_infra_guards_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.infra.runs import models as _orch_infra_runs_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.pipelines.definition import models as _orch_pipeline_definition_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.pipelines.sharding import models as _orch_sharding_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.source import models as _orch_source_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.test import models as _orch_test_run_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.test.catalog import models as _orch_test_catalog_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.test.compare import models as _orch_test_compare_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.test.flake import models as _orch_test_flake_models  # noqa: F401
from automojo.pychestrate.webservice.orchestration.test.triage import models as _orch_test_triage_models  # noqa: F401
from automojo.pychestrate.webservice.projects import models as _projects_models  # noqa: F401
from automojo.pychestrate.webservice.resources.checkout import models as _resources_checkout_models  # noqa: F401
from automojo.pychestrate.webservice.resources.health import models as _resources_health_models  # noqa: F401
from automojo.pychestrate.webservice.resources.inventory import models as _resources_inventory_models  # noqa: F401
from automojo.pychestrate.webservice.resources.lease import models as _resources_lease_models  # noqa: F401
from automojo.pychestrate.webservice.resources.pools import models as _resources_pools_models  # noqa: F401
from automojo.pychestrate.webservice.resources.scheduler import models as _resources_scheduler_models  # noqa: F401
from automojo.pychestrate.webservice.resources.usage_history import models as _resources_usage_history_models  # noqa: F401
from automojo.pychestrate.webservice.clients.upgrades import models as _upgrades_models  # noqa: F401
from automojo.pychestrate.webservice.ops.release import models as _ops_release_models  # noqa: F401
from automojo.pychestrate.webservice.webhooks_in import models as _webhooks_in_models  # noqa: F401
from automojo.pychestrate.webservice.webhooks_out import models as _webhooks_out_models  # noqa: F401
from automojo.pychestrate.webservice.secrets import models as _secrets_models  # noqa: F401
from automojo.pychestrate.webservice.security.auth import models as _auth_models  # noqa: F401
from automojo.pychestrate.webservice.security.rbac import models as _rbac_models  # noqa: F401

# Side-effect import so the published RestEndpointExtension resource
# base is loaded into the ResourceExtension subclass tree before the
# plugin-api catalog is built.
from automojo.pychestrate.webservice.extensions import rest_endpoint_protocol as _rest_endpoint_protocol  # noqa: F401
from automojo.pychestrate.webservice.extensions import rest_endpoint_example as _rest_endpoint_example  # noqa: F401

# CLI extension surface lives under ``automojo.pychestrate.cli`` for
# distribution reasons but the resource base must be loaded into the
# subclass tree alongside the others so the catalog walker sees it.
from automojo.pychestrate.cli.extensions import cli_subcommand as _cli_subcommand  # noqa: F401
from automojo.pychestrate.cli.extensions import example_subcommand as _cli_example_subcommand  # noqa: F401

# 1-authentication MFA extension surface — loaded ahead of the
# catalog build so MFAMethodExtension is enumerated.
from automojo.pychestrate.webservice.security.auth.extensions import mfa_method as _mfa_method  # noqa: F401
from automojo.pychestrate.webservice.security.auth.extensions import totp_method as _totp_method  # noqa: F401


SessionFactory = Callable[[], DbSession]


@dataclass(frozen=True)
class Phase1BootstrapConfig:
    """
        Operator-supplied bootstrap configuration.

        :param kek_source: ``"file"`` or ``"env"`` — matches
                           :func:`load_kek_at_startup` semantics.
        :param kek_file_path: Path to the KEK file when ``kek_source="file"``.
        :param kek_env_var: Environment variable name when ``kek_source="env"``.
        :param kek_id: Operator-assigned identifier for the active KEK.
        :param password_pepper: Pre-loaded pepper bytes wrapped in
                                :class:`SecretBytes`. Pass ``None`` to skip
                                pepper installation — callers that use only
                                OIDC / SAML do not need a local pepper.
        :param session_factory: Callable that opens a new session; used by
                                the audit bus subscriber to persist audit
                                rows outside the originating request's
                                transaction.
    """
    kek_source: str
    kek_file_path: Optional[str]
    kek_env_var: Optional[str]
    kek_id: str
    password_pepper: Optional[SecretBytes]
    session_factory: Optional[SessionFactory]


def register_phase1_builtin_extensions() -> None:
    """
        Register every in-tree Phase-1 factory protocol implementation and
        resource extension pack in the canonical order: identity users
        first (so directory sources are ready), then authentication (so
        sessions can reference them), then RBAC, secrets, audit, and
        feature flags.

        :returns: None.
    """
    users_register()
    auth_register()
    rbac_register()
    secrets_register()
    audit_register()
    flags_register()
    clients_register()
    projects_register()
    projects_freeze_registry()
    return


def bootstrap_phase1_runtime(*, config: Phase1BootstrapConfig) -> KekHandle:
    """
        Register extensions, load the KEK, wire the audit bus subscriber,
        and install the password pepper. Intended to be called once at
        service startup.

        :param config: Caller-supplied :class:`Phase1BootstrapConfig`.

        :returns: The loaded :class:`KekHandle` — useful for operators who
                  want to log the active KEK id at startup.
    """
    register_phase1_builtin_extensions()

    kek = load_kek_at_startup(
        source=config.kek_source,
        file_path=config.kek_file_path,
        env_var=config.kek_env_var,
        kek_id=config.kek_id,
    )
    set_active_kek(kek=kek)

    if config.password_pepper is not None:
        set_active_pepper(pepper=config.password_pepper)

    if config.session_factory is not None:
        wire_bus_subscribers(session_factory=config.session_factory)

    return kek
