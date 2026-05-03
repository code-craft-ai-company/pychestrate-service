"""
.. module:: persistence
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase 1 declarative base + repository / unit-of-work helpers.

.. moduleauthor:: Automation Mojo LLC

Public surface (M2):

* :class:`PychestratePhase1Base` — the SQLAlchemy declarative
  base every Phase-1 model attaches to.
* :class:`Repository` — generic load / load_many / save /
  delete helper with optimistic concurrency.
* :func:`unit_of_work` — transaction context manager with
  nested-savepoint support.
* Errors: :class:`PersistenceError`,
  :class:`StaleEntityError`,
  :class:`EntityNotFoundError`,
  :class:`UnitOfWorkMisuseError`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.persistence.exceptions import (
    EntityNotFoundError,
    PersistenceError,
    StaleEntityError,
    UnitOfWorkMisuseError,
)
from automojo.pychestrate.webservice.persistence.repository import (
    Repository,
)
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.persistence.uow import (
    reset_for_testing as reset_uow_for_testing,
    unit_of_work,
)
