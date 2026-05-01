"""
.. module:: webhooks_in.factories.inbound_webhook_parser
    :synopsis: ``inbound_webhook_parser`` factory contract.

Every parser declares its provider segment, the media types it
accepts, the signature header(s) it understands, and the
optional delivery-id header used by the replay-cache. The
``parse`` classmethod is contracted to be *total* — it must
return a :class:`ParsedWebhook` or a :class:`StructuredRejection`,
never raise. The dispatcher wraps every invocation in a
catch-and-reclassify boundary so an escaping exception still
surfaces as a structured rejection rather than a 500.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Mapping, Optional, Tuple, Union

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)
from automojo.pychestrate.webservice.webhooks_in.models import (
    ParsedWebhook,
    SignatureHeaderSpec,
    StructuredRejection,
)


class InboundWebhookParserProtocol(FactoryProtocolBase):
    """
        Contract for the inbound webhook parser dispatch. M1
        ships :class:`GenericHmacWebhookParser` as the only
        in-tree reference; M2 lands GitHub / GitLab /
        Bitbucket implementations.
    """

    factory_protocol_name: str = "inbound_webhook_parser"
    protocol_schema_version: int = 1

    is_published: bool = True
    published_docs_url: str = "https://docs.pychestrate.io/plugin-api/inbound_webhook_parser"
    published_reference: str = (
        "automojo.pychestrate.webservice.webhooks_in.factories.generic_hmac_parser"
        ".GenericHmacWebhookParser"
    )

    @classmethod
    def provider_name(cls) -> str:
        """
            Return the URL segment under
            ``/api/v1/webhooks/in/<provider>/...``.
        """
        raise NotImplementedError("Subclasses must implement provider_name")

    @classmethod
    def accepted_content_types(cls) -> Tuple[str, ...]:
        """
            Tuple of media types the parser consumes. The M2
            controller rejects with 415 when the request's
            ``Content-Type`` is outside this set.
        """
        raise NotImplementedError(
            "Subclasses must implement accepted_content_types",
        )

    @classmethod
    def signature_headers(cls) -> Tuple[SignatureHeaderSpec, ...]:
        """
            Tuple of every signature header the parser
            understands, in the order the verification helper
            should try them.
        """
        raise NotImplementedError(
            "Subclasses must implement signature_headers",
        )

    @classmethod
    def delivery_id_header(cls) -> Optional[str]:
        """
            Header carrying the provider-native delivery id, or
            ``None`` when the provider does not expose one.
        """
        rtnval: Optional[str] = None
        return rtnval

    @classmethod
    def parse(
            cls,
            *,
            raw_bytes: bytes,
            headers: Mapping[str, str]
        ) -> Union[ParsedWebhook, StructuredRejection]:
        """
            Parse a verified payload into a
            :class:`ParsedWebhook` carrying one or more
            normalized events, or surface a structured
            rejection. The dispatcher has already verified the
            signature and the replay cache before the parser
            sees the bytes.
        """
        raise NotImplementedError("Subclasses must implement parse")
