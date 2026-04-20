"""
.. module:: security.auth.pepper_loader
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Password pepper loader for local credential verification.

.. moduleauthor:: Automation Mojo LLC

The local credential pepper is loaded once at service startup from
``1-secrets-vault`` under ``system:auth.local.password_pepper`` and held
in a process-wide holder that :func:`local_flow.verify_local_credentials`
reads at hash time. This mirrors the KEK loader pattern so the credential
path never hits the RBAC evaluator for its own infrastructure.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Optional

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes


PEPPER_SECRET_REF: str = "system:auth.local.password_pepper"


_ACTIVE_PEPPER: Optional[SecretBytes] = None


def set_active_pepper(*, pepper: SecretBytes) -> None:
    """
        Register the active pepper for the process.

        :param pepper: The :class:`SecretBytes` returned by a successful
                       ``secrets_service.read_secret`` call against
                       :data:`PEPPER_SECRET_REF`.

        :returns: None.
    """
    global _ACTIVE_PEPPER
    _ACTIVE_PEPPER = pepper
    return


def get_active_pepper() -> SecretBytes:
    """
        Return the active pepper handle.

        :returns: The :class:`SecretBytes` wrapping the pepper bytes.
        :raises: ConfigurationError when no pepper has been loaded.
    """
    if _ACTIVE_PEPPER is None:
        raise ConfigurationError(
            "No active password pepper is loaded. Call set_active_pepper(...) "
            "during service bootstrap before local credential verification "
            "is invoked."
        )
    rtnval = _ACTIVE_PEPPER
    return rtnval


def reset_active_pepper_for_testing() -> None:
    """
        Clear the active pepper. Test-only helper.

        :returns: None.
    """
    global _ACTIVE_PEPPER
    _ACTIVE_PEPPER = None
    return
