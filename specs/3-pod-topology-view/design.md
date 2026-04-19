# 3-pod-topology-view — Design

## Architecture

The Topology View lives at
`source/site/automojo/pychestrate/webservice/pods/topology/`. It is a
read-through composition layer — it does not own any persistent state of
its own. The composer reads the pinned `pod_definition_version`, the
active `pod_registration`, and the current `pod_runtime_state`, merges
them into a `TopologyGraph` DTO, decorates each member with a
`RendererHint` sourced from `PodMemberRendererExtension`, and returns the
DTO as JSON. The composer is a pure function; a small cache wraps it with
ETag-based conditional response support. Per the architectural ground
rules, the view never reaches past the data Pychestrate already has — no
member probing, no client RPC.

## Data Model

No new tables. Reads join these existing rows:

- `pod_definition_version` (for members, links, tags).
- `pod_registration` (for `report_hash`, `report_json`,
  member report statuses).
- `pod_runtime_state` (for `state`, `in_use_since`, `failure_reason`).
- `client` (for `last_seen`, `last_agent_version`).

DTOs (`pods/topology/dtos.py`):

```
@dataclass(frozen=True)
class TopologyMember:
    name: str
    kind: str
    role: str
    attributes: Mapping[str, Any]
    tags: Sequence[str]
    report_status: ReportStatus       # reported | unreported | divergence
    divergence: bool
    divergence_reason: Optional[str]


@dataclass(frozen=True)
class TopologyLink:
    from_member: str
    to_member: str
    role: str
    attributes: Mapping[str, Any]


@dataclass(frozen=True)
class RendererHint:
    tag: str
    icon_ref: str
    bundle_url: Optional[str]


@dataclass(frozen=True)
class TopologyGraph:
    pod_id: UUID
    project_id: UUID
    definition_version: int
    members: Sequence[TopologyMember]
    links: Sequence[TopologyLink]
    registration_report_hash: Optional[str]
    lifecycle_state: PodState
    renderer_hints: Mapping[str, RendererHint]
    partial: bool
    etag: str
```

## Interfaces

### Public API

- `GET /api/v1/projects/{project_id}/pods/{pod_id}/topology`
  - Permission: `pod.topology.read`.
  - Headers: `If-None-Match`, `Accept-Encoding`.
  - Response: `TopologyGraph` JSON + `ETag` + `Cache-Control` headers.

### Internal API

```python
def compose_topology(
    *,
    pod_id: UUID,
    project_id: UUID,
    caller_permissions: AbstractSet[str],
) -> TopologyGraph:
    ...


def compute_etag(
    *,
    definition_version: int,
    registration_report_hash: Optional[str],
    lifecycle_state: PodState,
) -> str:
    ...


def load_renderer_hints(
    *,
    extension_host: ExtensionHost,
) -> Mapping[str, RendererHint]:
    ...
```

### Extension Surface

```python
class PodMemberRendererExtension(ResourceExtension):
    """
        Declares the WebComponent renderer for a pod member kind.
    """

    member_kind_name: ClassVar[str]
    tag_name: ClassVar[str]        # e.g. "pcx-linux-host"
    icon_ref: ClassVar[str]        # e.g. "lucide:server"
    bundle_path: ClassVar[Optional[str]] = None  # optional static bundle
```

Reference implementations (in-tree, under
`source/site/automojo/pychestrate/extensions/pod_member_renderers/`):

- `LinuxHostRenderer` -> `<pcx-linux-host>`.
- `WindowsHostRenderer` -> `<pcx-windows-host>`.
- `NetworkSwitchRenderer` -> `<pcx-network-switch>`.
- `GenericRenderer` fallback registered at `member_kind_name="*"` with
  highest PRECEDENCE number (lowest priority).

### Events Emitted

None directly. This feature is a read path.

### Events Consumed

- `entity.extension.host_rescan` — invalidates the renderer hint cache.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/pods/topology/
    __init__.py
    dtos.py
    composer.py                -- compose_topology pure function
    etag.py                    -- compute_etag
    renderer_hints.py          -- load_renderer_hints
    rest.py                    -- Flask-RestX router with If-None-Match handling
    metrics.py

source/site/automojo/pychestrate/extensions/pod_member_renderers/
    linux_host.py
    windows_host.py
    network_switch.py
    serial_console.py
    pdu.py
    generic.py                 -- fallback, highest PRECEDENCE
```

## Key Flows

**Warm topology read.** REST handler validates `If-None-Match` against a
computed ETag sourced from three cheap lookups (definition version,
registration report hash, lifecycle state). Match -> 304. Miss ->
composer loads all three rows, produces the `TopologyGraph`, applies
caller-permission filtering to confidential members, serializes, returns
200 with `ETag` and `Cache-Control: private, max-age=<freshness>`.

**Registration divergence.** Composer compares the definition's members
set with the report's members set (both by name). Members in
`definition \ report` mark as `unreported`; members in `report \ definition`
mark as `divergence=true, divergence_reason="extra_member_reported"`.

**Renderer hint resolution.** For each member kind present, composer
consults the renderer cache (populated at startup and on rescan); missing
kinds fall back to the `GenericRenderer` entry.

## Error Handling

- `PodNotFound` — translated to HTTP 404.
- `PermissionDenied` — translated to HTTP 403 (caller lacks
  `pod.topology.read`).
- `PartialComposition` — internal signal, not an exception; raises the
  `partial=true` flag and logs a warning. This is the graceful
  degradation path when the registration row is transiently unreadable.
- `ConfigurationError` — raised at startup if the default
  `GenericRenderer` is not registered.
- `SemanticError` — never caught.
- Multiline error messages use `os.linesep.join([...])`.

## Security Considerations

- RBAC permission: `pod.topology.read`;
  `pod.topology.read.confidential` unlocks members tagged
  `confidential`.
- Renderer bundle URLs served via a namespaced `/static/extensions/
  <ext_name>/<bundle>` path; the extension's filesystem layout is not
  exposed.
- The endpoint is rate-limited to 30 rpm per caller to prevent probing
  attacks against divergent topologies.
- The `report_json` is **not** returned verbatim — the composer
  transforms it into the DTO shape, stripping any unexpected fields.

## Observability

Metrics:

- `pychestrate_pod_topology_reads_total{outcome}` — counter
  (`outcome in {200, 304, 403, 404, 5xx}`).
- `pychestrate_pod_topology_divergence_total{project_id}` — counter.
- `pychestrate_pod_topology_latency_seconds` — histogram.
- `pychestrate_pod_topology_cache_hit_rate` — gauge (for the 304 path).

Log events: `pychestrate_pod_topology_read`,
`pychestrate_pod_topology_renderer_conflict`,
`pychestrate_pod_topology_partial`.

Trace span: `pod_topology.compose`.

## Open Questions

- Should we stream live updates via SSE in this feature or defer to a
  later streaming dashboard? Defer; phase 2 ships pull-only.
- Do we expose a GraphQL-style subset query (`?fields=...`) at this
  point? Defer; phase 10 plugin API surface is the right place.
