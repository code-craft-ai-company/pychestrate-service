"""
.. module:: configdocs.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception hierarchy for configuration-document loading.

.. moduleauthor:: Code Craft AI LLC

Registration and format-selection failures raise
:class:`ccai.errors.exceptions.ConfigurationError` rather than a type
declared here -- they are deployment misconfiguration and must block
startup the same way every other bad setting does. The exceptions in
this module describe a *document* that could not be read.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Optional, Sequence


class ConfigDocumentError(Exception):
    """
        Base for configuration-document failures.
    """


class ConfigDocumentParseError(ConfigDocumentError):
    """
        Raised when a format implementation cannot parse its document
        (Requirement 2.6).

        The loader never falls back to another format on a parse
        failure -- a document that fails to parse is an operator error
        to fix, not a signal to guess again with a different reader.
    """

    def __init__(
            self,
            *,
            domain: str,
            format_name: str,
            source_path: str,
            message: str,
            line_number: Optional[int] = None
        ):
        self.domain = domain
        self.format_name = format_name
        self.source_path = source_path
        self.line_number = line_number

        err_msg_lines = ["Failed to parse configuration document."]
        err_msg_lines.append("DOMAIN: {}".format(domain))
        err_msg_lines.append("FORMAT: {}".format(format_name))
        err_msg_lines.append("PATH: {}".format(source_path))
        if line_number is not None:
            err_msg_lines.append("LINE: {}".format(line_number))
        err_msg_lines.append("DETAIL: {}".format(message))
        super().__init__(os.linesep.join(err_msg_lines))


class ConfigDocumentDomainBleedError(ConfigDocumentError):
    """
        Raised when a document file carries a top-level key another
        domain claims (Requirement 4.3).

        This is the check that keeps a ``credentials:`` block from
        being quietly accepted inside ``landscape.yaml`` -- the most
        likely path by which inline secret material reaches a version
        control system.
    """

    def __init__(
            self,
            *,
            domain: str,
            source_path: str,
            offending_keys: Sequence[str],
            claimed_by: str
        ):
        self.domain = domain
        self.source_path = source_path
        self.offending_keys = tuple(offending_keys)
        self.claimed_by = claimed_by

        err_msg_lines = ["Configuration document carries keys owned by another domain."]
        err_msg_lines.append("DOMAIN: {}".format(domain))
        err_msg_lines.append("PATH: {}".format(source_path))
        err_msg_lines.append("OFFENDING_KEYS: {}".format(sorted(self.offending_keys)))
        err_msg_lines.append("CLAIMED_BY: {}".format(claimed_by))
        err_msg_lines.append(
            "Each domain owns its own file; move these keys into that domain's document.",
        )
        super().__init__(os.linesep.join(err_msg_lines))


class DuplicateDocumentEntryError(ConfigDocumentError):
    """
        Raised when the ``.d`` directory form yields the same entry
        identity from two files (Requirement 4.6).
    """

    def __init__(
            self,
            *,
            domain: str,
            identity: str,
            source_paths: Sequence[str]
        ):
        self.domain = domain
        self.identity = identity
        self.source_paths = tuple(source_paths)

        err_msg_lines = ["Duplicate entry identity across configuration documents."]
        err_msg_lines.append("DOMAIN: {}".format(domain))
        err_msg_lines.append("IDENTITY: {}".format(identity))
        err_msg_lines.append("PATHS: {}".format(list(self.source_paths)))
        super().__init__(os.linesep.join(err_msg_lines))


class ConfigDocumentValidationError(ConfigDocumentError):
    """
        Raised when a caller asks to project a document whose
        validation report carries errors (Requirement 8.3).

        Carries the report so the caller can render every diagnostic
        rather than only the first.
    """

    def __init__(self, *, domain: str, report: object):
        self.domain = domain
        self.report = report

        err_msg_lines = ["Configuration document failed validation."]
        err_msg_lines.append("DOMAIN: {}".format(domain))
        errors = getattr(report, "errors", ())
        err_msg_lines.append("ERROR_COUNT: {}".format(len(errors)))
        for diagnostic in errors:
            err_msg_lines.append("  {}".format(diagnostic))
        super().__init__(os.linesep.join(err_msg_lines))


class InlineSecretRejectedError(ConfigDocumentError):
    """
        Raised when a credentials document carries inline secret
        material rather than a reference (Requirement 6.2).

        The offending value is never included in the message, the
        arguments, or any log line this exception reaches.
    """

    def __init__(
            self,
            *,
            source_path: str,
            credential_name: str,
            offending_key: str
        ):
        self.source_path = source_path
        self.credential_name = credential_name
        self.offending_key = offending_key

        err_msg_lines = ["Credentials document contains an inline secret value."]
        err_msg_lines.append("PATH: {}".format(source_path))
        err_msg_lines.append("CREDENTIAL: {}".format(credential_name))
        err_msg_lines.append("KEY: {}".format(offending_key))
        err_msg_lines.append(
            "Credentials documents carry references only; store the material in the vault.",
        )
        super().__init__(os.linesep.join(err_msg_lines))
