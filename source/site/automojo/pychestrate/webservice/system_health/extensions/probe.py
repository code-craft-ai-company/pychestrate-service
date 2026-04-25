"""
.. module:: system_health.extensions.probe
    :synopsis: SystemHealthProbeExtension resource base.

Probes contributed by extensions subclass
:class:`SystemHealthProbeExtension`. The base captures the
canonical attributes (name, kind, interval, timeout) and
declares the :meth:`run_probe` classmethod the scheduler
invokes.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar

from automojo.pychestrate.webservice.extensions.resource_extension import (
    ResourceExtension,
)
from automojo.pychestrate.webservice.system_health.registry import (
    ProbeKind,
    ProbeResult,
)


class SystemHealthProbeExtension(ResourceExtension):
    """
        Resource base for probe contributions. Concrete probes
        declare the canonical attributes as class-level
        constants and override :meth:`run_probe`.
    """

    resource_extension_name: ClassVar[str] = "system_health_probe"

    name: ClassVar[str] = ""
    kind: ClassVar[ProbeKind] = ProbeKind.READINESS
    interval_seconds: ClassVar[float] = 10.0
    timeout_seconds: ClassVar[float] = 2.0

    @classmethod
    def run_probe(cls) -> ProbeResult:
        """
            Invoke the probe and return a :class:`ProbeResult`.

            :raises: NotImplementedError when subclasses do not
                     override.
        """
        raise NotImplementedError("Subclasses must implement run_probe")
