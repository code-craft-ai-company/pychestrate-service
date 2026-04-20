"""
.. module:: persistence.schema
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Isolated SQLAlchemy declarative base for Phase 1 identity features.

.. moduleauthor:: Automation Mojo LLC

The Phase 1 layer-1 features declare their own SQLAlchemy metadata so
their tables do not collide with the legacy ``PychestrateModelBase``
tables (e.g. ``secrets``, ``secret_versions``) declared in
:mod:`automojo.pychestrate.core.orm`. When the Phase 10 cut-over retires
the legacy tables, this base either rebases onto ``PychestrateModelBase``
or becomes the authoritative base for the whole service.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy.orm import declarative_base


PychestratePhase1Base = declarative_base()
