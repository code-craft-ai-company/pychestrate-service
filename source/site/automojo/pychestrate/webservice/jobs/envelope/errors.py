"""
.. module:: jobs.envelope.errors
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Exception hierarchy for the Layer-5 envelope codec.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class JobEnvelopeError(Exception):
    """
        Base class for recoverable envelope-codec errors. Subclasses
        signal specific failure modes; REST / wire layers translate
        each subclass to a distinct status code.
    """


class EnvelopeSchemaVersionError(JobEnvelopeError):
    """
        Raised when a caller deserializes an envelope whose
        ``schema_version`` is outside the service's supported range.
        The message includes both the envelope version and the
        supported range.
    """


class EnvelopeSerializationError(JobEnvelopeError):
    """
        Raised when canonical serialization or parsing fails (e.g.
        non-UTF-8 bytes, malformed JSON, disallowed top-level keys).
    """


class EnvelopeSigningKeyMissingError(JobEnvelopeError):
    """
        Raised when :func:`sign` is called before the service bootstrap
        has installed an active signing key. REST / wire layers
        translate to HTTP 503 equivalents.
    """


class EnvelopeClaimMissingError(JobEnvelopeError):
    """
        Raised when a job's ``job_type`` matches an
        :class:`EnvelopeFieldExtension`'s ``required_for_job_types``
        predicate and the dispatcher failed to populate that claim in
        ``extension_claims``. (Reserved for M2; M1 never raises this
        because the extension registry is not yet populated.)
    """
