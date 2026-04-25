"""
.. module:: orchestration.pipelines.definition.dag
    :synopsis: Stage-DAG builder + cycle detector + topological walker.

Pure helpers — no DB, no event bus. The pipeline service calls
:func:`build_dag` after parsing to surface cycles or missing
dependency targets before any persistence runs.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from automojo.pychestrate.webservice.orchestration.pipelines.definition.errors import (
    PipelineDagCycleError,
    PipelineDocumentInvalidError,
)
from automojo.pychestrate.webservice.orchestration.pipelines.definition.parser import (
    PipelineDocument,
)


@dataclass(frozen=True)
class StageDag:
    """
        Frozen view of the stage DAG.

        :param stage_ids: Ordered tuple of stage ids in
                          document order.
        :param dependencies: Map ``stage_id -> tuple(needs)``.
        :param topological_order: Stage ids in a valid
                                  topological order. The order
                                  is stable across runs because
                                  ties are broken on document
                                  index.
    """
    stage_ids: Tuple[str, ...]
    dependencies: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    topological_order: Tuple[str, ...] = ()


def build_dag(*, document: PipelineDocument) -> StageDag:
    """
        Build the stage DAG, validate every ``needs`` target,
        and return a :class:`StageDag` with a stable topological
        order.

        :raises: PipelineDocumentInvalidError when a ``needs``
                 target is unknown.
        :raises: PipelineDagCycleError when the dependency graph
                 has a cycle.
    """
    stage_ids: List[str] = [stage.stage_id for stage in document.stages]
    stage_index: Dict[str, int] = {}
    for index, stage_id in enumerate(stage_ids):
        stage_index[stage_id] = index

    dependencies: Dict[str, Tuple[str, ...]] = {}
    issues: List[str] = []

    for stage in document.stages:
        for need in stage.needs:
            if need not in stage_index:
                issues.append(
                    "stage '{}' needs unknown stage '{}'".format(
                        stage.stage_id, need,
                    )
                )
        dependencies[stage.stage_id] = tuple(stage.needs)

    if len(issues) > 0:
        err_lines = [
            "Pipeline DAG references {} unknown dependency target(s).".format(
                len(issues),
            ),
        ]
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise PipelineDocumentInvalidError(err_msg) from None

    topological = _kahn_topological(
        stage_ids=stage_ids,
        dependencies=dependencies,
        stage_index=stage_index,
    )
    rtnval = StageDag(
        stage_ids=tuple(stage_ids),
        dependencies=dependencies,
        topological_order=tuple(topological),
    )
    return rtnval


def _kahn_topological(
        *,
        stage_ids: List[str],
        dependencies: Dict[str, Tuple[str, ...]],
        stage_index: Dict[str, int]
    ) -> List[str]:
    """
        Stable topological sort: when multiple nodes are ready
        simultaneously, the one with the lower document index
        wins. Detects cycles.

        :raises: PipelineDagCycleError when the graph has a
                 cycle.
    """
    indegree: Dict[str, int] = {sid: 0 for sid in stage_ids}
    for sid, needs in dependencies.items():
        indegree[sid] = len(needs)

    ready: List[str] = []
    for sid in stage_ids:
        if indegree[sid] == 0:
            ready.append(sid)

    visited: List[str] = []
    while len(ready) > 0:
        # Stable: smallest document index first.
        ready.sort(key=lambda s: stage_index[s])
        current = ready.pop(0)
        visited.append(current)
        for sid in stage_ids:
            if current in dependencies.get(sid, ()):
                indegree[sid] = indegree[sid] - 1
                if indegree[sid] == 0:
                    ready.append(sid)

    if len(visited) != len(stage_ids):
        unvisited = [sid for sid in stage_ids if sid not in visited]
        err_lines = ["Pipeline DAG contains a cycle."]
        err_lines.append(
            "UNRESOLVED_STAGES: {}".format(", ".join(unvisited)),
        )
        err_msg = os.linesep.join(err_lines)
        raise PipelineDagCycleError(err_msg) from None
    return visited
