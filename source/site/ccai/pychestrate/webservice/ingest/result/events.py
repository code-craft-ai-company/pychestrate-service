"""
.. module:: ingest.result.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bus topic constants for result-tree ingest.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class ResultEventTopics:
    """
        Topics emitted by the result ingester.
    """
    TREE_LANDED = "entity.result_tree.landed"
    ARTIFACT_INGESTED = "entity.artifact.ingested"
    TASK_RESULT_INGESTED = "entity.task_result.ingested"
