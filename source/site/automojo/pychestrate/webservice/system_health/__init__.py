"""
.. module:: system_health
    :synopsis: 0-system-health — probe registry, scheduler, snapshot + aggregator.

Public surface (M1):

* :class:`HealthRegistry` + :class:`ProbeRecord` /
  :class:`ProbeKind` / :class:`ProbeStatus` /
  :class:`OverallStatus` / :class:`ProbeResult` /
  :class:`HealthSnapshot`.
* :class:`HealthScheduler` + :func:`run_probe_now` /
  :class:`HealthConfig`.
* :class:`SystemHealthProbeExtension` resource base +
  :class:`PostgresHealthProbe` reference + the
  :func:`set_db_session_factory` /
  :func:`reset_for_testing` postgres-probe helpers.
* :class:`SystemHealthEventTopics` +
  :func:`evaluate_transitions` aggregator helper.
* Errors: :class:`HealthRegistryError`,
  :class:`DuplicateProbeError`,
  :class:`ProbeNotFoundError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_resource_extension,
)
from automojo.pychestrate.webservice.system_health.aggregator import (
    evaluate_transitions,
    reset_for_testing as reset_aggregator_for_testing,
)
from automojo.pychestrate.webservice.system_health.events import (
    SystemHealthEventTopics,
)
from automojo.pychestrate.webservice.system_health.exceptions import (
    DuplicateProbeError,
    HealthRegistryError,
    ProbeNotFoundError,
)
from automojo.pychestrate.webservice.system_health.extensions.postgres_probe import (
    PostgresHealthProbe,
    reset_for_testing as reset_postgres_probe_for_testing,
    set_db_session_factory,
)
from automojo.pychestrate.webservice.system_health.extensions.probe import (
    SystemHealthProbeExtension,
)
from automojo.pychestrate.webservice.system_health.registry import (
    HealthRegistry,
    HealthSnapshot,
    OverallStatus,
    ProbeKind,
    ProbeRecord,
    ProbeResult,
    ProbeStatus,
)
from automojo.pychestrate.webservice.system_health.scheduler import (
    HealthConfig,
    HealthScheduler,
    run_probe_now,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`PostgresHealthProbe` reference
        under the :class:`SystemHealthProbeExtension` resource
        category. M2 widens this to the bus / object-store /
        timeseries / disk-space probes.
    """
    register_resource_extension(
        base_class=SystemHealthProbeExtension,
        extension=PostgresHealthProbe,
    )
    return
