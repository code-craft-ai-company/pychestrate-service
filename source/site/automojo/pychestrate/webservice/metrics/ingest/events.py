"""
.. module:: metrics.ingest.events
    :synopsis: Metrics-ingest bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class MetricsIngestEventTopics:
    """
        Metrics-ingest bus topics.
    """
    METRICS_REGISTRY_LOADED = "pychestrate.metrics.registry_loaded"
    SAMPLE_EMITTED = "pychestrate.metrics.sample_emitted"
    SAMPLE_DROPPED = "pychestrate.metrics.sample_dropped"
