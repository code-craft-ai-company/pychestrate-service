# 0-message-bus — Design

## Architecture

The bus is a single in-process singleton registered during the Phase 0
startup sequence with priority `15` (after web app host, before
`0-persistence` completes its migration phase). It owns a topic registry, a
per-topic append-only ring buffer, one worker thread per subscriber, and a
publish fast-path that fans out to subscriber queues. The bus is
authoritative for (1) the subscription table, (2) each subscriber's queue,
(3) per-topic buffer depth. Other features publish and subscribe; they
never inspect the registry directly. The design keeps a clean seam: the
`MessageBus` interface is the same whether backed by the in-process
implementation or a later network-backed driver, enabling a future
`factory: message_bus_driver` extension when multi-process delivery is
required.

## Data Model

All state is in-memory:

- `subscriptions: dict[str, list[SubscriptionRecord]]` keyed by canonical
  pattern.
- `SubscriptionRecord`:
  - `subscriber_name: str` — unique
  - `pattern: str` — normalized
  - `handler: Callable[[Event], None]`
  - `queue: Queue[Event]` — bounded
  - `worker: Thread`
  - `registered_at: datetime`
- `topic_stats: dict[str, TopicStats]` — running counters and a bounded
  recent-event ring for debugging.
- `overflow_policies: dict[str, OverflowPolicy]` — per-topic default
  `drop_oldest`.

No persistent tables. The `Event` envelope:

- `event_id: UUID` (ULID)
- `topic: str`
- `published_at: datetime` (UTC, microsecond)
- `request_id: str | None`
- `headers: dict[str, str]` (default empty)
- `payload: Any`

## Interfaces

### Public API

N/A — fully internal.

### Internal API

```python
class Event:
    def __init__(
        self,
        event_id: UUID,
        topic: str,
        published_at: datetime,
        request_id: str | None,
        headers: dict[str, str],
        payload: Any
    ) -> None:
        self.event_id = event_id
        self.topic = topic
        self.published_at = published_at
        self.request_id = request_id
        self.headers = headers
        self.payload = payload
        return


class MessageBus:
    def __init__(
        self,
        config: MessageBusConfig
    ) -> None:
        self._config = config
        self._subscriptions: dict[str, list[SubscriptionRecord]] = {}
        self._topic_stats: dict[str, TopicStats] = {}
        self._closed: bool = False
        return

    def publish(
        self,
        topic: str,
        payload: Any,
        headers: dict[str, str] | None = None
    ) -> Event:
        """
            Publish an event to every matching subscription.

            :param topic: The canonical topic (dot-separated segments).
            :param payload: The event payload.
            :param headers: Optional per-event headers.

            :returns: The Event envelope assigned by the bus.
            :raises: SemanticError if the bus is closed.
        """
        ...

    def subscribe(
        self,
        pattern: str,
        handler: Callable[[Event], None],
        subscriber_name: str,
        overflow_policy: OverflowPolicy | None = None
    ) -> Subscription:
        """
            Register a subscriber for a topic pattern.

            :param pattern: Topic pattern (supports '*' and '#' wildcards).
            :param handler: Callable invoked with each matching Event.
            :param subscriber_name: Unique subscriber identifier.
            :param overflow_policy: Override default overflow behavior.

            :returns: A Subscription handle.
            :raises: SemanticError on duplicate subscriber_name.
        """
        ...

    def drain(
        self,
        timeout_seconds: float
    ) -> DrainResult:
        """
            Stop accepting publishes and wait for subscriber queues to empty.

            :param timeout_seconds: Maximum wait for drain completion.

            :returns: DrainResult with counts of delivered / dropped.
            :raises: None (always returns).
        """
        ...


class Subscription:
    def __init__(
        self,
        bus: MessageBus,
        subscriber_name: str
    ) -> None:
        self._bus = bus
        self._subscriber_name = subscriber_name
        return

    def unsubscribe(self) -> None:
        """
            Remove this subscription from the bus.

            :returns: None
            :raises: None (idempotent).
        """
        ...


def initialize_message_bus(
    app: WebApplication,
    config: MessageBusConfig
) -> MessageBus:
    """
        Build the in-process bus and register lifecycle hooks.

        :param app: The web application.
        :param config: The bus config.

        :returns: The MessageBus singleton.
        :raises: ConfigurationError
    """
    ...
```

### Extension Surface

Phase 0 declares no factory protocol. The conceptual extension surface is
per-topic subscription via `E-extension-hooks` — handlers carry a
`@subscribes_to("entity.job.completed")` decorator (a *registration*
decorator, not a behavior-modifying one, per AGENTS.md rules). The
extension host translates those annotations into `bus.subscribe(...)` calls
during `on_load`.

When a network-backed implementation is introduced in a later phase, it
will be formalized as:

- `factory_protocol_name = "message_bus_driver"`
- `classmethod open(cls, config: MessageBusConfig) -> MessageBus`
- Reference driver: `InProcessMessageBusDriver` (the current impl),
  `PRECEDENCE = 1000` (lowest priority default so a site-local driver wins).

### Events Emitted

The bus does not emit bus-topic events for itself in Phase 0 (to avoid
publish recursion); instead it writes diagnostic log events and metrics.

### Events Consumed

