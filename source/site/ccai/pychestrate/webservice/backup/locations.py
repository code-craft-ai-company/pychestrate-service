"""
.. module:: backup.locations
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Where backup archives and key bundles are written.

.. moduleauthor:: Code Craft AI LLC

Two directories, both outside the code checkout by default:

* the **backup root** (``PYCHESTRATE_BACKUP_ROOT``, default
  ``<presence_dir>/backups``) -- data archives
  (``<backup_id>.backup.tar.gz``: database snapshot + run artifacts)
  and their ``.sha256`` sidecars;
* the **key-bundle directory** (``PYCHESTRATE_BACKUP_KEYS_DIR``,
  default ``<presence_dir>/backup-keys``) -- one
  ``<backup_id>.keys.tar`` per backup holding the KEK, the password
  pepper and the other service keys. A separate directory so an
  operator can ship archives and keys to different places: a stolen
  archive alone does not decrypt the secrets it contains.

Both resolve through the :class:`PychestrateVariables` chain
(environment > ``settings.config`` > presence default). Operator
tools that run before a persona is established fall back to the
environment and the bootstrap presence-directory resolver, which
apply the same defaults.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os


ENV_BACKUP_ROOT: str = "PYCHESTRATE_BACKUP_ROOT"
ENV_BACKUP_KEYS_DIR: str = "PYCHESTRATE_BACKUP_KEYS_DIR"

DEFAULT_BACKUP_DIR_NAME: str = "backups"
DEFAULT_BACKUP_KEYS_DIR_NAME: str = "backup-keys"


def _resolve_configured_directory(
        *,
        accessor_name: str,
        env_name: str,
        default_dir_name: str
    ) -> str:
    """
        Resolve a presence-relative directory variable.

        :param accessor_name: Attribute on :class:`PychestrateVariables`.
        :param env_name: Environment variable consulted when no
                         persona is established.
        :param default_dir_name: Directory name under the presence
                                 directory used as the last resort.

        :returns: Absolute, user-expanded directory path.
    """
    from ccai.errors.exceptions import SemanticError

    configured = None
    try:
        from ccai.thisapp.wellknown import ThisApplicationSingleton
        from ccai.pychestrate.webservice.pychestrate_variables import (
            PychestrateVariablesDesc,
        )

        # Resolve against the current application instance (the
        # PychestrateVariables accessor caches the first one it saw,
        # which goes stale when a test harness replaces it), forgetting
        # any cached value so environment changes are honored.
        var_desc = getattr(PychestrateVariablesDesc, accessor_name)
        this_app = ThisApplicationSingleton()
        this_app.forget_variable(var_desc)
        configured = this_app.get_variable_value(var_desc)
    except SemanticError:
        configured = None

    if configured is None or len(str(configured)) == 0:
        from_environment = os.environ.get(env_name, "")
        if len(from_environment) > 0:
            configured = from_environment
        else:
            from ccai.pychestrate.webservice.pychestrate_presence import (
                resolve_presence_dir,
            )
            configured = os.path.join(resolve_presence_dir(argv=None), default_dir_name)

    rtnval = os.path.abspath(os.path.expanduser(str(configured)))
    return rtnval


def resolve_backup_root() -> str:
    """
        Return the directory backup archives are written to.

        :returns: Absolute directory path (not created here).
    """
    rtnval = _resolve_configured_directory(
        accessor_name="PYCHESTRATE_BACKUP_ROOT",
        env_name=ENV_BACKUP_ROOT,
        default_dir_name=DEFAULT_BACKUP_DIR_NAME,
    )
    return rtnval


def resolve_backup_keys_dir() -> str:
    """
        Return the directory key bundles are written to.

        :returns: Absolute directory path (not created here).
    """
    rtnval = _resolve_configured_directory(
        accessor_name="PYCHESTRATE_BACKUP_KEYS_DIR",
        env_name=ENV_BACKUP_KEYS_DIR,
        default_dir_name=DEFAULT_BACKUP_KEYS_DIR_NAME,
    )
    return rtnval


def ensure_private_directory(*, path: str) -> str:
    """
        Create ``path`` (and parents) if missing and restrict it to
        the service user (mode 0700): backups hold every secret the
        service can decrypt.

        :param path: Directory path.

        :returns: The path.
    """
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    rtnval = path
    return rtnval


__all__ = [
    "DEFAULT_BACKUP_DIR_NAME",
    "DEFAULT_BACKUP_KEYS_DIR_NAME",
    "ENV_BACKUP_KEYS_DIR",
    "ENV_BACKUP_ROOT",
    "ensure_private_directory",
    "resolve_backup_keys_dir",
    "resolve_backup_root",
]
