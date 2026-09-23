"""
.. module:: jobs.dispatch
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Layer-5 JobDispatcher — build envelope + transmit + record attempt.

.. moduleauthor:: Code Craft AI LLC

Public surface:

* :class:`JobDispatcher` — dispatch facade (:mod:`.dispatcher`).
* :class:`DispatchRequestInputs` — caller-supplied IO shape.
* :class:`DispatchOutcome` — returned from :meth:`JobDispatcher.dispatch`.
* :class:`ClientTransportProtocol` + :class:`InMemoryTransport` —
  transport protocol + in-process test impl (:mod:`.transport_adapter`).
* :class:`DispatchStrategyProtocol` + :class:`FifoDispatchStrategy` —
  strategy protocol + default impl (:mod:`.factories`).
* :func:`register_builtin_extensions` — seed the factory registry.
* :class:`DispatchAttempt` — archive row (:mod:`.models`).
* Exception hierarchy: :class:`DispatchError`, :class:`DispatchNoCandidatesError`,
  :class:`DispatchTransportError`.

M1 wires build-envelope → transmit → record-attempt into a single
happy-path call; M2 adds run-state hand-off, ack timers, and the
backoff queue.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.jobs.dispatch.dispatcher import (
    DispatchOutcome,
    DispatchRequestInputs,
    JobDispatcher,
)
from ccai.pychestrate.webservice.jobs.dispatch.errors import (
    DispatchError,
    DispatchNoCandidatesError,
    DispatchSigningUnavailableError,
    DispatchTransportError,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.fifo import (
    FifoDispatchStrategy,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchStrategyProtocol,
)
from ccai.pychestrate.webservice.jobs.dispatch.models import DispatchAttempt
from ccai.pychestrate.webservice.jobs.dispatch.transport_adapter import (
    ClientTransportProtocol,
    InMemoryTransport,
    TransportCall,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree :class:`DispatchStrategyProtocol`
        implementations. Called from the service bootstrap (Phase-3
        register chain). M1 ships only :class:`FifoDispatchStrategy`;
        M2 adds ``StickyPodDispatchStrategy`` + external operator
        packs.

        :returns: None.
    """
    register_factory_implementation(implementation=FifoDispatchStrategy)
    return
