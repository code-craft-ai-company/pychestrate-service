"""
.. module:: clients
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase 2 Client & Pod Plane — client registry + enrollment M1.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.clients.enrollment import (
    register_builtin_extensions as enrollment_register,
)
from automojo.pychestrate.webservice.clients.registry import (
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
