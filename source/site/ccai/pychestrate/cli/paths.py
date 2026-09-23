"""
.. module:: cli.paths
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Where ``pyc`` keeps its configuration and cache.

.. moduleauthor:: Code Craft AI LLC

``pyc`` follows the XDG base-directory layout:

* credentials: ``$XDG_CONFIG_HOME/pychestrate/credentials``
  (``~/.config/pychestrate/credentials``), mode ``0600``;
* OpenAPI cache: ``$XDG_CACHE_HOME/pychestrate/openapi/``
  (``~/.cache/pychestrate/openapi/``).

Earlier builds used ``~/.pychestrate/credentials``, a directory the
service's own unit also writes ``server.log`` into. That file is still
read when it exists and the XDG file does not, so existing setups keep
working; new files are always written to the XDG location.
``PYC_CREDENTIALS_PATH`` and ``PYC_OPENAPI_CACHE_DIR`` override both.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from pathlib import Path
from typing import Mapping, Optional


PYC_CREDENTIALS_PATH_ENV_VAR: str = "PYC_CREDENTIALS_PATH"
PYC_OPENAPI_CACHE_DIR_ENV_VAR: str = "PYC_OPENAPI_CACHE_DIR"

XDG_CONFIG_HOME_ENV_VAR: str = "XDG_CONFIG_HOME"
XDG_CACHE_HOME_ENV_VAR: str = "XDG_CACHE_HOME"

APP_DIR_NAME: str = "pychestrate"
CREDENTIALS_FILE_NAME: str = "credentials"
OPENAPI_CACHE_DIR_NAME: str = "openapi"

#: The pre-XDG location, still read when nothing newer exists.
LEGACY_CREDENTIALS_RELATIVE_PATH: str = ".pychestrate/credentials"


def _environ(environ: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    """
        The environment to consult (tests pass their own).

        :param environ: Mapping or ``None`` for :data:`os.environ`.

        :returns: Mapping.
    """
    if environ is None:
        return os.environ
    return environ


def _home() -> Path:
    """
        The user's home directory.

        :returns: :class:`Path`.
    """
    rtnval = Path.home()
    return rtnval


def _xdg_base(*, environ: Mapping[str, str], variable: str, default_relative: str) -> Path:
    """
        Resolve an XDG base directory. Per the specification, an
        unset, empty, or relative value falls back to the default.

        :param environ: Environment mapping.
        :param variable: ``XDG_CONFIG_HOME`` or ``XDG_CACHE_HOME``.
        :param default_relative: Default under the home directory.

        :returns: Absolute :class:`Path`.
    """
    value = environ.get(variable, "")
    if len(value) > 0 and os.path.isabs(value):
        rtnval = Path(value)
        return rtnval
    rtnval = _home() / default_relative
    return rtnval


def xdg_credentials_path(*, environ: Optional[Mapping[str, str]] = None) -> Path:
    """
        The XDG credentials path (where new files are written).

        :param environ: Environment mapping (tests).

        :returns: Absolute :class:`Path`.
    """
    env = _environ(environ)
    base = _xdg_base(environ=env, variable=XDG_CONFIG_HOME_ENV_VAR, default_relative=".config")
    rtnval = base / APP_DIR_NAME / CREDENTIALS_FILE_NAME
    return rtnval


def legacy_credentials_path() -> Path:
    """
        The pre-XDG credentials path, ``~/.pychestrate/credentials``.

        :returns: Absolute :class:`Path`.
    """
    rtnval = _home() / LEGACY_CREDENTIALS_RELATIVE_PATH
    return rtnval


def resolve_credentials_path(*, environ: Optional[Mapping[str, str]] = None) -> Path:
    """
        The credentials file ``pyc`` reads: ``PYC_CREDENTIALS_PATH``
        when set; else the XDG file; else the legacy file when only it
        exists; else the XDG path (which does not exist yet).

        :param environ: Environment mapping (tests).

        :returns: Absolute :class:`Path`.
    """
    env = _environ(environ)
    override = env.get(PYC_CREDENTIALS_PATH_ENV_VAR, "")
    if len(override) > 0:
        rtnval = Path(override).expanduser().resolve()
        return rtnval

    xdg_path = xdg_credentials_path(environ=env)
    if xdg_path.is_file():
        return xdg_path
    legacy_path = legacy_credentials_path()
    if legacy_path.is_file():
        return legacy_path
    rtnval = xdg_path
    return rtnval


def resolve_writable_credentials_path(*, environ: Optional[Mapping[str, str]] = None) -> Path:
    """
        The credentials file ``pyc login`` / ``pyc config`` write to:
        the file already in use when there is one, else the XDG path.

        :param environ: Environment mapping (tests).

        :returns: Absolute :class:`Path`.
    """
    rtnval = resolve_credentials_path(environ=environ)
    return rtnval


def resolve_openapi_cache_dir(*, environ: Optional[Mapping[str, str]] = None) -> Path:
    """
        The OpenAPI cache directory: ``PYC_OPENAPI_CACHE_DIR`` when
        set, else ``$XDG_CACHE_HOME/pychestrate/openapi``.

        :param environ: Environment mapping (tests).

        :returns: Absolute :class:`Path`.
    """
    env = _environ(environ)
    override = env.get(PYC_OPENAPI_CACHE_DIR_ENV_VAR, "")
    if len(override) > 0:
        rtnval = Path(override).expanduser().resolve()
        return rtnval
    base = _xdg_base(environ=env, variable=XDG_CACHE_HOME_ENV_VAR, default_relative=".cache")
    rtnval = base / APP_DIR_NAME / OPENAPI_CACHE_DIR_NAME
    return rtnval


__all__ = [
    "PYC_CREDENTIALS_PATH_ENV_VAR",
    "PYC_OPENAPI_CACHE_DIR_ENV_VAR",
    "legacy_credentials_path",
    "resolve_credentials_path",
    "resolve_openapi_cache_dir",
    "resolve_writable_credentials_path",
    "xdg_credentials_path",
]
