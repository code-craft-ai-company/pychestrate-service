"""
.. module:: identity.flags.rules
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Rollout hashing and rule evaluation for feature flags.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib

from automojo.pychestrate.webservice.identity.flags.models import FlagContext


MAX_BASIS_POINTS: int = 10000


def compute_bucket(*, flag_key: str, bucketing_key: str) -> int:
    """
        Compute the 0..9999 bucket for a (flag_key, bucketing_key) pair.

        Uses ``sha256(flag_key || bucketing_key)`` and maps the first 8 bytes
        of the digest to a basis-points bucket. Deterministic across
        processes so rollouts are stable as long as ``flag_key`` and
        ``bucketing_key`` are stable.

        :param flag_key: Registered flag key.
        :param bucketing_key: Caller-supplied stable key.

        :returns: Integer in [0, 9999].
    """
    digest = hashlib.sha256((flag_key + "||" + bucketing_key).encode("utf-8")).digest()
    as_int = int.from_bytes(digest[:8], byteorder="big", signed=False)
    rtnval = as_int % MAX_BASIS_POINTS
    return rtnval


def evaluate_rollout(
        *,
        flag_key: str,
        context: FlagContext,
        rollout_percentage_bp: int
    ) -> bool:
    """
        Return True when the context falls within the rollout percentage.

        :param flag_key: Registered flag key.
        :param context: Evaluation context.
        :param rollout_percentage_bp: Basis points cutoff (0..10000).

        :returns: True if the bucket is inside the rollout, else False.
    """
    bucket = compute_bucket(flag_key=flag_key, bucketing_key=context.bucketing_key)
    rtnval = bucket < rollout_percentage_bp
    return rtnval
