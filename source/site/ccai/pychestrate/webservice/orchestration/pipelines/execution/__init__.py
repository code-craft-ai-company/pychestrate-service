"""
.. module:: orchestration.pipelines.execution
    :synopsis: Pipeline-execution package -- the DAG-walking orchestrator.

.. moduleauthor:: Code Craft AI LLC

This package hosts the :class:`PipelineOrchestrator` (PR p20q): a
straightforward in-process coordinator that walks a pipeline
definition's stage DAG in topological order and dispatches each
eligible stage's job through the EXISTING build / test / provision
dispatch paths. It does not re-implement job dispatch.

The walk is event-driven: the orchestrator subscribes to the
run-state machine's terminal bus topics (``entity.run.completed`` /
``entity.run.failed`` / ``entity.run.cancelled``). When a stage's
dispatched job reaches a terminal state, the orchestrator
re-evaluates which stages are now eligible, dispatches them, and
skips the dependents of any failed stage.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.orchestration.pipelines.execution.errors import (
    PipelineExecutionError,
    PipelineRunConflictError,
)
from ccai.pychestrate.webservice.orchestration.pipelines.execution.orchestrator import (
    PipelineOrchestrator,
    PipelineTriggerInputs,
)


__all__ = [
    "PipelineExecutionError",
    "PipelineRunConflictError",
    "PipelineOrchestrator",
    "PipelineTriggerInputs",
]
