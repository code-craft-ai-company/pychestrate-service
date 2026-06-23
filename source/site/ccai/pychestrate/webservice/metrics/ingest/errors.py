"""
.. module:: metrics.ingest.errors
    :synopsis: Metrics-ingest exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class MetricsIngestError(Exception):
    """
        Base for recoverable metrics-ingest errors.
    """


class MetricExtensionUnknownError(MetricsIngestError):
    """
        Raised when a caller references a metric_name that no
        :class:`MetricDefinitionExtension` claims.
    """
