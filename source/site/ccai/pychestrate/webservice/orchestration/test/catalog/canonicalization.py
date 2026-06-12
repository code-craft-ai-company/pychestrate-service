"""
.. module:: orchestration.test.catalog.canonicalization
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Canonical JSON encoding + SHA-256 digest for catalog rows.

.. moduleauthor:: Code Craft AI LLC

A catalog entry's digest is recomputed on every upsert so a
re-import that produces semantically identical content does not
churn the digest. The encoding mirrors the JCS subset
:mod:`jobs.envelope.canonical` uses so cross-feature digest
comparisons remain meaningful.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json

from typing import Any, Mapping

from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import (
    ImporterEntryPayload,
)


def canonicalize_entry(*, payload: ImporterEntryPayload) -> bytes:
    """
        Produce the canonical bytes for digest computation.

        :param payload: Importer-supplied payload.

        :returns: UTF-8 canonical JSON bytes.
    """
    body = {
        "entry_key": payload.entry_key,
        "display_name": payload.display_name,
        "description": payload.description,
        "required_capability_tags": sorted(payload.required_capability_tags),
        "param_schema": _normalize(value=payload.param_schema),
        "raw_metadata": _normalize(value=payload.raw_metadata),
    }
    rtnval = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return rtnval


def compute_digest(*, canonical_bytes: bytes) -> str:
    """
        Return the lowercase-hex SHA-256 digest of
        ``canonical_bytes``.
    """
    rtnval = hashlib.sha256(canonical_bytes).hexdigest()
    return rtnval


def _normalize(*, value: Any) -> Any:
    """
        Recursively materialize ``Mapping`` and tuple instances
        into JSON-serializable equivalents (dict / list).
    """
    if isinstance(value, Mapping):
        rtnval = {key: _normalize(value=val) for key, val in value.items()}
        return rtnval
    if isinstance(value, (list, tuple)):
        rtnval = [_normalize(value=item) for item in value]
        return rtnval
    return value
