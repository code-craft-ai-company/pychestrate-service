"""
.. module:: ingest.result.classification
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: RunFailureClassification — why a run ended the way it did.

.. moduleauthor:: Code Craft AI LLC

:class:`jobs.run.state.enums.TerminalOutcome` answers "did this run
succeed" with five values, only one of which -- ``failure`` -- covers
everything that went wrong inside the job. That is deliberately
coarse: the outcome set drives state transitions and must stay small.

It is also not enough for triage. The pod client can tell a run that
blew its wall-clock cap apart from one whose ``testbase`` binary was
missing apart from one whose tests genuinely failed -- the executors
distinguish all three internally -- but with only ``failure`` to
report, all three arrive at the service as the same thing and an
operator has to read prose to tell them apart.

This enum is the structured carrier for that distinction. It rides on
the ``ResultManifest`` under ``extras.failure_classification`` and is
recorded alongside ``terminal_outcome``, so "the pod was missing a
binary" is queryable rather than buried in a ``notes`` string.

Why ``extras`` and not a top-level manifest field: the pod client
reaches the service exclusively through the generated
``automojo-restclient-pychestrate`` package and is forbidden from
hand-rolling HTTP. The generated ``Resultmanifest`` model has no
``failure_classification`` field, but it does carry ``extras`` as a
``Dict[str, Any]``, so ``extras`` is the only structured member the
client can populate before the REST client is regenerated. The
OpenAPI document declares the member explicitly and constrains it to
this enum, so it is a real contract rather than an untyped bag.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from typing import Any, Dict, Optional


class RunFailureClassification(str, enum.Enum):
    """
        Why a run reached the terminal outcome it did. Reported by
        the pod client; never inferred server-side.
    """

    #: The job exceeded the executor's wall-clock cap and the pod
    #: killed it. The job never reported a verdict of its own.
    TIMEOUT = "timeout"

    #: The binary the job needed (``testbase``, ``make``, ``git``,
    #: the infra tool) is not installed on the pod. A pod
    #: provisioning problem, not a job problem.
    EXECUTABLE_NOT_FOUND = "executable_not_found"

    #: The job ran to completion and exited non-zero. This is the
    #: ordinary "the tests failed" / "the build broke" case.
    NONZERO_EXIT = "nonzero_exit"

    #: An operator cancelled the run and the pod terminated the
    #: process tree. Pairs with ``TerminalOutcome.CANCELLED``.
    CANCELLED = "cancelled"

    #: The pod could not start the process at all for a reason other
    #: than a missing binary (permissions, fork failure, a working
    #: directory that vanished).
    LAUNCH_ERROR = "launch_error"

    #: The pod refused the job before launching anything -- an
    #: envelope missing a required field, an unresolvable project
    #: root, an unrecognized job kind.
    SETUP_ERROR = "setup_error"


#: The member of ``ResultManifest.extras`` that carries the
#: classification. Named once here so the ingest, the OpenAPI
#: document, and the client agree on the spelling.
FAILURE_CLASSIFICATION_EXTRAS_KEY: str = "failure_classification"


def normalize_failure_classification(
        *, candidate: Optional[Any]
    ) -> Optional[str]:
    """
        Coerce a reported classification to a known enum value.

        An unrecognized value is dropped rather than stored. The
        field exists so a fixed vocabulary can be queried and
        aggregated; letting arbitrary strings through would turn it
        back into the free-form prose it replaces. The reported
        outcome is unaffected either way -- the classification is
        supplementary detail.

        :param candidate: Raw value read from the manifest.

        :returns: The canonical classification string, or ``None``
                  when absent or unrecognized.
    """
    if candidate is None:
        rtnval = None
        return rtnval

    if not isinstance(candidate, str):
        rtnval = None
        return rtnval

    text = candidate.strip().lower()
    if len(text) == 0:
        rtnval = None
        return rtnval

    for member in RunFailureClassification:
        if member.value == text:
            rtnval = member.value
            return rtnval

    rtnval = None
    return rtnval


def failure_classification_from_manifest(
        *, manifest: Dict[str, Any]
    ) -> Optional[str]:
    """
        Read ``extras.failure_classification`` off a posted
        ``ResultManifest``.

        :param manifest: The decoded ``ResultManifest`` dict.

        :returns: The canonical classification string, or ``None``
                  when the manifest carries none.
    """
    extras = manifest.get("extras", None)
    if not isinstance(extras, dict):
        rtnval = None
        return rtnval

    raw = extras.get(FAILURE_CLASSIFICATION_EXTRAS_KEY, None)
    rtnval = normalize_failure_classification(candidate=raw)
    return rtnval


__all__ = [
    "FAILURE_CLASSIFICATION_EXTRAS_KEY",
    "RunFailureClassification",
    "failure_classification_from_manifest",
    "normalize_failure_classification",
]
