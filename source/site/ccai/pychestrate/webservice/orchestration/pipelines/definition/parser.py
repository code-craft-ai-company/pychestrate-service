"""
.. module:: orchestration.pipelines.definition.parser
    :synopsis: YAML/JSON parser + schema validation for pipeline documents.

The M1 parser accepts YAML or JSON document bytes (UTF-8) and
returns a typed :class:`PipelineDocument`. Every aggregate
violation is collected before raising — callers see every
problem in a single ``PipelineDocumentInvalidError`` rather
than an iterative parse-fix-reparse loop.

JSON-Schema-style validation lives inline (no external schema
file at M1) so the codebase has a single source of truth for
the document shape.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

from ccai.pychestrate.webservice.orchestration.pipelines.definition.errors import (
    PipelineDocumentInvalidError,
)


SCHEMA_VERSION_DEFAULT: int = 1
PIPELINE_NAME_MAX_LEN: int = 128
STAGE_ID_MAX_LEN: int = 128
STEP_ID_MAX_LEN: int = 128
WHEN_CLAUSE_ALLOWED: Tuple[str, ...] = ("succeeded", "failed", "always")
DEFAULT_WHEN_CLAUSE: str = "succeeded"
DOCUMENT_MAX_BYTES: int = 1 * 1024 * 1024


@dataclass(frozen=True)
class StepSpec:
    """
        Frozen-dataclass view of a single step.

        :param step_id: Document-declared identifier.
        :param kind_name: Registered
                          :class:`PipelineStepKindProtocol`
                          name. Built-ins are ``"build"`` /
                          ``"test"`` / ``"script"``.
        :param uses: Optional reference for extension step
                     kinds; ignored for built-ins at M1.
        :param inputs: Free-form input dict. The step kind owns
                       the schema validation of this payload.
    """
    step_id: str
    kind_name: str
    uses: Optional[str] = None
    inputs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageSpec:
    """
        Frozen-dataclass view of a stage.
    """
    stage_id: str
    needs: Tuple[str, ...] = ()
    when: str = DEFAULT_WHEN_CLAUSE
    steps: Tuple[StepSpec, ...] = ()


@dataclass(frozen=True)
class PipelineDocument:
    """
        Top-level pipeline document AST.

        :param schema_version: Document schema version; M1
                               supports version ``1`` only.
        :param name: Caller-supplied display name.
        :param stages: Ordered tuple of :class:`StageSpec`.
    """
    schema_version: int
    name: str
    stages: Tuple[StageSpec, ...] = ()


def parse_document(
        *,
        document_bytes: bytes,
        filename: str
    ) -> PipelineDocument:
    """
        Parse + validate ``document_bytes`` into a typed
        :class:`PipelineDocument`. Decides between YAML and JSON
        by filename suffix; falls back to YAML when the suffix
        is unknown — every JSON document is also valid YAML.

        :raises: PipelineDocumentInvalidError on any
                 size / parse / schema violation. Every problem
                 is collected before raising.
    """
    issues: List[str] = []

    if document_bytes is None or len(document_bytes) == 0:
        issues.append("document is empty")
        _raise_with_issues(filename=filename, issues=issues)

    if len(document_bytes) > DOCUMENT_MAX_BYTES:
        issues.append(
            "document exceeds size cap: {} bytes (max {} bytes)".format(
                len(document_bytes), DOCUMENT_MAX_BYTES,
            )
        )
        _raise_with_issues(filename=filename, issues=issues)

    raw_text: str
    try:
        raw_text = document_bytes.decode("utf-8")
    except UnicodeDecodeError as decode_err:
        issues.append("document is not valid UTF-8: {}".format(decode_err))
        _raise_with_issues(filename=filename, issues=issues)
        return _unreachable_document()

    parsed: Any
    parser_used: str
    if filename.lower().endswith(".json"):
        try:
            parsed = json.loads(raw_text)
            parser_used = "json"
        except json.JSONDecodeError as json_err:
            issues.append("JSON parse error: {}".format(json_err))
            _raise_with_issues(filename=filename, issues=issues)
            return _unreachable_document()
    else:
        try:
            parsed = yaml.safe_load(raw_text)
            parser_used = "yaml"
        except yaml.YAMLError as yaml_err:
            issues.append("YAML parse error: {}".format(yaml_err))
            _raise_with_issues(filename=filename, issues=issues)
            return _unreachable_document()

    if not isinstance(parsed, dict):
        issues.append(
            "document root must be a mapping; got {} (parser={})".format(
                type(parsed).__name__, parser_used,
            )
        )
        _raise_with_issues(filename=filename, issues=issues)

    rtnval = _validate_document(parsed=parsed, issues=issues)
    if len(issues) > 0:
        _raise_with_issues(filename=filename, issues=issues)
    return rtnval


def _validate_document(
        *,
        parsed: Dict[str, Any],
        issues: List[str]
    ) -> PipelineDocument:
    """
        Validate the parsed-dict shape and produce the typed
        document. Every problem is appended to ``issues`` so
        the caller can raise once.
    """
    schema_version = parsed.get("schema_version", SCHEMA_VERSION_DEFAULT)
    if not isinstance(schema_version, int):
        issues.append(
            "schema_version must be an integer; got {}".format(
                type(schema_version).__name__,
            )
        )
        schema_version = SCHEMA_VERSION_DEFAULT
    elif schema_version != 1:
        issues.append(
            "unsupported schema_version {}; M1 supports 1".format(
                schema_version,
            )
        )

    name = parsed.get("name", "")
    if not isinstance(name, str):
        issues.append(
            "name must be a string; got {}".format(type(name).__name__),
        )
        name = ""
    if len(name) == 0:
        issues.append("name must be non-empty")
    if len(name) > PIPELINE_NAME_MAX_LEN:
        issues.append(
            "name exceeds {} chars".format(PIPELINE_NAME_MAX_LEN),
        )

    stages_raw = parsed.get("stages", None)
    if stages_raw is None:
        issues.append("stages must be present")
        stages_raw = []
    if not isinstance(stages_raw, list):
        issues.append(
            "stages must be a list; got {}".format(
                type(stages_raw).__name__,
            )
        )
        stages_raw = []
    if len(stages_raw) == 0:
        issues.append("stages must contain at least one entry")

    stages: List[StageSpec] = []
    seen_stage_ids: List[str] = []
    for index, raw_stage in enumerate(stages_raw):
        stage = _validate_stage(
            raw=raw_stage,
            stage_index=index,
            seen_stage_ids=seen_stage_ids,
            issues=issues,
        )
        stages.append(stage)
        seen_stage_ids.append(stage.stage_id)

    rtnval = PipelineDocument(
        schema_version=schema_version,
        name=name,
        stages=tuple(stages),
    )
    return rtnval


def _validate_stage(
        *,
        raw: Any,
        stage_index: int,
        seen_stage_ids: List[str],
        issues: List[str]
    ) -> StageSpec:
    """
        Validate a single stage entry.
    """
    location = "stages[{}]".format(stage_index)
    if not isinstance(raw, dict):
        issues.append(
            "{} must be a mapping; got {}".format(
                location, type(raw).__name__,
            )
        )
        rtnval = StageSpec(stage_id="<invalid>")
        return rtnval

    stage_id = raw.get("id", "")
    if not isinstance(stage_id, str):
        issues.append(
            "{}.id must be a string".format(location),
        )
        stage_id = ""
    if len(stage_id) == 0:
        issues.append("{}.id must be non-empty".format(location))
    if len(stage_id) > STAGE_ID_MAX_LEN:
        issues.append(
            "{}.id exceeds {} chars".format(location, STAGE_ID_MAX_LEN),
        )
    if stage_id in seen_stage_ids:
        issues.append(
            "{}.id duplicate: '{}'".format(location, stage_id),
        )

    needs_raw = raw.get("needs", [])
    if not isinstance(needs_raw, list):
        issues.append("{}.needs must be a list".format(location))
        needs_raw = []
    needs_clean: List[str] = []
    for n_index, dep in enumerate(needs_raw):
        if not isinstance(dep, str) or len(dep) == 0:
            issues.append(
                "{}.needs[{}] must be a non-empty string".format(
                    location, n_index,
                )
            )
            continue
        needs_clean.append(dep)

    when = raw.get("when", DEFAULT_WHEN_CLAUSE)
    if not isinstance(when, str):
        issues.append("{}.when must be a string".format(location))
        when = DEFAULT_WHEN_CLAUSE
    if when not in WHEN_CLAUSE_ALLOWED:
        issues.append(
            "{}.when '{}' must be one of {}".format(
                location, when, ", ".join(WHEN_CLAUSE_ALLOWED),
            )
        )

    steps_raw = raw.get("steps", None)
    if steps_raw is None:
        issues.append("{}.steps must be present".format(location))
        steps_raw = []
    if not isinstance(steps_raw, list):
        issues.append("{}.steps must be a list".format(location))
        steps_raw = []
    if len(steps_raw) == 0:
        issues.append("{}.steps must contain at least one entry".format(location))

    seen_step_ids: List[str] = []
    steps: List[StepSpec] = []
    for s_index, raw_step in enumerate(steps_raw):
        step = _validate_step(
            raw=raw_step,
            stage_location=location,
            step_index=s_index,
            seen_step_ids=seen_step_ids,
            issues=issues,
        )
        steps.append(step)
        seen_step_ids.append(step.step_id)

    rtnval = StageSpec(
        stage_id=stage_id,
        needs=tuple(needs_clean),
        when=when,
        steps=tuple(steps),
    )
    return rtnval


def _validate_step(
        *,
        raw: Any,
        stage_location: str,
        step_index: int,
        seen_step_ids: List[str],
        issues: List[str]
    ) -> StepSpec:
    """
        Validate a single step entry.
    """
    location = "{}.steps[{}]".format(stage_location, step_index)
    if not isinstance(raw, dict):
        issues.append(
            "{} must be a mapping; got {}".format(
                location, type(raw).__name__,
            )
        )
        rtnval = StepSpec(step_id="<invalid>", kind_name="")
        return rtnval

    step_id = raw.get("id", "")
    if not isinstance(step_id, str):
        issues.append("{}.id must be a string".format(location))
        step_id = ""
    if len(step_id) == 0:
        issues.append("{}.id must be non-empty".format(location))
    if len(step_id) > STEP_ID_MAX_LEN:
        issues.append(
            "{}.id exceeds {} chars".format(location, STEP_ID_MAX_LEN),
        )
    if step_id in seen_step_ids:
        issues.append(
            "{}.id duplicate: '{}'".format(location, step_id),
        )

    kind_name = raw.get("kind", "")
    if not isinstance(kind_name, str):
        issues.append("{}.kind must be a string".format(location))
        kind_name = ""
    if len(kind_name) == 0:
        issues.append("{}.kind must be non-empty".format(location))

    uses = raw.get("uses", None)
    if uses is not None and not isinstance(uses, str):
        issues.append("{}.uses must be a string when present".format(location))
        uses = None

    inputs = raw.get("inputs", {})
    if not isinstance(inputs, dict):
        issues.append("{}.inputs must be a mapping".format(location))
        inputs = {}

    rtnval = StepSpec(
        step_id=step_id,
        kind_name=kind_name,
        uses=uses,
        inputs=dict(inputs),
    )
    return rtnval


def _raise_with_issues(*, filename: str, issues: List[str]) -> None:
    """
        Build and raise a multiline
        :class:`PipelineDocumentInvalidError`.
    """
    err_lines = [
        "Pipeline document failed validation: {} issue(s).".format(len(issues)),
    ]
    err_lines.append("FILENAME: {}".format(filename))
    for index, issue in enumerate(issues):
        err_lines.append("  [{}] {}".format(index + 1, issue))
    err_msg = os.linesep.join(err_lines)
    raise PipelineDocumentInvalidError(err_msg) from None


def _unreachable_document() -> PipelineDocument:
    """
        Sentinel value satisfying type-checkers; the call sites
        that produce this have already raised before reaching
        the return statement.
    """
    rtnval = PipelineDocument(
        schema_version=SCHEMA_VERSION_DEFAULT, name="<invalid>",
    )
    return rtnval
