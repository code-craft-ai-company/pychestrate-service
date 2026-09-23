"""
.. module:: extensions.view_registry_self_check
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Startup self-check -- flag views whose extension
               registries are empty.

.. moduleauthor:: Code Craft AI LLC

Many views can only do their job when an extension registry behind
them has at least one implementation: an SLO needs a registered SLO
kind, an alert rule an alert-rule kind, a dashboard tile a tile kind,
an inbound webhook a parser, the Timeseries view a loaded metric
catalog. When a bootstrap step is missing, those registries are empty
and the views fail with messages such as "no registered kind" (audit
ORC-04). :func:`log_view_registry_self_check` runs after bootstrap and
logs one warning per view whose registries are empty, so a
misconfigured deployment says so in its startup log.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from dataclasses import dataclass
from typing import Callable, List, Tuple

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)


_LOGGER = logging.getLogger("pychestrate.extensions.self_check")


@dataclass(frozen=True)
class ViewRegistryRequirement:
    """
        One registry a view depends on.

        :param route: The view's route (e.g. ``/slos``).
        :param registry: Human-readable registry name.
        :param count: Zero-arg callable returning how many entries the
                      registry holds.
    """
    route: str
    registry: str
    count: Callable[[], int]


@dataclass(frozen=True)
class ViewRegistryGap:
    """
        A view whose registry is empty.

        :param route: The view's route.
        :param registry: The empty registry.
    """
    route: str
    registry: str


def _factory_count(*, protocol_name: str) -> Callable[[], int]:
    """
        A counter for one factory-protocol registry.

        :param protocol_name: ``factory_protocol_name`` to count.

        :returns: Zero-arg callable.
    """
    def _count() -> int:
        rtnval = len(list_factory_implementations(factory_protocol_name=protocol_name))
        return rtnval

    rtnval = _count
    return rtnval


def _metric_catalog_count() -> int:
    """
        How many metric definitions the timeseries registry holds (the
        metric catalog).

        :returns: The count.
    """
    from ccai.pychestrate.webservice.metrics.timeseries import (  # noqa: E402
        service as timeseries_service,
    )
    rtnval = len(timeseries_service.list_definitions())
    return rtnval


#: Every view-to-registry dependency the self-check verifies.
VIEW_REGISTRY_REQUIREMENTS: Tuple[ViewRegistryRequirement, ...] = (
    ViewRegistryRequirement(
        route="/timeseries", registry="metric catalog", count=_metric_catalog_count,
    ),
    ViewRegistryRequirement(
        route="/timeseries", registry="timeseries_driver", count=_factory_count(protocol_name="timeseries_driver"),
    ),
    ViewRegistryRequirement(
        route="/dashboards", registry="dashboard_tile_kind", count=_factory_count(protocol_name="dashboard_tile_kind"),
    ),
    ViewRegistryRequirement(
        route="/dashboards", registry="metric catalog", count=_metric_catalog_count,
    ),
    ViewRegistryRequirement(
        route="/slos", registry="slo_definition_kind", count=_factory_count(protocol_name="slo_definition_kind"),
    ),
    ViewRegistryRequirement(
        route="/metric-alerts", registry="alert_rule_kind", count=_factory_count(protocol_name="alert_rule_kind"),
    ),
    ViewRegistryRequirement(
        route="/webhooks", registry="inbound_webhook_parser", count=_factory_count(protocol_name="inbound_webhook_parser"),
    ),
    ViewRegistryRequirement(
        route="/release-channels", registry="release_channel_policy", count=_factory_count(protocol_name="release_channel_policy"),
    ),
    ViewRegistryRequirement(
        route="/pipelines", registry="pipeline_step_kind", count=_factory_count(protocol_name="pipeline_step_kind"),
    ),
    ViewRegistryRequirement(
        route="/test-catalog", registry="test_catalog_importer", count=_factory_count(protocol_name="test_catalog_importer"),
    ),
    ViewRegistryRequirement(
        route="/test-catalog", registry="test_runner_kind", count=_factory_count(protocol_name="test_runner_kind"),
    ),
    ViewRegistryRequirement(
        route="/builds", registry="build_runner_kind", count=_factory_count(protocol_name="build_runner_kind"),
    ),
    ViewRegistryRequirement(
        route="/environments", registry="environment_kind", count=_factory_count(protocol_name="environment_kind"),
    ),
    ViewRegistryRequirement(
        route="/environments", registry="drift_checker", count=_factory_count(protocol_name="drift_checker"),
    ),
    ViewRegistryRequirement(
        route="/provisioning-runs", registry="infra_tool_driver", count=_factory_count(protocol_name="infra_tool_driver"),
    ),
    ViewRegistryRequirement(
        route="/blast-radius-guards", registry="guard_rule", count=_factory_count(protocol_name="guard_rule"),
    ),
)


def check_view_registries(
        *,
        requirements: Tuple[ViewRegistryRequirement, ...] = VIEW_REGISTRY_REQUIREMENTS
    ) -> List[ViewRegistryGap]:
    """
        Return one gap per requirement whose registry is empty (or
        cannot be read).

        :param requirements: The requirements to check.

        :returns: The gaps, in requirement order (empty when every view
                  has what it needs).
    """
    gaps: List[ViewRegistryGap] = []
    for requirement in requirements:
        try:
            count = requirement.count()
        except Exception as xcpt:  # noqa: BLE001 -- a broken counter is a gap
            _LOGGER.warning(
                "pychestrate.bootstrap.self_check.count_failed route=%s registry=%s error=%s",
                requirement.route,
                requirement.registry,
                xcpt,
            )
            count = 0
        if count <= 0:
            gaps.append(ViewRegistryGap(route=requirement.route, registry=requirement.registry))
    rtnval = gaps
    return rtnval


def log_view_registry_self_check() -> List[ViewRegistryGap]:
    """
        Run :func:`check_view_registries` and log the outcome: one
        warning per gap, or one info line when every view is served.

        :returns: The gaps found.
    """
    gaps = check_view_registries()
    for gap in gaps:
        _LOGGER.warning(
            "pychestrate.bootstrap.self_check.empty_registry route=%s registry=%s"
            " -- this view cannot create or show data until the registry is"
            " populated at bootstrap",
            gap.route,
            gap.registry,
        )
    if len(gaps) == 0:
        _LOGGER.info(
            "pychestrate.bootstrap.self_check.ok views=%s",
            len(set(requirement.route for requirement in VIEW_REGISTRY_REQUIREMENTS)),
        )
    rtnval = gaps
    return rtnval


__all__ = [
    "VIEW_REGISTRY_REQUIREMENTS",
    "ViewRegistryGap",
    "ViewRegistryRequirement",
    "check_view_registries",
    "log_view_registry_self_check",
]
