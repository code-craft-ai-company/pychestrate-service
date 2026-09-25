"""
.. module:: configdocs.protocol
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``config_document_format`` factory contract.

.. moduleauthor:: Code Craft AI LLC

A configuration-document format implementation reads one domain's
document in one concrete on-disk format and returns the canonical
model for that domain. It is the only place in Pychestrate that knows
what the bytes look like.

The default implementations ship in-tree at ``PRECEDENCE = 1000``
reading the ``codecraftai`` formats. An enterprise deployment adds its
own by registering a subclass at a lower ``PRECEDENCE`` for the one
domain it cares about; the other domains keep their defaults
(Requirement 5.3).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Tuple

from ccai.pychestrate.webservice.configdocs.models import ConfigDocument
from ccai.pychestrate.webservice.configdocs.validation import ValidationReport
from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class ConfigDocumentFormatProtocol(FactoryProtocolBase):
    """
        Contract for configuration-document format implementations.
    """

    factory_protocol_name: str = "config_document_format"
    protocol_schema_version: int = 1

    # Stays unpublished until M2 lands the in-tree ``codecraftai``
    # implementations. ``8-plugin-api``'s catalog validator imports
    # every published_reference, so publishing a protocol whose
    # reference module does not exist yet fails
    # ``test_validate_catalog_resolves_every_reference``. M2 creates
    # ``configdocs/formats/codecraftai_landscape.py`` and flips this
    # to True in the same change.
    is_published: bool = False
    published_docs_url: str = (
        "https://docs.pychestrate.io/plugin-api/config_document_format"
    )
    published_reference: str = (
        "ccai.pychestrate.webservice.configdocs.formats.codecraftai_landscape"
        ".CodeCraftAiLandscapeFormat"
    )

    @classmethod
    def document_domain(cls) -> str:
        """
            The domain this implementation reads. Must be one of the
            values declared by :class:`ConfigDocumentDomain`
            (Requirement 2.4).

            :returns: The domain string value.
        """
        raise NotImplementedError("Subclasses must implement document_domain")

    @classmethod
    def format_name(cls) -> str:
        """
            Stable slug naming the on-disk format, e.g.
            ``codecraftai``. A deployment selects an implementation by
            this name through ``config.format.<domain>``.

            :returns: The format name.
        """
        raise NotImplementedError("Subclasses must implement format_name")

    @classmethod
    def file_basenames(cls) -> Tuple[str, ...]:
        """
            Filenames this implementation recognises, in preference
            order, e.g. ``("landscape.yaml", "landscape.yml")``.

            The domain owns the stem; the format owns the extension.
            Inside a ``.d`` directory these are matched by extension so
            that ``lab-west.yaml`` is picked up alongside
            ``lab-east.yaml``.

            :returns: Tuple of candidate basenames.
        """
        raise NotImplementedError("Subclasses must implement file_basenames")

    @classmethod
    def claimed_top_level_keys(cls) -> Tuple[str, ...]:
        """
            Top-level keys this domain's document legitimately owns.

            The loader unions the claims of the *other* domains and
            rejects a file that carries any of them (Requirement 4.3),
            which is what stops a ``credentials:`` block being quietly
            accepted inside a landscape file.

            :returns: Tuple of top-level key names.
        """
        raise NotImplementedError("Subclasses must implement claimed_top_level_keys")

    @classmethod
    def probe_top_level_keys(cls, *, path: str, text: str) -> Tuple[str, ...]:
        """
            The top-level keys present in ``text``, read as cheaply as
            the format allows.

            Called before :meth:`parse` so the domain-bleed check can
            reject a misfiled document without running a full parser
            over it. An implementation that cannot answer cheaply may
            do a full parse here; it must not raise on malformed input,
            and should return an empty tuple instead so that
            :meth:`parse` produces the real diagnostic.

            :param path: Absolute path of the document.
            :param text: The document's text.

            :returns: Tuple of top-level key names.
        """
        raise NotImplementedError("Subclasses must implement probe_top_level_keys")

    @classmethod
    def parse(cls, *, path: str, text: str) -> ConfigDocument:
        """
            Turn one document's text into its canonical model.

            :param path: Absolute path, recorded on the document as
                         ``source_path``.
            :param text: The document's text.

            :returns: The canonical document for this domain.
            :raises: ConfigDocumentParseError when the text cannot be
                     read. The loader never falls back to another
                     format (Requirement 2.6).
        """
        raise NotImplementedError("Subclasses must implement parse")

    @classmethod
    def validate(cls, *, document: ConfigDocument) -> ValidationReport:
        """
            Check a parsed document for format-level problems.

            Accumulates every finding rather than stopping at the
            first (Requirement 8.2). Cross-domain checks -- an
            unresolved credential reference, say -- belong to the
            loader, not here.

            :param document: The parsed canonical document.

            :returns: The report.
        """
        raise NotImplementedError("Subclasses must implement validate")
