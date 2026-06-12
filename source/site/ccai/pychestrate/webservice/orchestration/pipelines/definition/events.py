"""
.. module:: orchestration.pipelines.definition.events
    :synopsis: Pipeline-definition bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class PipelineEventTopics:
    """
        Pipeline-definition bus topics.
    """
    DEFINED = "entity.pipeline.defined"
    RUN_STARTED = "entity.pipeline.run_started"
    RUN_COMPLETED = "entity.pipeline.run_completed"
    STAGE_STARTED = "entity.pipeline.stage.started"
    STAGE_COMPLETED = "entity.pipeline.stage.completed"
    STAGE_SKIPPED = "entity.pipeline.stage.skipped"
    STEP_DISPATCHED = "entity.pipeline.step.dispatched"
    STEP_COMPLETED = "entity.pipeline.step.completed"
    VALIDATION_FAILED = "entity.pipeline.validation_failed"
