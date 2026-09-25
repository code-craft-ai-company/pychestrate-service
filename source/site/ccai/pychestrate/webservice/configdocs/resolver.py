"""
.. module:: configdocs.resolver
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Locating documents on disk and their format implementations.

.. moduleauthor:: Code Craft AI LLC

Two independent resolutions happen before a document can be read:

* **Where** it lives -- ``<presence_dir>/config/<stem>.<ext>``, the
  ``<stem>.d`` directory form, or an absolute path from the
  per-domain environment override (Requirement 4.1, 4.6, 4.7).
* **Which** implementation reads it -- the ``config_document_format``
  registered for ``(domain, format_name)`` (Requirement 5).

Neither resolution reads the document, so both are cheap enough to
run during a startup audit.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import List, Optional, Sequence, Tuple, Type

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.configdocs.domains import (
    CONFIG_SUBDIR,
    DEFAULT_FORMAT_NAME,
    DIRECTORY_SUFFIX,
    ConfigDocumentDomain,
    env_var_for_domain,
    stem_for_domain,
)
from ccai.pychestrate.webservice.configdocs.protocol import (
    ConfigDocumentFormatProtocol,
)
from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.pychestrate_presence import resolve_presence_dir


def resolve_config_dir(*, presence_dir: Optional[str] = None) -> str:
    """
        The directory holding every configuration document.

        :param presence_dir: Explicit presence directory. When None,
                             resolved through
                             :func:`resolve_presence_dir` (env var or
                             built-in default; the CLI flag is not
                             consulted here because the loader runs
                             after the entrypoint has already chosen).

        :returns: Absolute path of ``<presence_dir>/config``.
    """
    if presence_dir is None:
        presence_dir = resolve_presence_dir(argv=None)

    rtnval = os.path.join(presence_dir, CONFIG_SUBDIR)
    return rtnval


def _extensions_for(*, basenames: Sequence[str]) -> Tuple[str, ...]:
    """
        The distinct file extensions a format's basenames imply.

        :param basenames: The format's candidate basenames.

        :returns: Tuple of extensions including the leading dot.
    """
    found: List[str] = []
    for basename in basenames:
        _stem, extension = os.path.splitext(basename)
        if len(extension) > 0 and extension not in found:
            found.append(extension)

    rtnval = tuple(found)
    return rtnval


def _directory_members(*, directory: str, basenames: Sequence[str]) -> Tuple[str, ...]:
    """
        Files inside a ``.d`` directory a format recognises, lexically
        ordered.

        :param directory: The ``.d`` directory.
        :param basenames: The format's candidate basenames, used for
                          their extensions.

        :returns: Tuple of absolute paths.
    """
    extensions = _extensions_for(basenames=basenames)
    collected: List[str] = []

    for entry in sorted(os.listdir(directory)):
        candidate = os.path.join(directory, entry)
        if os.path.isfile(candidate) is not True:
            continue
        _stem, extension = os.path.splitext(entry)
        if len(extensions) > 0 and extension not in extensions:
            continue
        collected.append(candidate)

    rtnval = tuple(collected)
    return rtnval


def resolve_document_paths(
        *,
        domain: ConfigDocumentDomain,
        basenames: Sequence[str],
        config_dir: Optional[str] = None,
        presence_dir: Optional[str] = None,
        environ: Optional[dict] = None
    ) -> Tuple[str, ...]:
    """
        Every path contributing to one domain's document, in load
        order.

        Precedence: the ``PYCHESTRATE_CONFIG_<DOMAIN>_PATH`` override,
        then the ``<stem>.d`` directory, then the first matching
        ``<stem>.<ext>`` file. An absent document is an empty tuple,
        not an error (Requirement 4.5).

        :param domain: The domain to locate.
        :param basenames: The selected format's candidate basenames.
        :param config_dir: Explicit config directory.
        :param presence_dir: Explicit presence directory, used when
                             ``config_dir`` is None.
        :param environ: Environment mapping, defaulting to
                        ``os.environ``.

        :returns: Tuple of absolute paths. Empty when not configured.
    """
    if environ is None:
        environ = dict(os.environ)

    override = environ.get(env_var_for_domain(domain=domain), None)
    if override is not None and len(str(override).strip()) > 0:
        target = os.path.abspath(os.path.expanduser(str(override).strip()))
        if os.path.isdir(target) is True:
            return _directory_members(directory=target, basenames=basenames)
        if os.path.isfile(target) is True:
            return (target,)
        # An override naming nothing is an operator error worth
        # surfacing, unlike an absent default-location document.
        err_msg_lines = ["Configuration document override path does not exist."]
        err_msg_lines.append("DOMAIN: {}".format(domain.value))
        err_msg_lines.append("VARIABLE: {}".format(env_var_for_domain(domain=domain)))
        err_msg_lines.append("PATH: {}".format(target))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg)

    if config_dir is None:
        config_dir = resolve_config_dir(presence_dir=presence_dir)

    stem = stem_for_domain(domain=domain)

    directory = os.path.join(config_dir, "{}{}".format(stem, DIRECTORY_SUFFIX))
    if os.path.isdir(directory) is True:
        return _directory_members(directory=directory, basenames=basenames)

    for basename in basenames:
        candidate = os.path.join(config_dir, basename)
        if os.path.isfile(candidate) is True:
            return (candidate,)

    return tuple()


def list_formats_for_domain(
        *,
        domain: ConfigDocumentDomain
    ) -> Tuple[Type[ConfigDocumentFormatProtocol], ...]:
    """
        Registered implementations for one domain, in ``PRECEDENCE``
        order.

        :param domain: The domain.

        :returns: Tuple of implementation classes.
    """
    registered = list_factory_implementations(
        factory_protocol_name=ConfigDocumentFormatProtocol.factory_protocol_name,
    )

    collected: List[Type[ConfigDocumentFormatProtocol]] = []
    for implementation in registered:
        if implementation.document_domain() == domain.value:
            collected.append(implementation)

    rtnval = tuple(collected)
    return rtnval


def resolve_format_implementation(
        *,
        domain: ConfigDocumentDomain,
        format_name: Optional[str] = None
    ) -> Type[ConfigDocumentFormatProtocol]:
    """
        The implementation reading ``domain`` in ``format_name``.

        When two implementations claim the same ``(domain,
        format_name)`` the lower ``PRECEDENCE`` wins, which is how an
        enterprise implementation displaces the shipped default
        (Requirement 2.5).

        :param domain: The domain to read.
        :param format_name: The selected format, defaulting to
                            ``codecraftai`` (Requirement 3.7).

        :returns: The implementation class.
        :raises: ConfigurationError naming the registered formats when
                 nothing matches. There is deliberately no fallback to
                 the default (Requirement 5.2) -- a deployment that
                 asked for a format it does not have should fail loudly
                 rather than silently read its files with the wrong
                 reader.
    """
    if format_name is None:
        format_name = DEFAULT_FORMAT_NAME

    candidates = list_formats_for_domain(domain=domain)
    for implementation in candidates:
        if implementation.format_name() == format_name:
            return implementation

    available = sorted([item.format_name() for item in candidates])
    err_msg_lines = ["No configuration-document format implementation registered."]
    err_msg_lines.append("DOMAIN: {}".format(domain.value))
    err_msg_lines.append("REQUESTED_FORMAT: {}".format(format_name))
    err_msg_lines.append("REGISTERED_FORMATS: {}".format(available))
    err_msg = os.linesep.join(err_msg_lines)
    raise ConfigurationError(err_msg)


def claimed_keys_by_other_domains(
        *,
        domain: ConfigDocumentDomain,
        format_names: Optional[dict] = None
    ) -> Tuple[Tuple[str, str], ...]:
    """
        Top-level keys claimed by domains other than ``domain``.

        Only domains with a resolvable selected implementation
        contribute, so a partially-registered deployment (a test, or a
        service booting with one format installed) does not fail the
        bleed check for want of a claim list.

        :param domain: The domain being loaded.
        :param format_names: Optional per-domain format selection.

        :returns: Tuple of ``(key, owning_domain)`` pairs.
    """
    if format_names is None:
        format_names = {}

    collected: List[Tuple[str, str]] = []
    for other in ConfigDocumentDomain:
        if other == domain:
            continue
        try:
            implementation = resolve_format_implementation(
                domain=other, format_name=format_names.get(other, None),
            )
        except ConfigurationError:
            continue
        for key in implementation.claimed_top_level_keys():
            collected.append((key, other.value))

    rtnval = tuple(collected)
    return rtnval
