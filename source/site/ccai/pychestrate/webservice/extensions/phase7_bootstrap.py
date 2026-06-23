"""
.. module:: extensions.phase7_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Layer-7 (metrics & dashboards) extensions.

.. moduleauthor:: Code Craft AI LLC

Layer 7 hosts the metrics + dashboards plane:

* ``0-timeseries-backend`` — :class:`NativePgTimeseriesDriver`
  (only in-tree driver at M1; ``timeseries_driver`` factory).
* ``7-metrics-ingest`` — :class:`MetricDefinitionExtension`
  pack registering the in-tree metric catalog
  (:class:`ResourceReservationGrantedCounter` at M1).

M2 adds the alert-rule + SLO-definition extension packs and
the dashboard tile registry.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.metrics.alerts import (
    register_builtin_extensions as alerts_register,
)
from ccai.pychestrate.webservice.metrics.dashboards import (
    register_builtin_extensions as dashboards_register,
)
from ccai.pychestrate.webservice.metrics.ingest import (
    register_builtin_extensions as metrics_ingest_register,
)
from ccai.pychestrate.webservice.metrics.slos import (
    register_builtin_extensions as slos_register,
)
from ccai.pychestrate.webservice.metrics.timeseries import (
    register_builtin_extensions as timeseries_register,
)

# Side-effect imports so Layer-7 model tables attach to the metadata.
from ccai.pychestrate.webservice.metrics.alerts import models as _alerts_models  # noqa: F401
from ccai.pychestrate.webservice.metrics.dashboards import models as _dashboards_models  # noqa: F401
from ccai.pychestrate.webservice.metrics.slos import models as _slos_models  # noqa: F401
from ccai.pychestrate.webservice.metrics.timeseries import models as _timeseries_models  # noqa: F401


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
    dashboards_register()
    alerts_register()
    slos_register()
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
