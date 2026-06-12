# E-extension-hooks — Design

## Architecture

E-extension-hooks wires extension classmethods to `0-message-bus` as
subscribers. The decorator `@subscribes_to` attaches metadata to the
method; at `on_load` time the lifecycle coordinator walks the class and
registers each decorated method with `SubscriptionRouter`. The router
tracks subscriptions keyed by owner class so unload can remove them
atomically. Delivery is performed on an executor with per-handler
timeout and aspect-configured retry; failures feed back into
`E-extension-lifecycle` to drive quarantine decisions.

## Data Model

In-memory (no SQL):

- `HookSubscription` — dataclass:
  - `owner_qualname: str`
  - `topic: str`
  - `method: Callable`
  - `aspects: HookAspects`
  - `registered_at: datetime`
- `HookAspects` — dataclass (Aspects pattern):
  - `timeout_seconds: float = 5.0`
  - `retry_max: int = 0`
  - `retry_backoff_seconds: float = 1.0`
  - `max_consecutive_failures: int = 10`
  - `log_payload: bool = False`
- `HookDeliveryRecord` — dataclass:
  - `subscription: HookSubscription`
  - `event_topic: str`
  - `started_at: datetime`
  - `duration_seconds: float`
  - `status: Literal["ok","timeout","error","quarantined"]`
  - `error_type: Optional[str]`

## Interfaces

### Public API

REST (Phase 10 via `E-extension-registry-ui`):

- `GET /admin/extensions/{name}/subscriptions` — permission
  `extensions.read` — lists active subscriptions.

### Internal API

Code under
`source/site/ccai/pychestrate/webservice/extension/hooks/`.

```python
# decorator.py
def subscribes_to(*, topic: str, aspects: Optional["HookAspects"] = None) -> Callable:
    """
        Attaches subscription metadata (topic, aspects) to a classmethod.

        :param topic: Bus topic pattern, e.g. 'entity.job.completed'.
        :param aspects: Optional HookAspects instance (Aspects pattern).
        :returns: A passthrough decorator that does NOT modify behavior.
    """
    ...


# router.py
class SubscriptionRouter:
    """
        Registers bus subscriptions for extension classes and routes
        delivery with per-handler timeout + retry.
    """

    def __init__(self, *, bus: "MessageBus", health: "ExtensionHealthTable") -> None:
        ...

    def register_for_class(self, *, extension_cls: Type) -> List[HookSubscription]:
        ...

    def unregister_for_class(self, *, extension_cls: Type) -> None:
        ...

    def count_subscriptions(self, *, owner: Optional[Type] = None) -> int:
        ...

    def list_subscriptions(self, *, owner: Optional[Type] = None) -> List[HookSubscription]:
        ...

    def _deliver(self, *, subscription: HookSubscription,
                 event_topic: str, event_payload: Any) -> HookDeliveryRecord:
        ...


def get_subscription_router() -> SubscriptionRouter:
    ...
```

### Decorator example

```python
class JobCompletedAuditExtension(ResourceExtension):

    @classmethod
    @subscribes_to(topic="entity.job.completed",
                   aspects=HookAspects(timeout_seconds=5.0, retry_max=0))
    def on_job_completed(cls, *, event: "JobCompletedEvent") -> None:
        ...
```

### Extension Surface

- `@subscribes_to(topic=..., aspects=...)` — decorator-as-metadata
  (AGENTS.md-approved use case: "registering a function with a mapping
  system").
- `HookAspects` — the Aspects parameter that callers use to customize
  delivery behavior without behavior-modifying decorators.

### Events Emitted

- `extension.hook_delivered` —
  `{topic, ext, duration_seconds, status}`
- `extension.hook_delivery_failed` —
  `{topic, ext, reason, traceback}`
- `extension.subscription_registered` —
  `{owner, topic}`
- `extension.subscription_removed` —
  `{owner, topic}`

### Events Consumed

- `extension.loaded` — triggers `register_for_class`.
- `extension.unloaded` — triggers `unregister_for_class`.
- Every domain topic that has a subscriber attached.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/extension/hooks/
    __init__.py
    decorator.py           # subscribes_to metadata decorator
    aspects.py             # HookAspects dataclass
    router.py              # SubscriptionRouter
    delivery.py            # _deliver with timeout + retry
    records.py             # HookDeliveryRecord dataclass
    admin_routes.py        # GET /admin/extensions/{name}/subscriptions
```

## Key Flows

### Flow A — Load

1. Lifecycle coordinator calls `SubscriptionRouter.register_for_class`
   with the extension class after `on_load` succeeds.
2. Router walks the class for classmethods with
   `_subscribes_to_metadata` attribute (set by the decorator).
3. For each found, it registers the handler with `bus.subscribe(
   topic=..., handler=..., owner_key=qualname)` and records a
   `HookSubscription`.
4. Emits `extension.subscription_registered` events.

### Flow B — Delivery

1. Bus fires a topic; router receives the call.
2. For each matching subscription, router submits
   `_deliver(subscription=, event_topic=, event_payload=)` to the
   executor with `aspects.timeout_seconds`.
3. On success: records metric, emits `extension.hook_delivered`.
4. On timeout or exception: records failure, applies retry per
   aspects; on exhaustion, emits `extension.hook_delivery_failed` and
   updates health table.

### Flow C — Unload

1. Lifecycle `on_unload` calls `unregister_for_class`.
2. Router calls `bus.unsubscribe_all(owner_key=qualname)` and removes
   its local records; emits `extension.subscription_removed` events.

## Error Handling

- `ExtensionHookError` wraps any raised exception with
  `(topic, qualname, aspects)`.
- Handler exceptions are never re-raised out of `_deliver`; they are
  logged, recorded, and potentially retried.
- `SemanticError` from within a handler is still re-raised (never
  caught).
- Multiline error messages via `os.linesep.join`.

## Security Considerations

- Each delivery passes through `extension_sandbox.authorize(
  capability="dispatch:events", ext_name=...)` once Phase 8 lands;
  before then it is a pass-through.
- Bus topics with sensitive payloads require a matching
  `read:<scope>` capability on the subscriber's manifest; router
  refuses subscription if missing, emits
  `extension.subscription_rejected`.

## Observability

- Metrics:
  - `pychestrate_extension_hook_delivered_total{topic,ext,result}`
  - `pychestrate_extension_hook_duration_seconds{topic,ext}`
  - `pychestrate_extension_hook_timeouts_total{topic,ext}`
  - `pychestrate_extension_hook_retries_total{topic,ext}`
- Log events: `pychestrate_extension_hook_delivered`,
  `pychestrate_extension_hook_delivery_failed`,
  `pychestrate_extension_hook_retry`.
- Trace span: `pychestrate_extension.hook.dispatch`.

## Open Questions

- Should the router support per-tenant subscription partitioning for
  multi-tenant isolation? Timebox to Phase 10.
- Should subscription persistence be durable (survive restart) or
  always rebuilt? In-process only for now.
