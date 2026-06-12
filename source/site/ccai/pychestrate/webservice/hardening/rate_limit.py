"""
.. module:: hardening.rate_limit
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: In-process token-bucket rate limiter.

.. moduleauthor:: Code Craft AI LLC

A tiny in-process limiter that services call before starting an
operation. The limiter keys each bucket by ``(scope_name, scope_key)``
(e.g. ``("project.create.session", "<session-id>")``). When the bucket
is empty the caller should abort with HTTP 429 or the equivalent.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import threading
import time

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class _Bucket:
    """
        Internal token-bucket state.
    """
    capacity: int
    refill_per_second: float
    tokens: float
    last_refill: float


class RateLimitExceeded(Exception):
    """
        Raised when the caller exhausts the bucket. The ``retry_after_ms``
        attribute tells callers how long to wait before retrying.
    """

    def __init__(self, message: str, retry_after_ms: int) -> None:
        super().__init__(message)
        self.retry_after_ms: int = retry_after_ms
        return


_LOCK = threading.RLock()
_BUCKETS: Dict[Tuple[str, str], _Bucket] = {}


def acquire(
        *,
        scope_name: str,
        scope_key: str,
        capacity: int,
        refill_per_second: float
    ) -> None:
    """
        Consume one token from the ``(scope_name, scope_key)`` bucket or
        raise :class:`RateLimitExceeded`.

        :param scope_name: Logical bucket name, e.g. ``project.create.session``.
        :param scope_key: Bucket key (session id, IP, user id).
        :param capacity: Max tokens.
        :param refill_per_second: Steady-state refill rate.

        :raises: RateLimitExceeded
    """
    now = time.monotonic()
    key = (scope_name, str(scope_key))

    with _LOCK:
        bucket = _BUCKETS.get(key, None)
        if bucket is None:
            bucket = _Bucket(
                capacity=capacity,
                refill_per_second=float(refill_per_second),
                tokens=float(capacity),
                last_refill=now,
            )
            _BUCKETS[key] = bucket
        else:
            elapsed = now - bucket.last_refill
            if elapsed > 0.0:
                refill = elapsed * bucket.refill_per_second
                bucket.tokens = min(float(bucket.capacity), bucket.tokens + refill)
                bucket.last_refill = now

        if bucket.tokens < 1.0:
            deficit = 1.0 - bucket.tokens
            seconds_to_wait = deficit / bucket.refill_per_second if bucket.refill_per_second > 0.0 else 60.0
            retry_after_ms = int(seconds_to_wait * 1000.0)
            raise RateLimitExceeded(
                message="Rate limit exceeded for {}:{}".format(scope_name, scope_key),
                retry_after_ms=retry_after_ms,
            )

        bucket.tokens -= 1.0

    return


def reset_for_testing() -> None:
    """
        Clear every bucket. Test-only.
    """
    with _LOCK:
        _BUCKETS.clear()
    return
