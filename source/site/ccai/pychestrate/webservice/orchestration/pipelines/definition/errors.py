"""
.. module:: orchestration.pipelines.definition.errors
    :synopsis: Pipeline-definition exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class PipelineError(Exception):
    """
        Base for recoverable pipeline-definition errors.
    """


class PipelineDocumentInvalidError(PipelineError):
    """
        Raised when the pipeline document fails parsing or
        schema validation. The message lists the offending
        location(s).
    """


class PipelineDagCycleError(PipelineError):
    """
        Raised when DAG cycle detection finds a non-trivial
        SCC.
    """


class PipelineStepKindUnknownError(PipelineError):
    """
        Raised when a step references a kind that no registered
        :class:`PipelineStepKindProtocol` implementation
        claims.
    """


class PipelineRunNotFoundError(PipelineError):
    """
        Raised when a pipeline-run lookup misses.
    """


class PipelineStepRunNotFoundError(PipelineError):
    """
        Raised when a pipeline-step-run lookup misses.
    """
