"""
.. module:: ingest.progress.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bus topic constants for progress ingest.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ProgressEventTopics:
    """
        Bus topics emitted by the progress receiver.
    """
    RECEIVED = "entity.progress.received"
    SUMMARY_LANDED = "entity.progress.summary_landed"
    RECORD_INGESTED = "entity.progress.record_ingested"
