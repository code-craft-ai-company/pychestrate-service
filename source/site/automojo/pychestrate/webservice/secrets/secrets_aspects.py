"""
.. module:: secrets.secrets_aspects
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Caller-supplied behavior knobs for secrets service calls.

.. moduleauthor:: Automation Mojo LLC

Per AGENTS.md the ``SecretsAspects`` dataclass is how callers control
secrets service behavior. No behavior-modifying decorator is used; the
service reads the aspects values directly.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from dataclasses import dataclass


class LogVerbosity(enum.Enum):
    """
        Verbosity level for secrets service log emission. NEVER exposes
        plaintext at any level.
    """
    NORMAL = "NORMAL"
    DEBUG = "DEBUG"


@dataclass(frozen=True)
class SecretsAspects:
    """
        Behavior knobs the caller supplies to secrets service functions.

        :param sync: If True, wait for durable backend confirmation before returning.
        :param timeout_seconds: Per-call deadline for backend operations.
        :param retry_budget: Number of attempts for transient backend errors.
        :param include_metadata: Return version + rotation metadata alongside bytes.
        :param log_verbosity: NORMAL | DEBUG — never exposes plaintext at any level.
    """
    sync: bool
    timeout_seconds: float
    retry_budget: int
    include_metadata: bool
    log_verbosity: LogVerbosity


def build_default_aspects() -> SecretsAspects:
    """
        Construct the default :class:`SecretsAspects` for routine callers.

        Per AGENTS.md we never use mutable defaults; callers that want
        defaults explicitly invoke this function to obtain a fresh frozen
        dataclass.

        :returns: The default :class:`SecretsAspects`.
    """
    rtnval = SecretsAspects(
        sync=True,
        timeout_seconds=5.0,
        retry_budget=3,
        include_metadata=False,
        log_verbosity=LogVerbosity.NORMAL,
    )
    return rtnval
