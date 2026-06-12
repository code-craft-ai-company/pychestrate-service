"""
.. module:: metrics.dashboards.factories.single_stat_tile_kind
    :synopsis: MetricSingleStatTileKind — reference single-stat tile.

Required config:

* ``metric_name`` — registered timeseries metric.

Optional config:

* ``label_filter`` — exact-match label dict.
* ``unit`` — display unit string.
* ``title`` — display title.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from ccai.pychestrate.webservice.metrics.dashboards.factories.tile_kind_protocol import (
    DashboardTileKindProtocol,
    TileKindRecord,
)


METRIC_SINGLE_STAT_KIND_NAME: str = "metric-single-stat"


class MetricSingleStatTileKind(DashboardTileKindProtocol):
    """
        Reference single-stat tile (one big number).
    """

    factory_protocol_name: str = "dashboard_tile_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1100

    @classmethod
    def kind_name(cls) -> str:
        rtnval = METRIC_SINGLE_STAT_KIND_NAME
        return rtnval

    @classmethod
    def record(cls) -> TileKindRecord:
        rtnval = TileKindRecord(
            kind=METRIC_SINGLE_STAT_KIND_NAME,
            webcomponent_tag="px-metric-single-stat",
            default_size=(2, 2),
            description="Single-value display of the latest sample.",
            default_config={
                "label_filter": {},
                "unit": "",
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

        unit = config.get("unit", "")
        if not isinstance(unit, str):
            issues.append("'unit' must be a string when present")

        title = config.get("title", "")
        if not isinstance(title, str):
            issues.append("'title' must be a string when present")

        if len(issues) > 0:
            rtnval: Tuple[bool, Tuple[str, ...]] = (False, tuple(issues))
            return rtnval
        rtnval = (True, ())
        return rtnval
