"""
.. module:: orchestration.pipelines.definition.canonicalization
    :synopsis: Canonical-JSON + digest helpers for pipeline documents.

The canonical-JSON form sorts keys, drops whitespace, and
materializes every field as plain Python primitives so two
documents that differ only in serialization (YAML vs JSON,
key order, trailing whitespace) hash to the same digest.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json

from typing import Any, Dict, List

from ccai.pychestrate.webservice.orchestration.pipelines.definition.parser import (
    PipelineDocument,
    StageSpec,
    StepSpec,
)


def canonicalize_document(*, document: PipelineDocument) -> str:
    """
        Render the document as canonical JSON.
    """
    payload: Dict[str, Any] = {
        "schema_version": document.schema_version,
        "name": document.name,
        "stages": [_canonical_stage(stage=s) for s in document.stages],
    }
    rtnval = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True,
    )
    return rtnval


def compute_pipeline_digest(*, document: PipelineDocument) -> str:
    """
        SHA-256 hex digest of the canonicalized document.
    """
    canonical = canonicalize_document(document=document)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest


def _canonical_stage(*, stage: StageSpec) -> Dict[str, Any]:
    rtnval = {
        "id": stage.stage_id,
        "needs": list(stage.needs),
        "when": stage.when,
        "steps": [_canonical_step(step=s) for s in stage.steps],
    }
    return rtnval


def _canonical_step(*, step: StepSpec) -> Dict[str, Any]:
    inputs_sorted: Dict[str, Any] = {
        key: step.inputs[key] for key in sorted(step.inputs.keys())
    }
    rtnval: Dict[str, Any] = {
        "id": step.step_id,
        "kind": step.kind_name,
        "inputs": inputs_sorted,
    }
    if step.uses is not None:
        rtnval["uses"] = step.uses
    return rtnval
