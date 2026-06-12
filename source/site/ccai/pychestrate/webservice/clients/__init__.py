"""
.. module:: clients
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase 2 Client & Pod Plane — client registry + enrollment M1.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.clients.enrollment import (
    register_builtin_extensions as enrollment_register,
)
from ccai.pychestrate.webservice.clients.registry import (
    register_builtin_extensions as registry_register,
)


def register_builtin_extensions() -> None:
    """
        Register the in-tree factory protocols and resource extensions for
        the Phase 2 client plane: enrollment token issuer, identity
        verifier, and the canonical client-attribute kinds.

        :returns: None.
    """
    registry_register()
    enrollment_register()
    return
