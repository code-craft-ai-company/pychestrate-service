"""
.. module:: retention.selectors
    :synopsis: SelectorClause → predicate compiler.

The retention service receives candidate entity identifiers
plus a snapshot of attributes per entity (age, size, project,
tag set). The compiler turns a :class:`SelectorClause` into a
predicate the evaluator runs against each candidate. Each
clause field combines as AND so an empty clause matches every
candidate (the M1 behavior the existing
:func:`evaluate_policy` relies on).

The data-class-specific selectors (artifact / run_result /
log_stream / audit_record / metric_sample) wrap the same
predicate but pre-validate their per-class field sets so a
caller cannot accidentally select a metric with a tag
expression that only makes sense for an artifact. Phase-10
hardening adds per-data-class SQL projection; M2 keeps the
predicate Python-side.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, Set, Tuple

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.retention.models import SelectorClause


@dataclass(frozen=True)
class CandidateAttributes:
    """
        Per-candidate description the selector predicate
        consumes. Fields the caller does not populate default
        to neutral values (zero age, zero size, no tags, no
        project).
    """
    entity_id: str
    age_days: int = 0
    size_bytes: int = 0
    project_id: Optional[str] = None
    tags: Tuple[str, ...] = ()


SelectorPredicate = Callable[[CandidateAttributes], bool]


SUPPORTED_DATA_CLASSES: Tuple[str, ...] = (
    "artifact",
    "run_result",
    "log_stream",
    "audit_record",
    "metric_sample",
)


def compile_selector(*, selector: SelectorClause) -> SelectorPredicate:
    """
        Turn ``selector`` into a callable that returns ``True``
        when a :class:`CandidateAttributes` snapshot matches.

        Field semantics:

        * ``tag_expression`` — boolean expression evaluated
          against the candidate's ``tags`` via the existing
          tagging compiler. Empty string matches.
        * ``age_days`` — minimum age (inclusive); zero matches.
        * ``size_bytes_over`` — strict greater-than threshold;
          zero matches.
        * ``project_ids`` — intersect by membership; empty
          tuple matches.
    """
    if selector is None:
        err_lines = ["compile_selector requires a non-None selector."]
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None

    tag_predicate = _compile_tag_predicate(
        expression=selector.tag_expression,
    )
    age_threshold = max(0, int(selector.age_days))
    size_threshold = max(0, int(selector.size_bytes_over))
    allowed_projects: Set[str] = set(selector.project_ids or ())

    def _predicate(candidate: CandidateAttributes) -> bool:
        if age_threshold > 0 and int(candidate.age_days) < age_threshold:
            return False
        if size_threshold > 0 and int(candidate.size_bytes) <= size_threshold:
            return False
        if len(allowed_projects) > 0:
            if candidate.project_id is None:
                return False
            if candidate.project_id not in allowed_projects:
                return False
        if tag_predicate is not None:
            tag_set = set(candidate.tags or ())
            if tag_predicate(tag_set) is not True:
                return False
        return True

    rtnval = _predicate
    return rtnval


def compile_selector_for_data_class(
        *,
        data_class: str,
        selector: SelectorClause
    ) -> SelectorPredicate:
    """
        Validate the data class against the supported set and
        compile the selector. Used by the per-data-class
        wrappers — every wrapper resolves to the same predicate
        but carries the data-class label for future
        per-class field projection.

        :raises: SemanticError on an unsupported data class.
    """
    if data_class not in SUPPORTED_DATA_CLASSES:
        err_lines = [
            "Selector compile rejected an unsupported data_class.",
        ]
        err_lines.append("VALUE: {!r}".format(data_class))
        err_lines.append(
            "SUPPORTED: {}".format(", ".join(SUPPORTED_DATA_CLASSES)),
        )
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None
    rtnval = compile_selector(selector=selector)
    return rtnval


def _compile_tag_predicate(*, expression: str):
    """
        Compile a boolean tag expression into a predicate over
        a tag-set, deferring to the existing
        :mod:`tagging.expression` compiler. Empty / None
        expression collapses to ``None`` so the caller skips
        the tag check.
    """
    if expression is None or len(expression.strip()) == 0:
        return None
    from automojo.pychestrate.webservice.tagging.expression import (
        compile_tag_expression,
    )
    rtnval = compile_tag_expression(expression=expression)
    return rtnval
