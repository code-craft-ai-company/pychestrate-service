"""
.. module:: jobs.results.path_builder
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Deterministic path naming for per-run result locations.

.. moduleauthor:: Code Craft AI LLC

The path template — ``<project_slug>/results/<yyyy>/<mm>/<dd>/<job_type>/<run_id>``
— is a deliberate trade between human navigability (year-month-day
groups make ad-hoc browsing feasible) and uniqueness
(``run_id`` is a UUID so collisions across same-day runs are
impossible). Each component is sanitized through
:func:`canonicalize_component` so caller-supplied strings cannot
escape into parent directories or smuggle shell characters.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re

from datetime import datetime, timezone

from ccai.pychestrate.webservice.jobs.results.errors import (
    PathComponentInvalidError,
)


_SAFE_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")
MAX_COMPONENT_LENGTH: int = 96


def canonicalize_component(*, raw: str) -> str:
    """
        Sanitize a single path component.

        Lower-cases, collapses any run of unsafe characters into a
        single ``-``, strips leading / trailing ``-``, and refuses
        empty results.

        :param raw: Caller-supplied component string.

        :returns: Canonicalized component.
        :raises: PathComponentInvalidError when the result is
                 empty or longer than
                 :data:`MAX_COMPONENT_LENGTH`.
    """
    if raw is None:
        err_msg = "Path component is None"
        raise PathComponentInvalidError(err_msg) from None
    lowered = raw.strip().lower()
    sanitized = _SAFE_PATTERN.sub("-", lowered).strip("-")
    if len(sanitized) == 0:
        err_lines = ["Path component canonicalizes to empty."]
        err_lines.append("RAW: {}".format(raw))
        err_msg = os.linesep.join(err_lines)
        raise PathComponentInvalidError(err_msg) from None
    if len(sanitized) > MAX_COMPONENT_LENGTH:
        err_lines = ["Path component is too long."]
        err_lines.append("LENGTH: {}".format(len(sanitized)))
        err_lines.append("MAX: {}".format(MAX_COMPONENT_LENGTH))
        err_msg = os.linesep.join(err_lines)
        raise PathComponentInvalidError(err_msg) from None
    return sanitized


def build_canonical_prefix(
        *,
        project_slug: str,
        job_type: str,
        run_id: str,
        when: datetime
    ) -> str:
    """
        Build the canonical per-run results prefix.

        Format: ``<project_slug>/results/<yyyy>/<mm>/<dd>/<job_type>/<run_id>``

        :param project_slug: Project slug (sanitized).
        :param job_type: Job-type string (sanitized).
        :param run_id: Run UUID — used verbatim after lower-casing
                       since UUIDs are already filesystem-safe.
        :param when: Allocation timestamp (UTC). The y/m/d
                     components come from this — callers pass the
                     same ``utc_now()`` they intend to record on
                     the allocation row.

        :returns: Canonical prefix, slash-separated.
    """
    project_part = canonicalize_component(raw=project_slug)
    job_part = canonicalize_component(raw=job_type)
    run_part = canonicalize_component(raw=run_id)

    when_utc = when
    if when_utc.tzinfo is None:
        when_utc = when_utc.replace(tzinfo=timezone.utc)
    when_utc = when_utc.astimezone(timezone.utc)

    rtnval = "{}/results/{:04d}/{:02d}/{:02d}/{}/{}".format(
        project_part,
        when_utc.year,
        when_utc.month,
        when_utc.day,
        job_part,
        run_part,
    )
    return rtnval
