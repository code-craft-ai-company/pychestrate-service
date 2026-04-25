"""
.. module:: webhooks_in.normalization
    :synopsis: Publish parsed normalized events on the message bus.

The dispatcher invokes :func:`publish_domain_events` after the
parser has returned a :class:`ParsedWebhook`. The function
enqueues every event through the transactional outbox so the
publish is atomic with the seen-delivery insert: either both
land (and a downstream subscriber sees each event exactly once)
or neither lands (and the request will retry via the provider's
own delivery scheduler).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Mapping

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.webhooks_in.models import (
    NormalizedEvent,
    ParsedWebhook,
)


def publish_domain_events(
        *,
        db_session: DbSession,
        parsed: ParsedWebhook,
        webhook_id: str,
        request_id: str
    ) -> int:
    """
        Enqueue every normalized event a parser emitted on the
        outbox, decorated with the dispatch correlation
        identifiers.

        :param db_session: Open DB session shared with the
                           replay-cache write so both land in
                           the same transaction.
        :param parsed: Parser-produced :class:`ParsedWebhook`.
        :param webhook_id: Configured webhook id; carried on
                           every published event for downstream
                           filtering.
        :param request_id: Server-assigned request id; carried
                           on every published event for trace
                           correlation.

        :returns: Number of events enqueued.
    """
    count = 0
    for event in parsed.domain_events:
        decorated = _decorate_payload(
            event=event,
            provider=parsed.provider,
            hook_name=parsed.hook_name,
            webhook_id=webhook_id,
            request_id=request_id,
        )
        source_event_id = (
            event.source_event_id if event.source_event_id is not None
            and len(event.source_event_id) > 0
            else new_uuid()
        )
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=event.topic,
                payload=decorated,
                source_event_id=source_event_id,
            ),
        )
        count = count + 1
    return count


def _decorate_payload(
        *,
        event: NormalizedEvent,
        provider: str,
        hook_name: str,
        webhook_id: str,
        request_id: str
    ) -> Mapping[str, object]:
    """
        Stamp the dispatcher correlation envelope on top of
        the parser's payload. Parser-supplied keys win on
        conflict so a parser can deliberately override the
        decorator (mostly useful for tests).
    """
    decorated = dict()
    decorated["webhook_provider"] = provider
    decorated["webhook_hook_name"] = hook_name
    decorated["webhook_id"] = webhook_id
    decorated["webhook_request_id"] = request_id
    for key, value in event.payload.items():
        decorated[key] = value
    return decorated
