"""
.. module:: metrics.timeseries
    :synopsis: 0-timeseries-backend — facade + native driver + metric registry.

Public surface:

* :class:`TimeseriesSample` — persistence row.
* :class:`MetricKind`, :class:`MetricDefinition`,
  :class:`Sample`, :class:`SampleView` — IO shapes.
* :class:`MetricRegistry` — process-singleton resolving
  metric names to :class:`MetricDefinition`.
* :class:`TimeseriesFacade` — process-singleton dispatching
  writes to the active driver.
* :func:`get_metric_registry`, :func:`get_facade`,
  :func:`reset_for_testing`, :func:`register_definition`,
  :func:`write_counter`, :func:`write_gauge`,
  :func:`list_definitions`,
  :func:`list_samples_for_metric`.
* :class:`TimeseriesDriverProtocol` factory contract +
  reference :class:`NativePgTimeseriesDriver`.
* :class:`TimeseriesEventTopics`.
* Errors: :class:`TimeseriesError`,
  :class:`MetricUnknownError`,
  :class:`MetricLabelInvalidError`,
  :class:`MetricCardinalityExceededError`,
  :class:`TimeseriesDriverNotFoundError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.metrics.timeseries.errors import (
    MetricCardinalityExceededError,
    MetricLabelInvalidError,
    MetricUnknownError,
    TimeseriesDriverNotFoundError,
    TimeseriesError,
)
from ccai.pychestrate.webservice.metrics.timeseries.events import (
    TimeseriesEventTopics,
)
from ccai.pychestrate.webservice.metrics.timeseries.facade import (
    MetricDefinition,
    MetricKind,
    MetricRegistry,
    Sample,
    TimeseriesFacade,
    get_facade,
    get_metric_registry,
    reset_for_testing,
)
from ccai.pychestrate.webservice.metrics.timeseries.factories.driver_protocol import (
    TimeseriesDriverProtocol,
)
from ccai.pychestrate.webservice.metrics.timeseries.factories.native_pg_driver import (
    NativePgTimeseriesDriver,
)
from ccai.pychestrate.webservice.metrics.timeseries.models import (
    TimeseriesSample,
)
from ccai.pychestrate.webservice.metrics.timeseries.service import (
    SampleView,
    list_definitions,
    list_samples_for_metric,
    register_definition,
    write_counter,
    write_gauge,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`NativePgTimeseriesDriver`
        reference. Operators contribute additional drivers
        (Prometheus, Influx, Timescale) by registering
        additional :class:`TimeseriesDriverProtocol`
        implementations with lower PRECEDENCE.
    """
    register_factory_implementation(
        implementation=NativePgTimeseriesDriver,
    )
    return
