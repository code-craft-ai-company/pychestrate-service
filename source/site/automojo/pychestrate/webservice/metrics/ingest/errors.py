"""
.. module:: metrics.ingest.errors
    :synopsis: Metrics-ingest exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
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
