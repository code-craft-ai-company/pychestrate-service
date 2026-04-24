"""
.. module:: extensions.phase5_bootstrap
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Register the in-tree Phase-3 (Layer-5) extensions at startup.

.. moduleauthor:: Automation Mojo LLC

Naming: ``phaseN`` files correspond to spec *layers* (``phase5`` →
Layer 5 — the job-execution plane), matching the pattern established
by :mod:`phase1_bootstrap` / :mod:`phase2_bootstrap` /
:mod:`phase3_bootstrap`. Operator callers run
:func:`bootstrap_phase1_runtime` + ``phase2`` + ``phase3`` +
:func:`bootstrap_phase5_runtime` in sequence at service start.

M1 ships one registration: :class:`FifoDispatchStrategy` under the
``dispatch_strategy`` factory protocol. ``5-run-state-machine`` and
``5-job-envelope`` do not need registration here because they do not
own factory protocols; their startup requirements are covered by
:func:`install_envelope_signer` and in-code side-effect model
imports.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.jobs.dispatch import (
    register_builtin_extensions as dispatch_register,
)

# Side-effect imports so Layer-5 model tables attach to the metadata.
from automojo.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.dispatch.receipt import models as _dispatch_receipt_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from automojo.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401


SessionFactory = Callable[[], DbSession]


@dataclass(frozen=True)
class Phase5BootstrapConfig:
    """
        Operator-supplied Phase-5 bootstrap configuration.

        :param session_factory: Optional session factory reserved
                                for future Layer-5 bus subscribers
                                (progress ingest, result watcher).
                                M1 does not consume it but
                                accepting the parameter keeps the
                                config shape forward-compatible.
    """
    session_factory: Optional[SessionFactory]


def register_phase5_builtin_extensions() -> None:
    """
        Register every in-tree Layer-5 factory implementation.

        :returns: None.
    """
    dispatch_register()
    return


def bootstrap_phase5_runtime(*, config: Phase5BootstrapConfig) -> None:
    """
        Register Layer-5 extensions. M1 has no background tasks or
        bus subscribers to wire; future M2 work (progress / result
        ingest) extends this function.

        :param config: Caller-supplied
                       :class:`Phase5BootstrapConfig`.

        :returns: None.
    """
    register_phase5_builtin_extensions()
    _ = config  # reserved for M2+ subscriber wiring
    return
