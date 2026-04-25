"""
.. module:: ops.release.release_aspects
    :synopsis: ReleaseAspects dataclass + default builder.

The Aspects pattern packages caller-supplied behavior knobs —
sync vs async, timeouts, cascading rollback, bake-window
bypass, log verbosity — into a single immutable bundle. The
service entry points accept exactly one ``aspects`` parameter
in addition to the per-call data parameters; this keeps the
signature stable as new behaviors land in M2 / M3.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from dataclasses import dataclass


class LogVerbosity(str, enum.Enum):
    """
        Log verbosity levels permitted in a release path. The
        signer never logs key bytes regardless of the chosen
        verbosity.
    """
    NORMAL = "normal"
    DEBUG = "debug"


@dataclass(frozen=True)
class ReleaseAspects:
    """
        Operator-supplied behavior bundle for a release call.

        :param sync: Wait for signer + persistence + event
                     emit to settle before returning.
        :param timeout_seconds: Per-call deadline applied to
                                signer / verify / policy
                                lookups.
        :param include_cascading_agent_rollback: When set on a
                                                 ``rollback_channel``
                                                 call against a
                                                 SERVICE release,
                                                 also roll the
                                                 AGENT release on
                                                 the same channel.
        :param bypass_bake_window: When set on a
                                   ``promote_release`` call,
                                   skip the bake-window check.
                                   Honored only when the caller
                                   carries
                                   ``system:release.bypass_bake``.
        :param log_verbosity: Logging level for the call.
    """
    sync: bool
    timeout_seconds: float
    include_cascading_agent_rollback: bool
    bypass_bake_window: bool
    log_verbosity: LogVerbosity


def build_default_release_aspects() -> ReleaseAspects:
    """
        Return the default aspects for routine release
        operations: synchronous, 30 s deadline, no cascading
        rollback, no bake bypass, normal logging.

        :returns: A frozen :class:`ReleaseAspects`.
    """
    rtnval = ReleaseAspects(
        sync=True,
        timeout_seconds=30.0,
        include_cascading_agent_rollback=False,
        bypass_bake_window=False,
        log_verbosity=LogVerbosity.NORMAL,
    )
    return rtnval
