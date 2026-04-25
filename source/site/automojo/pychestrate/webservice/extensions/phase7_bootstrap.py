"""
.. module:: extensions.phase7_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Layer-7 (metrics & dashboards) extensions.

.. moduleauthor:: Automation Mojo LLC

Layer 7 hosts the metrics + dashboards plane:

* ``0-timeseries-backend`` — :class:`NativePgTimeseriesDriver`
  (only in-tree driver at M1; ``timeseries_driver`` factory).
* ``7-metrics-ingest`` — :class:`MetricDefinitionExtension`
  pack registering the in-tree metric catalog
  (:class:`ResourceReservationGrantedCounter` at M1).

M2 adds the alert-rule + SLO-definition extension packs and
the dashboard tile registry.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.metrics.ingest import (
    register_builtin_extensions as metrics_ingest_register,
)
from automojo.pychestrate.webservice.metrics.timeseries import (
    register_builtin_extensions as timeseries_register,
)

# Side-effect imports so Layer-7 model tables attach to the metadata.
from automojo.pychestrate.webservice.metrics.timeseries import models as _timeseries_models  # noqa: F401


SessionFactory = Callable[[], DbSession]


@dataclass(frozen=True)
class Phase7BootstrapConfig:
    """
        Operator-supplied Phase-7 bootstrap configuration.

        :param session_factory: Optional session factory for
                                future M2 bus subscriber wiring.
    """
    session_factory: Optional[SessionFactory]


def register_phase7_builtin_extensions() -> None:
    """
        Register every in-tree Layer-7 factory + resource
        extension. Must run before any service that emits
        metrics so the registry is non-empty.
    """
    timeseries_register()
    metrics_ingest_register()
    return


def bootstrap_phase7_runtime(*, config: Phase7BootstrapConfig) -> None:
    """
        Register Layer-7 extensions. M1 has no background
        workers; M2 wires the
        :class:`MetricDefinitionExtension` bus subscriber +
        the alert-evaluator tick loop.
    """
    register_phase7_builtin_extensions()
    _ = config
    return
