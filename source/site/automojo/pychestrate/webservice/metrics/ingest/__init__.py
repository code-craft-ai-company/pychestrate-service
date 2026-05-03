"""
.. module:: metrics.ingest
    :synopsis: 7-metrics-ingest — bus → :class:`TimeseriesFacade` translator.

Public surface:

* :class:`MetricDefinitionExtension` base class +
  :class:`ResourceReservationGrantedCounter` reference.
* :class:`MetricsIngestEventTopics`.
* :class:`MetricExtensionView`,
  :class:`EmittedSampleView` — IO shapes.
* :func:`register_builtin_extensions`,
  :func:`reload_definitions_from_extensions`,
  :func:`emit_metric_for_event`,
  :func:`list_metric_extensions`.
* Errors: :class:`MetricsIngestError`,
  :class:`MetricExtensionUnknownError`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_resource_extension,
)
from automojo.pychestrate.webservice.metrics.ingest.errors import (
    MetricExtensionUnknownError,
    MetricsIngestError,
)
from automojo.pychestrate.webservice.metrics.ingest.events import (
    MetricsIngestEventTopics,
)
from automojo.pychestrate.webservice.metrics.ingest.extensions.metric_definition import (
    MetricDefinitionExtension,
)
from automojo.pychestrate.webservice.metrics.ingest.extensions.reservation_granted_counter import (
    ResourceReservationGrantedCounter,
)
from automojo.pychestrate.webservice.metrics.ingest.service import (
    EmittedSampleView,
    MetricExtensionView,
    emit_metric_for_event,
    list_metric_extensions,
    reload_definitions_from_extensions,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`ResourceReservationGrantedCounter`
        reference under :class:`MetricDefinitionExtension`.
    """
    register_resource_extension(
        base_class=MetricDefinitionExtension,
        extension=ResourceReservationGrantedCounter,
    )
    return
