"""
.. module:: metrics.timeseries.errors
    :synopsis: Timeseries-backend exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class TimeseriesError(Exception):
    """
        Base for recoverable timeseries-backend errors.
    """


class MetricUnknownError(TimeseriesError):
    """
        Raised when a write references a metric_name that
        the registry has not seen.
    """


class MetricLabelInvalidError(TimeseriesError):
    """
        Raised when a write supplies labels that do not match
        the metric's declared label_names — extras, missing,
        or reserved.
    """


class MetricCardinalityExceededError(TimeseriesError):
    """
        Raised when a write would push the metric's distinct
        label-tuple count past ``cardinality_max``.
    """


class TimeseriesDriverNotFoundError(TimeseriesError):
    """
        Raised when no :class:`TimeseriesDriverProtocol` is
        registered.
    """
