"""
.. module:: extensions.resource_extension
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ResourceExtension — set-of-kinds extension point base class.

.. moduleauthor:: Code Craft AI LLC

Resource extensions form a *set of kinds* — in contrast to factory
protocols which form a *chain of overrides*. Each :class:`ResourceExtension`
subclass declares a category (permission keys, audit event types, role
presets, pod member kinds, ...) and implementations subclass it to
contribute a concrete kind. The registry iterates direct subclasses; there
is no PRECEDENCE semantics.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar


class ResourceExtension:
    """
        Base class that declares a category of discoverable resource kinds.
    """

    resource_extension_name: ClassVar[str] = ""