None — the bus is passive infrastructure.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/`:

- `messaging/__init__.py`
- `messaging/bus.py` — `MessageBus`, `Subscription`, `Event`.
- `messaging/config.py` — `MessageBusConfig`, `OverflowPolicy` enum.
- `messaging/matcher.py` — `match_pattern(pattern, topic)` — pure function.
- `messaging/worker.py` — per-subscriber worker thread loop.
- `messaging/stats.py` — `TopicStats` accumulation.
- `messaging/hooks.py` — startup/shutdown hooks against the web app.
- `messaging/errors.py` — `SubscriberInvocationError`.

## Key Flows

### Flow 1 — Publish fan-out

1. Feature calls `bus.publish("entity.run.state_changed", payload)`.
2. `publish` constructs `Event` with new ULID, current UTC, ambient
   `request_id` from the web host ContextVar.
3. `publish` looks up matching subscriptions via `match_pattern`.
4. For each match, `publish` enqueues on the subscriber's private queue.
   If queue full, the topic's `overflow_policy` is applied and
   `pychestrate_bus_overflow_total` is incremented.
5. Metrics: `pychestrate_bus_published_total{topic, status}` incremented
   with `status = matched | unmatched`.
6. Trace span `pychestrate.bus.publish` closes.

### Flow 2 — Subscriber worker loop

1. Worker thread blocks on its queue.
2. On wake, starts span `pychestrate.bus.deliver` with
   `subscriber_name` attribute.
3. Invokes handler inside a try/except; on exception, catches ONCE,
   wraps as `SubscriberInvocationError` with topic + subscriber + cause,
   logs `pychestrate.bus.subscriber.failed`, continues.
4. Records duration to
   `pychestrate_bus_delivery_duration_seconds{topic,subscriber}`.

### Flow 3 — Shutdown drain

1. Host shutdown hook (priority `80`) calls `bus.drain(bus_drain_seconds)`.
2. `drain` sets `_closed = True` — new publishes raise `SemanticError`.
3. Each subscriber worker is signaled to finish its queue, joined with a
   remaining-time budget.
4. `drain` emits `pychestrate.bus.drain.completed` with delivered /
   dropped counts.

## Error Handling

- Subscriber exceptions: caught exactly once, reclassified as
  `SubscriberInvocationError`, logged, NOT re-raised. This is the rare
  legitimate case of catch-and-log per AGENTS.md because the bus cannot
  meaningfully propagate a downstream handler failure back to the
  publisher.
- `SemanticError` from publish-after-close, duplicate subscriber name, or
  invalid pattern: bubbles — never caught.
- `ConfigurationError` from invalid `MessageBusConfig` at startup: bubbles
  to the host, process exits with code 78.

Error message construction example:

```python
err_msg_lines = ["Subscriber handler raised during delivery."]
err_msg_lines.append("SUBSCRIBER: {}".format(subscriber_name))
err_msg_lines.append("TOPIC: {}".format(event.topic))
err_msg_lines.append("EVENT ID: {}".format(event.event_id))
err_msg_lines.append("CAUSE: {}".format(str(cause)))

err_msg = os.linesep.join(err_msg_lines)
logger.error(err_msg)
```

## Security Considerations

- All data is in-process; no network exposure in Phase 0.
- Payload inspection is not logged by default to avoid leaking entity
  content (e.g., secrets). Only envelope fields (`event_id`, `topic`,
  `published_at`, `request_id`) appear in log events.
- Subscribers registered by extensions will be gated by
  `E-extension-sandbox` in Phase 8 — an extension without the `bus:subscribe`
  capability cannot subscribe. Until then, only in-tree code subscribes.
- `request_id` propagation enables audit correlation once `1-audit-log`
  lands.

## Observability

Metrics:

- `pychestrate_bus_published_total{topic,status}` — counter
  (`status` in `{matched, unmatched}`)
- `pychestrate_bus_delivery_duration_seconds{topic,subscriber}` — histogram
- `pychestrate_bus_subscriber_failures_total{topic,subscriber}` — counter
- `pychestrate_bus_buffer_depth{topic}` — gauge (max across subscribers)
- `pychestrate_bus_overflow_total{topic,policy}` — counter

Log events:

- `pychestrate.bus.published` (sampled at 1:1000 by default; 1:1 at debug)
- `pychestrate.bus.subscriber.failed`
- `pychestrate.bus.overflow`
- `pychestrate.bus.drain.started`
- `pychestrate.bus.drain.completed`

Trace spans:

- `pychestrate.bus.publish` — attributes `topic`, `subscriber_count`,
  `matched`
- `pychestrate.bus.deliver` — attributes `topic`, `subscriber_name`,
  `duration_ms`

Dashboards: bus panel in the future `9-admin-ui`; topic-depth alerting in
Phase 9.

## Open Questions

- Default `topic_buffer_max = 10_000` is a guess; revisit after Phase 3
  live-run traffic. Timebox: Phase 3 exit.
- `@subscribes_to` annotation name — align with `codecraftai-extension`
  conventions or adopt Pychestrate-local naming? Timebox: Phase 0.5 start.
- Whether to surface an async (`asyncio`) subscribe variant in Phase 0 or
  defer. Timebox: Phase 0 exit — decision informed by how much of the
  webservice codebase is async.
