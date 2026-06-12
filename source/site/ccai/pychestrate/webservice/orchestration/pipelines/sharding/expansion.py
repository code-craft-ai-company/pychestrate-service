"""
.. module:: orchestration.pipelines.sharding.expansion
    :synopsis: Matrix-spec primitives — IO shapes, canonical JSON,
               shard-id derivation.

The shard id is a 16-char hex prefix of the SHA-256 of the
canonicalized dimension-value mapping. The canonical JSON form
is sorted-keys, no whitespace, UTF-8 encoded — identical input
matrices produce identical shard ids across hosts and python
versions.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json
import os

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ccai.pychestrate.webservice.orchestration.pipelines.sharding.errors import (
    MatrixSpecInvalidError,
)


SHARD_ID_HEX_LEN: int = 16


@dataclass(frozen=True)
class MatrixDimensionFilter:
    """
        Dimension-value filter used by ``includes`` / ``excludes``.

        ``values`` maps a subset of dimension names onto exact
        values; a candidate dimension-tuple matches the filter
        when every key in ``values`` agrees. ``includes`` widens
        the set ``excludes`` narrows.
    """
    values: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MatrixSpec:
    """
        Caller-provided matrix specification.

        :param dimensions: Dimension name → list of allowed
                           values. Each list must be non-empty.
        :param includes: Optional hand-crafted combinations
                         outside the cartesian product.
        :param excludes: Optional combinations to drop from the
                         cartesian product.
    """
    dimensions: Dict[str, List[str]] = field(default_factory=dict)
    includes: List[MatrixDimensionFilter] = field(default_factory=list)
    excludes: List[MatrixDimensionFilter] = field(default_factory=list)


def canonicalize_dimension_values(*, dimension_values: Dict[str, str]) -> str:
    """
        Render a single dimension-tuple as canonical JSON
        (sorted keys, no whitespace).
    """
    rtnval = json.dumps(
        dimension_values, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True,
    )
    return rtnval


def canonicalize_matrix_spec(*, matrix_spec: MatrixSpec) -> str:
    """
        Render the entire :class:`MatrixSpec` as canonical JSON.
        The output is suitable for hashing into the
        ``matrix_spec_canonical_sha256`` column on
        :class:`ShardSet`.
    """
    payload = {
        "dimensions": {
            name: list(values)
            for name, values in sorted(matrix_spec.dimensions.items())
        },
        "includes": [
            dict(sorted(flt.values.items()))
            for flt in matrix_spec.includes
        ],
        "excludes": [
            dict(sorted(flt.values.items()))
            for flt in matrix_spec.excludes
        ],
    }
    rtnval = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True,
    )
    return rtnval


def matrix_spec_sha256(*, matrix_spec: MatrixSpec) -> str:
    """
        SHA-256 hex digest of the canonical matrix spec.
    """
    canonical = canonicalize_matrix_spec(matrix_spec=matrix_spec)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest


def compute_shard_id(*, dimension_values: Dict[str, str]) -> str:
    """
        Derive the 16-char hex shard id for a single
        dimension-tuple. Identical input produces an identical
        id across hosts and python versions.
    """
    canonical = canonicalize_dimension_values(
        dimension_values=dimension_values,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    rtnval = digest[:SHARD_ID_HEX_LEN]
    return rtnval


def validate_matrix_spec(*, matrix_spec: MatrixSpec) -> None:
    """
        Reject empty / malformed matrix specs at the boundary
        before any expansion runs.

        :raises: MatrixSpecInvalidError.
    """
    if matrix_spec.dimensions is None or len(matrix_spec.dimensions) == 0:
        err_lines = ["MatrixSpec.dimensions must be non-empty."]
        err_msg = os.linesep.join(err_lines)
        raise MatrixSpecInvalidError(err_msg) from None

    for name, values in matrix_spec.dimensions.items():
        if name is None or len(name) == 0:
            err_lines = ["MatrixSpec.dimensions has an empty key."]
            err_msg = os.linesep.join(err_lines)
            raise MatrixSpecInvalidError(err_msg) from None
        if values is None or len(values) == 0:
            err_lines = ["MatrixSpec dimension has no values."]
            err_lines.append("DIMENSION: {}".format(name))
            err_msg = os.linesep.join(err_lines)
            raise MatrixSpecInvalidError(err_msg) from None
    return


def cartesian_product(
        *,
        dimensions: Dict[str, List[str]]
    ) -> List[Dict[str, str]]:
    """
        Lex-ordered cartesian product of ``dimensions``.
        Dimension names are emitted in sorted order on every
        produced tuple — callers downstream can reuse the order
        for deterministic shard-id generation.
    """
    sorted_names = sorted(dimensions.keys())
    if len(sorted_names) == 0:
        rtnval: List[Dict[str, str]] = []
        return rtnval

    accumulator: List[Dict[str, str]] = [{}]
    for name in sorted_names:
        values = list(dimensions[name])
        next_accumulator: List[Dict[str, str]] = []
        for prefix in accumulator:
            for value in values:
                extended = dict(prefix)
                extended[name] = value
                next_accumulator.append(extended)
        accumulator = next_accumulator
    return accumulator


def filter_matches(
        *,
        candidate: Dict[str, str],
        filters: List[MatrixDimensionFilter]
    ) -> bool:
    """
        Return True when at least one filter accepts ``candidate``.
        A filter accepts when every key in its ``values`` is
        present in ``candidate`` with the same value. An empty
        filter list never accepts.
    """
    if filters is None or len(filters) == 0:
        return False
    for flt in filters:
        match = True
        for key, value in flt.values.items():
            existing = candidate.get(key, None)
            if existing != value:
                match = False
                break
        if match is True:
            return True
    return False


def apply_includes_excludes(
        *,
        candidates: List[Dict[str, str]],
        includes: List[MatrixDimensionFilter],
        excludes: List[MatrixDimensionFilter]
    ) -> List[Dict[str, str]]:
    """
        Apply includes + excludes to a cartesian-product output.

        Includes-only specs add hand-crafted tuples that are not
        in the cartesian product. Excludes-only specs drop
        tuples from the cartesian product. Order:

        1. Drop every candidate that matches any exclude.
        2. Append every include filter (rendered as a fully-
           specified dimension tuple) that is not already in the
           result and does not match an exclude.

        Includes that omit some dimensions are rejected — the
        M1 surface insists on full dimension tuples for
        includes.
    """
    survivors: List[Dict[str, str]] = []
    for candidate in candidates:
        if filter_matches(candidate=candidate, filters=excludes) is True:
            continue
        survivors.append(candidate)

    seen: List[str] = [
        canonicalize_dimension_values(dimension_values=row)
        for row in survivors
    ]

    if includes is None:
        return survivors

    for incl in includes:
        canonical_incl = canonicalize_dimension_values(
            dimension_values=incl.values,
        )
        if canonical_incl in seen:
            continue
        if filter_matches(
                candidate=incl.values, filters=excludes,
            ) is True:
            continue
        survivors.append(dict(incl.values))
        seen.append(canonical_incl)
    return survivors


def parallel_group_for(*, dimension_values: Dict[str, str]) -> str:
    """
        Hard-wired M1 grouping: every shard sits in the
        ``"default"`` parallel group. M2 swaps in a
        strategy-supplied grouping function when grouped
        reassembly lands.
    """
    rtnval = "default"
    return rtnval


def assign_sequence_in_group(
        *,
        candidates: List[Dict[str, str]]
    ) -> List[Tuple[Dict[str, str], str, int]]:
    """
        Assign a stable lexicographic sequence inside each
        parallel group. Returns a list of
        ``(dimension_values, parallel_group, sequence_in_group)``
        triples.
    """
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for candidate in candidates:
        group = parallel_group_for(dimension_values=candidate)
        bucket = grouped.setdefault(group, [])
        bucket.append(candidate)

    rtnval: List[Tuple[Dict[str, str], str, int]] = []
    for group, members in grouped.items():
        members.sort(
            key=lambda d: canonicalize_dimension_values(dimension_values=d),
        )
        for index, member in enumerate(members):
            rtnval.append((member, group, index))
    return rtnval
