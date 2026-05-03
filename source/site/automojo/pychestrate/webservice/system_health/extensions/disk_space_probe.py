"""
.. module:: system_health.extensions.disk_space_probe
    :synopsis: DiskSpaceHealthProbe — readiness probe over disk free space.

The probe checks ``shutil.disk_usage`` against a configurable
warning threshold (default 90% used). Reports ``FAIL`` when
used >= threshold; ``OK`` otherwise. The watched path defaults
to the working directory of the process; tests configure it
explicitly.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import shutil
import threading
import time

from datetime import datetime, timezone
from typing import Optional

from automojo.pychestrate.webservice.system_health.extensions.probe import (
    SystemHealthProbeExtension,
)
from automojo.pychestrate.webservice.system_health.registry import (
    ProbeKind,
    ProbeResult,
    ProbeStatus,
    truncate_last_error,
)


DEFAULT_WATCH_PATH: str = "."
DEFAULT_USED_FRACTION_THRESHOLD: float = 0.90


_LOCK = threading.RLock()
_WATCH_PATH: str = DEFAULT_WATCH_PATH
_USED_THRESHOLD: float = DEFAULT_USED_FRACTION_THRESHOLD


def configure(
        *,
        watch_path: Optional[str] = None,
        used_fraction_threshold: Optional[float] = None
    ) -> None:
    """
        Set the active watch path and used-fraction threshold.
        ``None`` leaves the prior value intact.
    """
    global _WATCH_PATH
    global _USED_THRESHOLD
    with _LOCK:
        if watch_path is not None:
            _WATCH_PATH = watch_path
        if used_fraction_threshold is not None:
            _USED_THRESHOLD = used_fraction_threshold
    return


def reset_for_testing() -> None:
    """
        Restore the module-level configuration defaults.
    """
    global _WATCH_PATH
    global _USED_THRESHOLD
    with _LOCK:
        _WATCH_PATH = DEFAULT_WATCH_PATH
        _USED_THRESHOLD = DEFAULT_USED_FRACTION_THRESHOLD
    return


class DiskSpaceHealthProbe(SystemHealthProbeExtension):
    """
        Readiness probe over a configured filesystem path.
        Reports ``FAIL`` when used / total >= the configured
        threshold (default 90%) and the
        ``last_error`` carries the canonical token
        ``disk_threshold_exceeded`` plus the fraction.
    """
    resource_extension_name: str = "system_health_probe"

    name: str = "disk_space"
    kind: ProbeKind = ProbeKind.READINESS
    interval_seconds: float = 30.0
    timeout_seconds: float = 1.0

    @classmethod
    def run_probe(cls) -> ProbeResult:
        with _LOCK:
            watch_path = _WATCH_PATH
            threshold = _USED_THRESHOLD
        observed_at = datetime.now(tz=timezone.utc)
        monotonic_start = time.monotonic()
        try:
            usage = shutil.disk_usage(watch_path)
        except (OSError, FileNotFoundError) as probe_err:
            elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
            rtnval = ProbeResult(
                status=ProbeStatus.FAIL,
                duration_ms=elapsed_ms,
                observed_at=datetime.now(tz=timezone.utc),
                last_error=truncate_last_error(
                    message="{}: {}".format(
                        type(probe_err).__name__, probe_err,
                    ),
                ),
            )
            return rtnval
        elapsed_ms = (time.monotonic() - monotonic_start) * 1000.0
        if usage.total <= 0:
            rtnval = ProbeResult(
                status=ProbeStatus.UNKNOWN,
                duration_ms=elapsed_ms,
                observed_at=datetime.now(tz=timezone.utc),
                last_error="disk_total_zero",
            )
            return rtnval
        used_fraction = float(usage.used) / float(usage.total)
        details = {
            "watch_path": watch_path,
            "used_fraction": used_fraction,
            "threshold": threshold,
            "total_bytes": int(usage.total),
            "used_bytes": int(usage.used),
            "free_bytes": int(usage.free),
        }
        if used_fraction >= threshold:
            rtnval = ProbeResult(
                status=ProbeStatus.FAIL,
                duration_ms=elapsed_ms,
                observed_at=datetime.now(tz=timezone.utc),
                last_error=truncate_last_error(
                    message=(
                        "disk_threshold_exceeded "
                        "used_fraction={:.4f} threshold={:.4f}".format(
                            used_fraction, threshold,
                        )
                    ),
                ),
                details=details,
            )
            return rtnval
        rtnval = ProbeResult(
            status=ProbeStatus.OK,
            duration_ms=elapsed_ms,
            observed_at=datetime.now(tz=timezone.utc),
            details=details,
        )
        return rtnval
