"""
.. module:: orchestration.pipelines.execution.errors
    :synopsis: Pipeline-execution exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class PipelineExecutionError(Exception):
    """
        Base for recoverable pipeline-execution errors.
    """


class PipelineRunConflictError(PipelineExecutionError):
    """
        Raised when a pipeline run cannot be triggered because a
        conflicting run is already active for the same definition.
        Surfaces as an HTTP 409 over REST.
    """


class PipelineMatrixUnsupportedError(PipelineExecutionError):
    """
        Raised when a trigger asks for matrix dimensions. A pipeline
        run executes every stage exactly once -- matrix expansion is
        a preview only -- so a run that silently ignored the matrix
        would report success for shards it never ran. Surfaces as an
        HTTP 422 over REST.
    """
