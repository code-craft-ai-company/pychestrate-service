"""
.. module:: orchestration.test.compare.events
    :synopsis: Compare-runs bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class CompareEventTopics:
    """
        Compare-runs bus topics. M1 emits BUILT and CACHE_HIT;
        M2 wires the diff-viewer-selected diagnostic.
    """
    BUILT = "entity.compare.report_built"
    CACHE_HIT = "entity.compare.report_cache_hit"
    DIFF_VIEWER_SELECTED = "entity.compare.diff_viewer_selected"
