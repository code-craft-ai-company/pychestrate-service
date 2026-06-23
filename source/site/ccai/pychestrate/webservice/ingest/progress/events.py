"""
.. module:: ingest.progress.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bus topic constants for progress ingest.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class ProgressEventTopics:
    """
        Bus topics emitted by the progress receiver.
    """
    RECEIVED = "entity.progress.received"
    SUMMARY_LANDED = "entity.progress.summary_landed"
    RECORD_INGESTED = "entity.progress.record_ingested"
    #: Emitted when a generalized build / provision progress frame
    #: (``frame_kind != test``) lands. The live-run bus bridge
    #: forwards this onto the run's SSE relay as a ``progress``
    #: RunEvent.
    FRAME_LANDED = "entity.progress.frame_landed"
