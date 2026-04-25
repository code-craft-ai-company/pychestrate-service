"""
.. module:: webhooks_in.factories.generic_hmac_parser
    :synopsis: GenericHmacWebhookParser — fallback HMAC-SHA-256
               parser used by the M1 reference path.

The generic parser accepts ``application/json`` payloads
signed with HMAC-SHA-256. It reads the signature from
``X-Pychestrate-Signature`` (matching the outbound webhook
canonical header) and the optional delivery id from
``X-Pychestrate-Delivery-Id``. The parser emits a single
``entity.webhook.payload`` normalized event carrying the raw
JSON payload — sufficient to demonstrate end-to-end signing,
verifying, and event publishing without committing to a
provider-specific schema.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Mapping, Optional, Tuple, Union

from automojo.pychestrate.webservice.webhooks_in.factories.inbound_webhook_parser import (
    InboundWebhookParserProtocol,
)
from automojo.pychestrate.webservice.webhooks_in.models import (
    NormalizedEvent,
    ParsedWebhook,
    SignatureAlgorithm,
    SignatureEncoding,
    SignatureHeaderSpec,
    StructuredRejection,
)


GENERIC_PROVIDER_NAME: str = "generic"
GENERIC_HOOK_PAYLOAD_TOPIC: str = "entity.webhook.payload"
GENERIC_SIGNATURE_HEADER: str = "X-Pychestrate-Signature"
GENERIC_DELIVERY_ID_HEADER: str = "X-Pychestrate-Delivery-Id"
GENERIC_HOOK_NAME_HEADER: str = "X-Pychestrate-Hook-Name"


class GenericHmacWebhookParser(InboundWebhookParserProtocol):
    """
        Fallback parser for callers that only need the
        generic HMAC envelope. Always emits exactly one
        normalized event whose payload is the parsed JSON body
        plus the request hook-name header.
    """

    factory_protocol_name: str = "inbound_webhook_parser"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1500

    @classmethod
    def provider_name(cls) -> str:
        rtnval = GENERIC_PROVIDER_NAME
        return rtnval

    @classmethod
    def accepted_content_types(cls) -> Tuple[str, ...]:
        rtnval: Tuple[str, ...] = ("application/json",)
        return rtnval

    @classmethod
    def signature_headers(cls) -> Tuple[SignatureHeaderSpec, ...]:
        spec = SignatureHeaderSpec(
            header=GENERIC_SIGNATURE_HEADER,
            algorithm=SignatureAlgorithm.HMAC_SHA256,
            encoding=SignatureEncoding.HEX_WITH_PREFIX,
            prefix="sha256=",
            weak=False,
        )
        rtnval: Tuple[SignatureHeaderSpec, ...] = (spec,)
        return rtnval

    @classmethod
    def delivery_id_header(cls) -> Optional[str]:
        rtnval = GENERIC_DELIVERY_ID_HEADER
        return rtnval

    @classmethod
    def parse(
            cls,
            *,
            raw_bytes: bytes,
            headers: Mapping[str, str]
        ) -> Union[ParsedWebhook, StructuredRejection]:
        """
            Parse a JSON envelope into a single
            ``entity.webhook.payload`` normalized event.
        """
        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except UnicodeDecodeError as decode_err:
            rtnval = StructuredRejection(
                reason="payload_not_utf8",
                detail=str(decode_err),
                recoverable=True,
            )
            return rtnval
        except json.JSONDecodeError as json_err:
            rtnval = StructuredRejection(
                reason="payload_not_json",
                detail=str(json_err),
                recoverable=True,
            )
            return rtnval

        delivery_id = _read_header(
            headers=headers, name=GENERIC_DELIVERY_ID_HEADER,
        )
        hook_name = _read_header(
            headers=headers, name=GENERIC_HOOK_NAME_HEADER,
        )
        if hook_name is None:
            hook_name = ""

        event = NormalizedEvent(
            topic=GENERIC_HOOK_PAYLOAD_TOPIC,
            payload={
                "provider": GENERIC_PROVIDER_NAME,
                "hook_name": hook_name,
                "delivery_id": delivery_id,
                "body": payload,
            },
            source_event_id=delivery_id,
        )
        rtnval = ParsedWebhook(
            provider=GENERIC_PROVIDER_NAME,
            hook_name=hook_name,
            delivery_id=delivery_id,
            domain_events=(event,),
        )
        return rtnval


def _read_header(*, headers: Mapping[str, str], name: str) -> Optional[str]:
    """
        Case-insensitive header read.
    """
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    rtnval: Optional[str] = None
    return rtnval
