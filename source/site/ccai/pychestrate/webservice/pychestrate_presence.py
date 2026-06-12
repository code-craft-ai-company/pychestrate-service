"""
.. module:: webservice.pychestrate_presence
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bootstrap-time resolver for the pychestrate persona
               presence directory.

.. moduleauthor:: Code Craft AI LLC

The persona presence directory (``ccai.thisapp``'s
``presence_dir``) holds settings.config + all per-host application
state for pychestrate. Its value must be known BEFORE
``establish_webapp_persona`` is called -- the settings file lives
inside it, so it cannot itself be read from settings. That's a
chicken-and-egg, and the way out is a tiny module that resolves
the presence directory from inputs available at process boot, in
strict precedence:

    1. CLI flag ``--presence-dir <path>``
    2. Environment variable ``PYCHESTRATE_PRESENCE_DIR``
    3. Built-in pychestrate default ``~/pychestrate``

This module deliberately does NOT depend on
:mod:`ccai.thisapp` -- it's the bootstrap step that brings
this_app to life. Once the entrypoint has resolved the value here
and passed it to ``establish_webapp_persona(presence_dir=...)``,
every subsequent variable lookup goes through
``PersonaVariables.AM_PRESENCE_DIR`` (the canonical, this_app-
backed accessor) or other ``AppVarAccessor`` descriptors in
:mod:`ccai.pychestrate.webservice.pychestrate_variables`.

Entrypoint usage
----------------

    import sys
    from ccai.pychestrate.webservice.pychestrate_presence import (
        resolve_presence_dir,
    )

    presence_dir = resolve_presence_dir(argv=sys.argv[1:])
    app = establish_webapp_persona(
        name="pychestrate",
        logger_name="scms",
        log_basename="pychestrate",
        presence_dir=presence_dir,
    )

For gunicorn-hosted production the env var is the practical knob
(gunicorn inherits the parent env). For interactive dev runs the
CLI flag is convenient.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Optional, Sequence


# Pychestrate-specific default: the directory ``~/pychestrate``
# under the service user's $HOME. Aligns with the
# ``ccai.thisapp.persona`` library default for
# ``name="pychestrate"`` but stated explicitly here so the
# pychestrate entrypoint owns the decision.
DEFAULT_PRESENCE_DIR_NAME: str = "pychestrate"


# Custom pychestrate-owned env var. Read DIRECTLY (not via
# ``AppVarAccessor`` / this_app) because the presence_dir has to
# be known BEFORE this_app exists.
ENV_PRESENCE_DIR: str = "PYCHESTRATE_PRESENCE_DIR"


# CLI flag accepted by the entrypoint. Same observation as the env
# var: parsed before this_app exists, so we do not (and cannot) go
# through any argparse-driven configuration framework that depends
# on the persona.
CLI_FLAG_PRESENCE_DIR: str = "--presence-dir"


def _default_presence_dir() -> str:
    """
        Return the pychestrate default presence directory:
        ``~/pychestrate`` resolved against the current $HOME.

        :returns: Absolute filesystem path.
    """
    user_home = os.path.expanduser("~")
    rtnval = os.path.join(user_home, DEFAULT_PRESENCE_DIR_NAME)
    return rtnval


def _extract_cli_override(*, argv: Optional[Sequence[str]]) -> Optional[str]:
    """
        Look for ``--presence-dir <path>`` (two args) or
        ``--presence-dir=<path>`` (one arg) in ``argv`` and return
        the path, or ``None`` if the flag is absent.

        Tolerant of malformed input: a bare ``--presence-dir`` with
        no following value is treated as absent. This is bootstrap
        code; we do not want hard failures here -- the default
        kicks in and the operator sees the persona logging the
        resolved path at startup.

        :param argv: Sequence of argument strings (usually
                     ``sys.argv[1:]``). ``None`` returns ``None``.

        :returns: Override path string, or ``None``.
    """
    if argv is None:
        return None
    arg_list = list(argv)

    index = 0
    while index < len(arg_list):
        token = arg_list[index]
        if token == CLI_FLAG_PRESENCE_DIR:
            following_index = index + 1
            if following_index < len(arg_list):
                candidate = arg_list[following_index]
                if len(candidate) > 0 and candidate.startswith("-") is False:
                    return candidate
            return None
        prefix = "{}=".format(CLI_FLAG_PRESENCE_DIR)
        if token.startswith(prefix):
            candidate = token[len(prefix):]
            if len(candidate) > 0:
                return candidate
            return None
        index = index + 1

    return None


def _extract_env_override() -> Optional[str]:
    """
        Read :data:`ENV_PRESENCE_DIR` directly from
        :data:`os.environ`. Empty / unset -> ``None``.

        :returns: Override path string, or ``None``.
    """
    raw = os.environ.get(ENV_PRESENCE_DIR, None)
    if raw is None or len(raw) == 0:
        return None
    rtnval = raw
    return rtnval


def resolve_presence_dir(
        *, argv: Optional[Sequence[str]] = None
    ) -> str:
    """
        Resolve the pychestrate persona presence directory by
        consulting each input channel in strict precedence:

        1. ``--presence-dir`` CLI flag in ``argv``.
        2. ``PYCHESTRATE_PRESENCE_DIR`` environment variable.
        3. Built-in default ``~/pychestrate``.

        The returned path is expanded (``~`` resolved) and
        absolutized. The directory is NOT created here -- the
        setup-state bootstrap (`bootstrap_setup_state`) creates it
        mode 0700 on first boot.

        :param argv: Sequence of argv strings (typically
                     ``sys.argv[1:]``). ``None`` skips CLI lookup.

        :returns: Absolute path of the resolved presence directory.
    """
    cli_value = _extract_cli_override(argv=argv)
    if cli_value is not None:
        chosen = cli_value
    else:
        env_value = _extract_env_override()
        if env_value is not None:
            chosen = env_value
        else:
            chosen = _default_presence_dir()

    expanded = os.path.expanduser(chosen)
    absolutized = os.path.abspath(expanded)
    rtnval = absolutized
    return rtnval


__all__ = [
    "CLI_FLAG_PRESENCE_DIR",
    "DEFAULT_PRESENCE_DIR_NAME",
    "ENV_PRESENCE_DIR",
    "resolve_presence_dir",
]
