"""
.. module:: extensions.factory_protocol
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FactoryProtocolBase — named-behavior extension point base class.

.. moduleauthor:: Automation Mojo LLC

Pychestrate factory protocols follow the ``automojo-extension`` design.
A :class:`FactoryProtocolBase` subclass declares a contract identified by
``factory_protocol_name``; concrete implementations inherit the protocol
and set a numeric :attr:`PRECEDENCE` (lower = higher priority).
Consumers select an implementation through the registry exposed by
:mod:`automojo.pychestrate.webservice.extensions.registry`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar


class FactoryProtocolBase:
    """
        Base class that declares a named extension protocol.

        Subclasses declare:
        - ``factory_protocol_name``: the canonical protocol name.
        - ``protocol_schema_version``: integer contract version. Bumped whenever
          the declared classmethod surface changes in an incompatible way.

        Concrete implementations further set :attr:`PRECEDENCE` to establish
        ordering across multiple implementations of the same protocol.
    """

    factory_protocol_name: ClassVar[str] = ""
    protocol_schema_version: ClassVar[int] = 1
    PRECEDENCE: ClassVar[int] = 1000
