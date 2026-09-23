"""
.. module:: jobs.results.artifact_root
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Where run artifacts live on the service host.

.. moduleauthor:: Code Craft AI LLC

A run's result tree is addressed by its allocation's
``backend_key_prefix`` -- the relative key
``<project>/results/<yyyy>/<mm>/<dd>/<job_type>/<run_id>`` built by
:func:`jobs.results.path_builder.build_canonical_prefix`. On the
local-filesystem results backend that key is a directory, and
before this module every consumer turned it into one with
``os.path.abspath`` -- that is, against the process working
directory. Under gunicorn (``--chdir source/site``) run artifacts
therefore landed inside the code checkout, where the systemd unit
mounts the tree read-only and the next ``rsync --delete`` deploy
would erase them.

The key is now anchored under the **artifact root**:

* ``PYCHESTRATE_ARTIFACT_ROOT`` (environment, or the ``DATASTORAGE``
  section of ``settings.config``), else
* ``<presence_dir>/artifacts`` -- next to the SQLite database, under
  the service user's state directory, writable by the unit and part
  of the backup set.

Every reader and writer of a result tree -- the presigned upload
sink, the operator download route, the testbase result scanner, and
the backup -- resolves paths through :func:`resolve_result_tree_path`
so they agree on one location.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Optional

from ccai.pychestrate.webservice.jobs.results.errors import (
    ArtifactPathInvalidError,
)


#: Environment variable (and settings key) naming the artifact root.
ENV_ARTIFACT_ROOT: str = "PYCHESTRATE_ARTIFACT_ROOT"

#: Directory name of the default artifact root inside the presence
#: directory.
DEFAULT_ARTIFACT_DIR_NAME: str = "artifacts"

#: Process-wide override (test seam and embedding hook). ``None``
#: resolves the configured value on every call.
_ARTIFACT_ROOT_OVERRIDE: Optional[str] = None


def set_artifact_root_override(*, root: Optional[str]) -> None:
    """
        Pin the artifact root for this process, bypassing the
        configured value. Tests use it to point uploads at a
        temporary directory; ``None`` restores normal resolution.

        :param root: Directory path, or ``None`` to clear.

        :returns: None.
    """
    global _ARTIFACT_ROOT_OVERRIDE
    _ARTIFACT_ROOT_OVERRIDE = root
    return


def _configured_artifact_root() -> str:
    """
        Read the configured artifact root through the
        :class:`PychestrateVariables` precedence chain (environment >
        settings.config > ``<presence_dir>/artifacts``). Outside an
        established persona (operator tools run before the service
        bootstraps) fall back to the environment variable and then to
        the bootstrap-time presence directory resolver, which apply
        the same defaults.

        :returns: The configured path (not yet absolutized).
    """
    from ccai.errors.exceptions import SemanticError

    try:
        from ccai.thisapp.wellknown import ThisApplicationSingleton
        from ccai.pychestrate.webservice.pychestrate_variables import (
            PychestrateVariables,
            PychestrateVariablesDesc,
        )

        # Forget any cached resolution so an environment change made
        # after the first read (tests, operator tools) is honored.
        ThisApplicationSingleton().forget_variable(
            PychestrateVariablesDesc.PYCHESTRATE_ARTIFACT_ROOT
        )
        configured = PychestrateVariables.PYCHESTRATE_ARTIFACT_ROOT
    except SemanticError:
        configured = None

    if configured is None or len(str(configured)) == 0:
        from_environment = os.environ.get(ENV_ARTIFACT_ROOT, "")
        if len(from_environment) > 0:
            configured = from_environment
        else:
            from ccai.pychestrate.webservice.pychestrate_presence import (
                resolve_presence_dir,
            )
            configured = os.path.join(
                resolve_presence_dir(argv=None), DEFAULT_ARTIFACT_DIR_NAME,
            )

    rtnval = str(configured)
    return rtnval


def resolve_artifact_root() -> str:
    """
        Return the absolute directory run artifacts are stored under.
        The directory is not created here; writers create the parts
        of the tree they need.

        :returns: Absolute, user-expanded directory path.
    """
    if _ARTIFACT_ROOT_OVERRIDE is not None:
        chosen = _ARTIFACT_ROOT_OVERRIDE
    else:
        chosen = _configured_artifact_root()
    rtnval = os.path.abspath(os.path.expanduser(chosen))
    return rtnval


def resolve_result_tree_path(
        *,
        backend_key_prefix: str,
        allow_absolute: bool = True,
        artifact_root: Optional[str] = None
    ) -> str:
    """
        Resolve a run's ``backend_key_prefix`` to the absolute
        directory that holds its result tree.

        A relative prefix (every prefix the path builder produces) is
        anchored under the artifact root and must stay inside it. An
        absolute prefix is accepted only when ``allow_absolute`` is
        True -- allocation rows the server wrote itself -- and is
        refused for prefixes a client supplied.

        :param backend_key_prefix: Allocation prefix.
        :param allow_absolute: Whether an absolute prefix is honored
                               as-is.
        :param artifact_root: Root override; defaults to
                              :func:`resolve_artifact_root`.

        :returns: Absolute directory path.
        :raises: ArtifactPathInvalidError when the prefix is empty,
                 absolute while ``allow_absolute`` is False, or
                 escapes the artifact root.
    """
    if backend_key_prefix is None or len(str(backend_key_prefix).strip()) == 0:
        raise ArtifactPathInvalidError("Result-tree prefix is empty.") from None

    prefix = str(backend_key_prefix).strip()
    if os.path.isabs(prefix) is True:
        if allow_absolute is False:
            err_lines = ["Result-tree prefix must be relative to the artifact root."]
            err_lines.append("PREFIX: {}".format(prefix))
            err_msg = os.linesep.join(err_lines)
            raise ArtifactPathInvalidError(err_msg) from None
        rtnval = os.path.abspath(prefix)
        return rtnval

    if artifact_root is None:
        root = resolve_artifact_root()
    else:
        root = os.path.abspath(os.path.expanduser(artifact_root))

    resolved = os.path.abspath(os.path.join(root, prefix))
    if os.path.commonpath([root, resolved]) != root or resolved == root:
        err_lines = ["Result-tree prefix escapes the artifact root."]
        err_lines.append("PREFIX: {}".format(prefix))
        err_lines.append("ARTIFACT_ROOT: {}".format(root))
        err_msg = os.linesep.join(err_lines)
        raise ArtifactPathInvalidError(err_msg) from None

    rtnval = resolved
    return rtnval


__all__ = [
    "DEFAULT_ARTIFACT_DIR_NAME",
    "ENV_ARTIFACT_ROOT",
    "resolve_artifact_root",
    "resolve_result_tree_path",
    "set_artifact_root_override",
]
