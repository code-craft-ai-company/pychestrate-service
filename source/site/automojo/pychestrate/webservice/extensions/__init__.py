"""
.. module:: extensions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Pychestrate extension host — factory protocols and resource extensions.

.. moduleauthor:: Automation Mojo LLC

This package implements the Phase 0.5 extension host stub referenced by
Layer E (`E-extension-host`). It is the minimal registry required so the
Layer 1 features can declare their `FactoryProtocolBase` subclasses and
`ResourceExtension` bases and register in-tree reference implementations
without pulling in filesystem scanning. Extension pack discovery on
``sys.path`` is intentionally deferred to a later milestone; registration
here is explicit via :func:`register_factory_implementation` and
:func:`register_resource_extension`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"
