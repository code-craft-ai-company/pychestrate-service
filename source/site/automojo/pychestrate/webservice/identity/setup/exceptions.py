"""
.. module:: identity.setup.exceptions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Domain exceptions raised by the initial-setup wizard.

.. moduleauthor:: Automation Mojo LLC

These are the only exceptions the setup blueprint and manager raise
on the documented sad-paths. ``ConfigurationError`` (from
``automojo.errors``) and ``SemanticError`` (from
``automojo.errors``) are still used for misconfiguration and API
misuse respectively.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class SetupAlreadyCompleteError(Exception):
    """
        Raised when an operation that only makes sense during pending
        setup is invoked after :data:`InitialSetup.completed_at` has
        been stamped. Examples: re-issuing a token, completing setup
        a second time, or hitting any ``/setup/*`` route after the
        wizard has finished.
    """


class InvalidSetupTokenError(Exception):
    """
        Raised when the operator submits a token whose sha256 does
        not match the stored :data:`InitialSetup.token_hash`. The
        webservice maps this to a 401 / login-failed response.
    """


class SetupNotInitializedError(Exception):
    """
        Raised when an operation expects the setup row to already
        exist (e.g. the unlock middleware reading the row) but no row
        has been provisioned yet. This indicates the
        :func:`bootstrap_setup_state` step in the runtime bootstrap
        was skipped.
    """


__all__ = [
    "InvalidSetupTokenError",
    "SetupAlreadyCompleteError",
    "SetupNotInitializedError",
]
