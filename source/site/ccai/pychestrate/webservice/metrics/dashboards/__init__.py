"""
.. module:: metrics.dashboards
    :synopsis: 7-project-dashboards — per-project dashboard catalog.

Public surface:

* :class:`Dashboard` — persistence row.
* :class:`TileInstance`, :class:`DashboardView`,
  :class:`TileKindRecord` — IO shapes.
* :func:`create_dashboard`, :func:`get_dashboard`,
  :func:`list_dashboards_for_project`,
  :func:`update_dashboard_tiles`,
  :func:`delete_dashboard`,
  :func:`list_tile_kinds`.
* :class:`DashboardTileKindProtocol` factory contract +
  reference :class:`MetricLineChartTileKind`,
  :class:`MetricSingleStatTileKind`.
* :class:`DashboardEventTopics`.
* Errors: :class:`DashboardError`,
  :class:`DashboardNotFoundError`,
  :class:`DashboardConflictError`,
  :class:`TileKindUnknownError`,
  :class:`TileConfigInvalidError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.metrics.dashboards.errors import (
    DashboardConflictError,
    DashboardError,
    DashboardNotFoundError,
    TileConfigInvalidError,
    TileKindUnknownError,
)
from ccai.pychestrate.webservice.metrics.dashboards.events import (
    DashboardEventTopics,
)
from ccai.pychestrate.webservice.metrics.dashboards.factories.tile_kind_protocol import (
    DashboardTileKindProtocol,
    TileKindRecord,
)
from ccai.pychestrate.webservice.metrics.dashboards.factories.line_chart_tile_kind import (
    MetricLineChartTileKind,
)
from ccai.pychestrate.webservice.metrics.dashboards.factories.single_stat_tile_kind import (
    MetricSingleStatTileKind,
)
from ccai.pychestrate.webservice.metrics.dashboards.models import (
    Dashboard,
)
from ccai.pychestrate.webservice.metrics.dashboards.service import (
    DashboardView,
    TileInstance,
    create_dashboard,
    delete_dashboard,
    get_dashboard,
    list_dashboards_for_project,
    list_tile_kinds,
    update_dashboard_tiles,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`MetricLineChartTileKind` and
        :class:`MetricSingleStatTileKind` references.
    """
    register_factory_implementation(implementation=MetricLineChartTileKind)
    register_factory_implementation(implementation=MetricSingleStatTileKind)
    return
