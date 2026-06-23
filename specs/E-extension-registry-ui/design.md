# E-extension-registry-ui — Design

## Architecture

E-extension-registry-ui is a pair of admin pages rendered under
`9-admin-ui`, composed of WebComponents whose data source is the
existing REST surface exposed by earlier Layer E features. No new
state is owned here — the UI is a view over the authoritative
registries. A small backend shim in Python composes data from the
host, manifest registry, health table, subscription router, sandbox
authority, and compat checker into the JSON shapes expected by the
front-end.

## Data Model

N/A in persistent storage. The composite shapes are:

- `ExtensionListRow` — JSON:
  - `name, version, state, precedence_count, protocols_count,
    kinds_count, capabilities_count, last_error_at`
- `ExtensionDetailPayload` — JSON:
  - `manifest: ExtensionManifest`
  - `state: ExtensionHealthState`
  - `capabilities: List[str]`
  - `precedence_pins: List[PrecedencePin]`
  - `subscriptions: List[HookSubscription]`
  - `recent_failures: List[ExtensionLifecycleRecord]`
  - `compat: List[CompatReportRow]`

## Interfaces

### Public API

REST (read-only composite; actions route to existing per-feature
endpoints):

- `GET /admin/extensions` — list view.
- `GET /admin/extensions/{name}` — detail view.
- `GET /admin/extensions/stream` — WebSocket; streams row updates
  from the bus.

### Internal API

Code under
`source/site/ccai/pychestrate/webservice/extension/ui/`.

```python
# composer.py
class ExtensionViewComposer:
    """
        Composes per-extension view payloads from the authoritative
        Layer E registries.
    """

    def __init__(self, *, host: "ExtensionHost",
                 manifests: "ManifestRegistry",
                 lifecycle: "LifecycleCoordinator",
                 router: "SubscriptionRouter",
                 authority: "CapabilityAuthority",
                 compat: "CompatChecker") -> None:
        ...

    def build_list(self) -> List[ExtensionListRow]:
        ...

    def build_detail(self, *, ext_name: str) -> ExtensionDetailPayload:
        ...


def get_extension_view_composer() -> ExtensionViewComposer:
    ...


# stream.py
class ExtensionViewStream:
    """
        WebSocket endpoint serving incremental row updates.
    """

    def __init__(self, *, bus: "MessageBus",
                 composer: ExtensionViewComposer) -> None:
        ...

    def on_connect(self, *, ws: "WebSocket", auth: "Principal") -> None:
        ...

    def on_disconnect(self, *, ws: "WebSocket") -> None:
        ...
```

WebComponent tag surface (`source/site/.../webinterface/static/components/`):

- `<pychestrate-extension-list filter="unhealthy">`
- `<pychestrate-extension-detail name="...">`
- `<pychestrate-extension-panel slot="...">` — host element extensions
  can contribute into.

### Extension Surface

- `ExtensionDetailPanelExtension` — `ResourceExtension` base class.
  Subclasses declare `panel_slot_name` and `render(ext_detail)`
  returning an HTML fragment; the detail page composes them under
  the "Custom Panels" section.

### Events Emitted

- `extension.ui_view_rendered` — `{page, ext?, actor}`
- `extension.ui_action_requested` —
  `{page, action, target_ext, actor}`
- `extension.ui_action_completed` —
  `{page, action, target_ext, actor, result, correlation_id}`

### Events Consumed

- `extension.loaded`, `extension.unloaded`,
  `extension.call_failed`, `extension.quarantined`,
  `extension.capability_granted`, `extension.capability_revoked`,
  `extension.rescan_completed` — all trigger stream updates.

## Component Breakdown

```
source/site/ccai/pychestrate/webservice/extension/ui/
    __init__.py
    composer.py            # ExtensionViewComposer
    stream.py              # ExtensionViewStream (WebSocket)
    admin_routes.py        # GET /admin/extensions[/{name}]
    panels.py              # ExtensionDetailPanelExtension base
source/site/ccai/pychestrate/webservice/webinterface/static/components/
    pychestrate-extension-list.js
    pychestrate-extension-detail.js
    pychestrate-extension-panel.js
```

## Key Flows

### Flow A — List view

1. Operator navigates to `/admin/extensions`; WebComponent issues
   `GET /admin/extensions`.
2. Composer reads host snapshot, manifests, lifecycle health,
   subscription counts, capabilities, compat counts; produces rows.
3. WebComponent renders; opens the stream WebSocket.
4. Bus events fan out via the stream; WebComponent patches rows
   in place.

### Flow B — Detail view + action

1. Operator clicks a row → `/admin/extensions/{name}`.
2. Composer produces detail payload; panels for contributed
   `ExtensionDetailPanelExtension` subclasses render.
3. Operator clicks "Grant `dispatch:jobs`" → component POSTs to
   `/admin/extensions/{name}/capabilities/grant` (owned by
   `E-extension-sandbox`).
4. Response + `extension.capability_granted` event arrive; UI
   refreshes the capability list.

### Flow C — Stream fallback

1. WebSocket drops; component retries 3 times with backoff.
2. On exhaustion, component falls back to polling
   `GET /admin/extensions` every `ui_refresh_seconds`.

## Error Handling

- `ConfigurationError` never reaches the UI — composer catches at the
  boundary and reclassifies into a JSON error body `{code, detail}`.
- `PermissionError` from action endpoints → 403; UI hides the button
  and logs the attempt.
- Action button disabled states use `aria-disabled`; no silent
  failures.

## Security Considerations

- All GET endpoints gated by `extensions.read`.
- Action POSTs reuse per-feature permission (`extensions.rescan`,
  `extensions.grant`, `extensions.quarantine`).
- WebSocket accepts the same session cookie as admin REST; closes
  without negotiation if unauthenticated.
- CSRF tokens present on every action POST; origin check enforced.

## Observability

- Metrics:
  - `pychestrate_extension_ui_view_total{page}`
  - `pychestrate_extension_ui_action_total{action,result}`
  - `pychestrate_extension_ui_stream_connections`
  - `pychestrate_extension_ui_stream_dropped_total{reason}`
- Log events: `pychestrate_extension_ui_action_requested`,
  `pychestrate_extension_ui_action_completed`,
  `pychestrate_extension_ui_stream_connected`,
  `pychestrate_extension_ui_stream_dropped`.
- Trace span: `pychestrate_extension.ui.render`,
  `pychestrate_extension.ui.stream`.

## Open Questions

- Should we expose a GraphQL surface in addition to the composite
  REST endpoint? Deferred.
- Should per-tenant views filter out cross-tenant extensions? Phase 10
  decision; currently single-tenant.
