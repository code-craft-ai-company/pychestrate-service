"""
.. module:: configdocs
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 0-config-formats — extensible readers for externally-authored
               configuration documents.

.. moduleauthor:: Code Craft AI LLC

Pychestrate consumes four kinds of externally-authored document --
resource specifications, landscapes, topologies, and credentials --
and authors none of them. This package owns how they are located,
read, and turned into canonical models, without the rest of the
service learning anything about their on-disk format.

Public surface:

* :class:`ConfigDocumentDomain` — the fixed four-domain vocabulary.
* :class:`ConfigDocumentFormatProtocol` — the ``config_document_format``
  factory contract an enterprise deployment implements to read its own
  formats.
* Canonical models: :class:`ResourceSpecDocument`,
  :class:`LandscapeDocument`, :class:`TopologyDocument`,
  :class:`CredentialsDocument`, and the entry types they carry.
* :func:`load_document`, :func:`load_all_documents`,
  :class:`LoadOutcome`.
* :class:`ValidationReport`, :class:`Diagnostic`,
  :class:`DiagnosticCodes`.
* :func:`register_config_document_format` — registration with the
  domain and shadowing guards.

The in-tree ``codecraftai`` format implementations land in M2; until
then :func:`register_builtin_extensions` registers nothing and every
domain resolves as unconfigured.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from typing import Type

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.configdocs.domains import (
    CONFIG_SUBDIR,
    DEFAULT_FORMAT_NAME,
    DIRECTORY_SUFFIX,
    ConfigDocumentDomain,
    coerce_domain,
    domain_values,
    env_var_for_domain,
    format_variable_for_domain,
    stem_for_domain,
)
from ccai.pychestrate.webservice.configdocs.errors import (
    ConfigDocumentDomainBleedError,
    ConfigDocumentError,
    ConfigDocumentParseError,
    ConfigDocumentValidationError,
    DuplicateDocumentEntryError,
    InlineSecretRejectedError,
)
from ccai.pychestrate.webservice.configdocs.loader import (
    LoadOutcome,
    combined_report,
    load_all_documents,
    load_document,
)
from ccai.pychestrate.webservice.configdocs.merging import merge_documents
from ccai.pychestrate.webservice.configdocs.models import (
    CANONICAL_SCHEMA_VERSION,
    DOCUMENT_TYPES,
    AddressPlane,
    ConfigDocument,
    CredentialReference,
    CredentialsDocument,
    DeviceAddresses,
    LandscapeDevice,
    LandscapeDocument,
    LandscapeService,
    ResourceSpecDocument,
    ResourceSpecEntry,
    TopologyDocument,
    TopologyEntry,
    TopologyMember,
)
from ccai.pychestrate.webservice.configdocs.protocol import (
    ConfigDocumentFormatProtocol,
)
from ccai.pychestrate.webservice.configdocs.resolver import (
    claimed_keys_by_other_domains,
    list_formats_for_domain,
    resolve_config_dir,
    resolve_document_paths,
    resolve_format_implementation,
)
from ccai.pychestrate.webservice.configdocs.validation import (
    Diagnostic,
    DiagnosticCodes,
    DiagnosticSeverity,
    ValidationReport,
    build_report,
    merge_reports,
)
from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)


_LOGGER = logging.getLogger("pychestrate.configdocs")


def register_config_document_format(
        *,
        implementation: Type[ConfigDocumentFormatProtocol]
    ) -> None:
    """
        Register a ``config_document_format`` implementation.

        Wraps the generic registry with the two guards this protocol
        needs, because neither can be expressed generically:

        * An implementation naming an undeclared domain is rejected
          (Requirement 2.4). The domain vocabulary is fixed; a typo
          would otherwise register an implementation nothing could
          ever resolve.
        * An implementation claiming a ``(domain, format_name)`` pair
          another already holds logs
          ``pychestrate_config_format_shadowed`` naming both classes
          (Requirement 2.5). This is a warning rather than an error:
          shadowing is exactly how an enterprise implementation
          displaces the shipped default, so it must be allowed --
          but silently swapping which code reads an operator's
          inventory is not something to discover later.

        :param implementation: The implementation class.

        :returns: None.
        :raises: ConfigurationError when the class declares no domain,
                 an unknown domain, or an empty format name.
    """
    domain_text = implementation.document_domain()
    try:
        domain = coerce_domain(domain=domain_text)
    except ValueError:
        err_msg_lines = ["Configuration-document format declares an unknown domain."]
        err_msg_lines.append("IMPLEMENTATION: {}".format(implementation.__qualname__))
        err_msg_lines.append("DOMAIN: {}".format(domain_text))
        err_msg_lines.append("DECLARED_DOMAINS: {}".format(list(domain_values())))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    format_name = implementation.format_name()
    if format_name is None or len(str(format_name).strip()) == 0:
        err_msg_lines = ["Configuration-document format declares an empty format name."]
        err_msg_lines.append("IMPLEMENTATION: {}".format(implementation.__qualname__))
        err_msg_lines.append("DOMAIN: {}".format(domain.value))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    for existing in list_formats_for_domain(domain=domain):
        if existing is implementation:
            continue
        if existing.format_name() != format_name:
            continue
        shadowed = existing
        winner = implementation
        if getattr(existing, "PRECEDENCE", 1000) <= getattr(implementation, "PRECEDENCE", 1000):
            shadowed = implementation
            winner = existing
        _LOGGER.warning(
            "pychestrate_config_format_shadowed: domain=%s format=%s "
            "winner=%s shadowed=%s",
            domain.value, format_name,
            winner.__qualname__, shadowed.__qualname__,
        )

    register_factory_implementation(implementation=implementation)
    return


def register_builtin_extensions() -> None:
    """
        Seed the in-tree ``codecraftai`` format implementations.

        Registers nothing until M2 lands them, so every domain
        resolves as unconfigured. M2 adds the four implementations
        here and the matching call in
        :mod:`ccai.pychestrate.webservice.extensions.bootstrap` --
        wiring a no-op into the shared startup path now would be
        churn for no behaviour.

        :returns: None.
    """
    return
