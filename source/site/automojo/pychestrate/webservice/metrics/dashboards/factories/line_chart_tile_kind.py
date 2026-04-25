"""
.. module:: metrics.dashboards.factories.line_chart_tile_kind
    :synopsis: MetricLineChartTileKind — reference line-chart tile.

Required config:

* ``metric_name`` — registered timeseries metric.
* ``label_filter`` — mapping of label name → exact value;
  empty dict means "no filter".

Optional config:

* ``range_seconds`` — non-negative integer (defaults to
  3600 in the M2 UI).
* ``title`` — string display title.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from automojo.pychestrate.webservice.metrics.dashboards.factories.tile_kind_protocol import (
    DashboardTileKindProtocol,
    TileKindRecord,
)


METRIC_LINE_CHART_KIND_NAME: str = "metric-line-chart"


class MetricLineChartTileKind(DashboardTileKindProtocol):
    """
        Reference line-chart tile.
    """

    factory_protocol_name: str = "dashboard_tile_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def kind_name(cls) -> str:
        rtnval = METRIC_LINE_CHART_KIND_NAME
        return rtnval

    @classmethod
    def record(cls) -> TileKindRecord:
        rtnval = TileKindRecord(
            kind=METRIC_LINE_CHART_KIND_NAME,
            webcomponent_tag="px-metric-line-chart",
            default_size=(6, 3),
            description="Line chart of a timeseries metric over a range.",
            default_config={
                "label_filter": {},
                "range_seconds": 3600,
                "title": "",
            },
        )
        return rtnval

    @classmethod
    def validate_config(
            cls,
            *,
            config: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []
        metric_name = config.get("metric_name", None)
        if metric_name is None:
            issues.append("'metric_name' is required")
        elif not isinstance(metric_name, str) or len(metric_name) == 0:
            issues.append("'metric_name' must be a non-empty string")

        label_filter = config.get("label_filter", {})
        if not isinstance(label_filter, dict):
            issues.append("'label_filter' must be a mapping when present")
        else:
            for key, value in label_filter.items():
                if not isinstance(key, str) or len(key) == 0:
                    issues.append("'label_filter' keys must be non-empty strings")
                    break
                if not isinstance(value, str):
                    issues.append("'label_filter' values must be strings")
                    break

        range_seconds = config.get("range_seconds", 0)
        if not isinstance(range_seconds, int) or range_seconds < 0:
            issues.append("'range_seconds' must be a non-negative integer")

        title = config.get("title", "")
        if not isinstance(title, str):
            issues.append("'title' must be a string when present")

        if len(issues) > 0:
            rtnval: Tuple[bool, Tuple[str, ...]] = (False, tuple(issues))
            return rtnval
        rtnval = (True, ())
        return rtnval
