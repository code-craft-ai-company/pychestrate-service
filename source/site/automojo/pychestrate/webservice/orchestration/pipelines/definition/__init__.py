"""
.. module:: orchestration.pipelines.definition
    :synopsis: 6-pipeline-definition — pipeline document parser + DAG + run state.

Public surface:

* :class:`PipelineRun`, :class:`PipelineStageRun`,
  :class:`PipelineStepRun`, :class:`PipelineDocumentCache`,
  :class:`PipelineRunState`, :class:`StageState`,
  :class:`StepState`, :class:`TriggerCause` — persistence rows
  + enums.
* :class:`PipelineDocument`, :class:`StageSpec`,
  :class:`StepSpec`, :class:`PipelineRunView`,
  :class:`PipelineStageRunView`, :class:`PipelineStepRunView`,
  :class:`TriggerAspects` — IO shapes.
* :func:`parse_document`, :func:`canonicalize_document`,
  :func:`compute_pipeline_digest`, :func:`build_dag`,
  :func:`load_from_source`, :func:`trigger_run`,
  :func:`get_pipeline_run`, :func:`apply_step_terminal`.
* :class:`PipelineStepKindProtocol` factory contract +
  reference :class:`BuildStepKind`, :class:`TestStepKind`,
  :class:`ScriptStepKind`.
* :class:`PipelineEventTopics`.
* Errors: :class:`PipelineError`,
  :class:`PipelineDocumentInvalidError`,
  :class:`PipelineDagCycleError`,
  :class:`PipelineStepKindUnknownError`,
  :class:`PipelineRunNotFoundError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.canonicalization import (
    canonicalize_document,
    compute_pipeline_digest,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.dag import (
    build_dag,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.errors import (
    PipelineDagCycleError,
    PipelineDocumentInvalidError,
    PipelineError,
    PipelineRunNotFoundError,
    PipelineStepKindUnknownError,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.events import (
    PipelineEventTopics,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.factories.build_step_kind import (
    BuildStepKind,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.factories.script_step_kind import (
    ScriptStepKind,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.factories.step_kind_protocol import (
    JobProduction,
    PipelineStepKindProtocol,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.factories.test_step_kind import (
    TestStepKind,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.models import (
    PipelineDocumentCache,
    PipelineRun,
    PipelineRunState,
    PipelineStageRun,
    PipelineStepRun,
    StageState,
    StepState,
    TriggerCause,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.parser import (
    PipelineDocument,
    StageSpec,
    StepSpec,
    parse_document,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.service import (
    PipelineRunView,
    PipelineStageRunView,
    PipelineStepRunView,
    TriggerAspects,
    apply_step_terminal,
    get_pipeline_run,
    load_from_source,
    trigger_run,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`BuildStepKind`,
        :class:`TestStepKind`, and :class:`ScriptStepKind`
        reference implementations.
    """
    register_factory_implementation(implementation=BuildStepKind)
    register_factory_implementation(implementation=TestStepKind)
    register_factory_implementation(implementation=ScriptStepKind)
    return
