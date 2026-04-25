"""
.. module:: orchestration.pipelines.definition.factories.step_kind_protocol
    :synopsis: ``pipeline_step_kind`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, List, Mapping, Tuple

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


@dataclass(frozen=True)
class JobProduction:
    """
        Pipeline → Layer-5 translation result.

        :param job_kind: Stable kind label that the M2 dispatch
                         layer routes on (``"build"`` /
                         ``"test"`` / ``"infra"`` /
                         ``"script"`` / etc.).
        :param envelope_inputs: Caller-facing inputs the M2
                                dispatcher copies into the
                                Layer-5 job envelope.
        :param annotations: Free-form metadata persisted on
                            :class:`PipelineStepRun.inputs` for
                            diagnostics.
    """
    job_kind: str
    envelope_inputs: Mapping[str, Any] = field(default_factory=dict)
    annotations: Mapping[str, Any] = field(default_factory=dict)


class PipelineStepKindProtocol(FactoryProtocolBase):
    """
        Contract for ``pipeline_step_kind`` extensions. M1
        in-tree references cover ``build`` / ``test`` /
        ``script``; ``infra`` and ``artifact-promote`` land in
        M3 once their owning features ship.
    """

    factory_protocol_name: str = "pipeline_step_kind"
    protocol_schema_version: int = 1

    @classmethod
    def kind_name(cls) -> str:
        """
            Stable identifier matching the ``kind`` field on a
            :class:`StepSpec`.
        """
        raise NotImplementedError("Subclasses must implement kind_name")

    @classmethod
    def validate_inputs(
            cls,
            *,
            inputs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        """
            Validate ``inputs`` against the kind's schema.
            Returns ``(True, ())`` on success and
            ``(False, ("reason1", "reason2", ...))`` otherwise.
            The framework aggregates every kind's issues into a
            single :class:`PipelineDocumentInvalidError`.
        """
        raise NotImplementedError("Subclasses must implement validate_inputs")

    @classmethod
    def produce_jobs(
            cls,
            *,
            project_id: str,
            run_id: str,
            stage_id: str,
            step_id: str,
            inputs: Mapping[str, Any]
        ) -> List[JobProduction]:
        """
            Translate the step into one or more Layer-5 jobs.
        """
        raise NotImplementedError("Subclasses must implement produce_jobs")
