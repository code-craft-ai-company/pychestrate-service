"""
.. module:: metrics.ingest.extensions.rpa_counters
    :synopsis: Metric extensions for 6-rpa-orchestration and 9-ui-profiles.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Mapping

from ccai.pychestrate.webservice.metrics.ingest.extensions.metric_definition import (
    MetricDefinitionExtension,
    MetricEmissionKind,
)
from ccai.pychestrate.webservice.metrics.timeseries.facade import (
    MetricDefinition,
    MetricKind,
)


RPA_TRIGGERED_METRIC: str = "pychestrate_rpa_jobs_triggered_total"
RPA_COMPLETED_METRIC: str = "pychestrate_rpa_jobs_completed_total"
RPA_FAILED_METRIC: str = "pychestrate_rpa_jobs_failed_total"
UI_PROFILE_CHANGED_METRIC: str = "pychestrate_ui_profile_deployment_changed_total"


class RpaJobsTriggeredCounter(MetricDefinitionExtension):
    """
        Counter per ``entity.rpa.job_started``. Labels: ``project_id``,
        ``type_id``, ``execution_mode``.
    """

    @classmethod
    def metric_name(cls) -> str:
        return RPA_TRIGGERED_METRIC

    @classmethod
    def definition(cls) -> MetricDefinition:
        rtnval = MetricDefinition(
            name=RPA_TRIGGERED_METRIC,
            kind=MetricKind.COUNTER,
            label_names=("project_id", "type_id", "execution_mode"),
            help_text="Number of RPA jobs triggered.",
            cardinality_max=10000,
        )
        return rtnval

    @classmethod
    def source_topic(cls) -> str:
        return "entity.rpa.job_started"

    @classmethod
    def emission_kind(cls) -> MetricEmissionKind:
        return MetricEmissionKind.COUNTER_INCREMENT

    @classmethod
    def extract_labels(cls, *, event_payload: Mapping[str, Any]) -> Mapping[str, str]:
        rtnval = {
            "project_id": str(event_payload.get("project_id", "")),
            "type_id": str(event_payload.get("type_id", "")),
            "execution_mode": str(event_payload.get("execution_mode", "")),
        }
        return rtnval

    @classmethod
    def extract_value(cls, *, event_payload: Mapping[str, Any]) -> float:
        return 1.0


class RpaJobsCompletedCounter(MetricDefinitionExtension):
    """
        Counter per ``entity.rpa.job_completed`` (successful terminal
        state). Labels: ``project_id``, ``type_id``.
    """

    @classmethod
    def metric_name(cls) -> str:
        return RPA_COMPLETED_METRIC

    @classmethod
    def definition(cls) -> MetricDefinition:
        rtnval = MetricDefinition(
            name=RPA_COMPLETED_METRIC,
            kind=MetricKind.COUNTER,
            label_names=("project_id", "type_id"),
            help_text="Number of RPA jobs that succeeded.",
            cardinality_max=10000,
        )
        return rtnval

    @classmethod
    def source_topic(cls) -> str:
        return "entity.rpa.job_completed"

    @classmethod
    def emission_kind(cls) -> MetricEmissionKind:
        return MetricEmissionKind.COUNTER_INCREMENT

    @classmethod
    def extract_labels(cls, *, event_payload: Mapping[str, Any]) -> Mapping[str, str]:
        rtnval = {
            "project_id": str(event_payload.get("project_id", "")),
            "type_id": str(event_payload.get("type_id", "")),
        }
        return rtnval

    @classmethod
    def extract_value(cls, *, event_payload: Mapping[str, Any]) -> float:
        return 1.0


class RpaJobsFailedCounter(MetricDefinitionExtension):
    """
        Counter per ``entity.rpa.job_failed`` (failed or timed out).
        Labels: ``project_id``, ``type_id``, ``final_status``.
    """

    @classmethod
    def metric_name(cls) -> str:
        return RPA_FAILED_METRIC

    @classmethod
    def definition(cls) -> MetricDefinition:
        rtnval = MetricDefinition(
            name=RPA_FAILED_METRIC,
            kind=MetricKind.COUNTER,
            label_names=("project_id", "type_id", "final_status"),
            help_text="Number of RPA jobs that failed or timed out.",
            cardinality_max=10000,
        )
        return rtnval

    @classmethod
    def source_topic(cls) -> str:
        return "entity.rpa.job_failed"

    @classmethod
    def emission_kind(cls) -> MetricEmissionKind:
        return MetricEmissionKind.COUNTER_INCREMENT

    @classmethod
    def extract_labels(cls, *, event_payload: Mapping[str, Any]) -> Mapping[str, str]:
        rtnval = {
            "project_id": str(event_payload.get("project_id", "")),
            "type_id": str(event_payload.get("type_id", "")),
            "final_status": str(event_payload.get("final_status", event_payload.get("status", ""))),
        }
        return rtnval

    @classmethod
    def extract_value(cls, *, event_payload: Mapping[str, Any]) -> float:
        return 1.0


class UiProfileDeploymentChangedCounter(MetricDefinitionExtension):
    """
        Counter per ``entity.ui_profile.deployment_changed``. Label:
        ``surface_count``.
    """

    @classmethod
    def metric_name(cls) -> str:
        return UI_PROFILE_CHANGED_METRIC

    @classmethod
    def definition(cls) -> MetricDefinition:
        rtnval = MetricDefinition(
            name=UI_PROFILE_CHANGED_METRIC,
            kind=MetricKind.COUNTER,
            label_names=("surface_count",),
            help_text="Number of deployment UI-profile changes.",
            cardinality_max=16,
        )
        return rtnval

    @classmethod
    def source_topic(cls) -> str:
        return "entity.ui_profile.deployment_changed"

    @classmethod
    def emission_kind(cls) -> MetricEmissionKind:
        return MetricEmissionKind.COUNTER_INCREMENT

    @classmethod
    def extract_labels(cls, *, event_payload: Mapping[str, Any]) -> Mapping[str, str]:
        surfaces = event_payload.get("surfaces", []) or []
        rtnval = {"surface_count": str(len(surfaces))}
        return rtnval

    @classmethod
    def extract_value(cls, *, event_payload: Mapping[str, Any]) -> float:
        return 1.0


PHASE11_METRIC_EXTENSIONS = (
    RpaJobsTriggeredCounter,
    RpaJobsCompletedCounter,
    RpaJobsFailedCounter,
    UiProfileDeploymentChangedCounter,
)
