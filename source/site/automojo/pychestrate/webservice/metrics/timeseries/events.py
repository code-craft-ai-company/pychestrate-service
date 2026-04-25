"""
.. module:: metrics.timeseries.events
    :synopsis: Timeseries-backend bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class TimeseriesEventTopics:
    """
        Timeseries-backend bus topics. M1 emits
        DEFINITION_REGISTERED + SAMPLE_BUFFERED +
        CARDINALITY_EXCEEDED for diagnostics; M2 wires the
        driver-degradation + write-failure topics.
    """
    DEFINITION_REGISTERED = "pychestrate.timeseries.definition_registered"
    SAMPLE_BUFFERED = "pychestrate.timeseries.sample_buffered"
    CARDINALITY_EXCEEDED = "pychestrate.timeseries.cardinality_exceeded"
    DRIVER_DEGRADED = "pychestrate.timeseries.driver_degraded"
