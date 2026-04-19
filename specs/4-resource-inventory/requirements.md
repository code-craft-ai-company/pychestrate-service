# 4-resource-inventory — Requirements

## Introduction

The `4-resource-inventory` feature is the authoritative catalog of externally-owned
assets that Pychestrate tracks, deconflicts, leases, and reports on — physical and
virtual devices, IP addresses, IP subnets, software licenses, and anything else a
job might contend for. Pychestrate does not create, destroy, or directly manage
these resources; they are owned by the lab, the network team, the vendor, or a
provisioning system outside the orchestrator. This feature therefore focuses on
*registration*, *typed attribute validation*, *identity stability*, and *lookup*.
It is the flagship landing site for `ResourceKindExtension` — the per-kind
surface that lets an out-of-tree extension pack add a new resource type
(packet-capture rig, lab fridge, IPv6 /64, vendor-specific license token, …) with
typed attributes, validators, and default probe bindings.
Layer 4 sits between the pod plane (`3-client-registry`, `3-pod-definitions`) and
the job dispatcher (`5-job-dispatch`); inventory is the root of that layer and is
consumed by `4-resource-pools`, `4-checkout-checkin`,
`4-conflict-deconfliction`, `4-resource-health`, and `4-usage-history`. The
feature ships in Phase 4.

## Requirements

### Requirement 1: Register and Resolve Resources by Stable Identity

**User Story:** As a lab administrator, I want to register externally-owned
devices, IPs, and licenses with typed attributes, so that jobs have a stable,
addressable catalog to bind against.

**Acceptance Criteria (EARS):**

1. WHEN an administrator POSTs `POST /api/v1/resources` with a registered
   `kind` and a valid attribute payload THEN the system SHALL persist a new
   `Resource` row, assign a time-ordered UUIDv7 `resource_id`, emit
   `entity.resource.registered`, and return `201` with the resource body.
2. IF the payload declares a `kind` that no loaded `ResourceKindExtension`
   claims THEN the system SHALL reject the request with `400` and the error
   body MUST name the unknown kind and list every currently-loaded kind.
3. WHILE a resource has state `retired` the system SHALL NOT allow any new
   reservation or checkout against it; lookups SHALL still resolve it so
   historical reports remain valid.
4. WHERE the registered `kind` declares `identity_attrs` the system SHALL
   enforce uniqueness of that attribute tuple across non-retired resources
   and SHALL reject duplicate registrations with `409 Conflict`.

### Requirement 2: Typed Attributes Validated Against the Resource Kind

**User Story:** As a feature author, I want a resource's attributes to be
validated by the owning `ResourceKindExtension`, so that malformed data can
never land in the inventory.

**Acceptance Criteria (EARS):**

1. WHEN a resource is registered or updated THEN the system SHALL invoke
   `ResourceKindExtension.validate_attributes(attrs)` for the declared kind
   before writing to the database.
2. IF the validator raises `ResourceAttributeError` THEN the system SHALL
   reject the write with `422 Unprocessable Entity` and surface the
   validator's per-field error list verbatim.
3. WHERE a kind declares a subnet attribute the system SHALL require it to
   parse as an RFC 4291 IPv4/IPv6 network and SHALL normalize its string
   representation to CIDR form before persistence.
4. WHEN a kind declares an attribute with `sensitive: true` THEN the system
   SHALL store the value through `1-secrets-vault` and the REST response
   SHALL return a `secret_ref`, never the cleartext value.

### Requirement 3: Resource Lifecycle States are Explicit and Auditable

**User Story:** As an operator, I want resources to move through a small,
explicit set of lifecycle states, so that I can reason about availability
without guessing.

**Acceptance Criteria (EARS):**

1. WHEN a resource is first registered THEN the system SHALL place it in
   state `available`.
2. IF an administrator marks a resource `quarantined` THEN the system SHALL
   emit `entity.resource.quarantined`, refuse all new reservations against
   it, and leave existing active reservations intact.
3. IF an administrator marks a quarantined resource `available` THEN the
   system SHALL emit `entity.resource.healed` and accept reservations again.
4. WHILE a resource is in state `retired` the system SHALL NOT accept any
   further state transition except `retired → retired` (idempotent no-op);
   un-retiring requires a fresh registration with a new `resource_id`.

### Requirement 4: Inventory Query API with Filter-by-Kind and Attribute

**User Story:** As a scheduler component, I want an efficient filter-by-kind
and filter-by-attribute query, so that I can resolve candidate resources in
microseconds during dispatch.

**Acceptance Criteria (EARS):**

1. WHEN `GET /api/v1/resources?kind=<k>&state=available&tags=<t>` is called
   THEN the system SHALL return all matching resources with p99 < 50 ms on a
   50,000-resource inventory.
2. IF the caller passes an unknown filter attribute THEN the system SHALL
   return `400` with the list of supported attributes for that kind.
3. WHERE the kind declares an indexed attribute the system SHALL use the
   declared index and SHALL NOT fall back to a table scan.

## Property-Based Test Requirements

### Property 1: Registration Round-Trip Preserves Attributes

- **Invariant:** For any resource kind K and any attribute payload A that
  `K.validate_attributes(A)` accepts, registering the resource and then
  reading it back yields `attrs == A` (modulo CIDR normalization for subnet
  fields and secret-ref substitution for sensitive fields).
- **Generator:** A Hypothesis strategy that composes one of the in-tree
  `ResourceKindExtension` subclasses and generates valid attribute payloads
  per that kind's declared schema. Subnet fields use `ip_networks()`,
  sensitive fields use `text(min_size=8, max_size=64)`.
- **Assertion:** `loaded.attrs == normalize(A, kind=K)` and every sensitive
  field returns as a `secret_ref` rather than cleartext.
- **Sample size:** 1000 generated cases per registered kind.

### Property 2: Identity Uniqueness is Strict

- **Invariant:** For any sequence of concurrent registration attempts
  supplying the same `identity_attrs` value on the same kind, exactly one
  attempt returns `201` and all others return `409`.
- **Generator:** `hypothesis.strategies.lists(tuples(identity_value,
  payload), min_size=2, max_size=32)` fanned out across N worker threads
  hitting the REST endpoint.
- **Assertion:** `sum(1 for r in results if r.status_code == 201) == 1` and
  every other result is `409` with a body referencing the winning
  `resource_id`.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** Single-resource registration p99 < 80 ms end to
  end. Filtered `GET /api/v1/resources` p99 < 50 ms on a 50k inventory with
  appropriate indices. Attribute validation SHALL complete in under 5 ms for
  any in-tree kind on a payload < 4 KB.
- **NFR-2 (Security):** Registration requires permission
  `resource.inventory.write`; query requires `resource.inventory.read`.
  Sensitive attributes are stored through `1-secrets-vault` and never
  appear in REST responses, logs, metrics, or the audit log. All REST
  inputs are validated before dispatch; a malformed JSON body returns
  `400` without invoking the kind's validator.
- **NFR-3 (Observability):** Emit metrics
  `pychestrate_resource_registered_total{kind}`,
  `pychestrate_resource_quarantined_total{kind}`,
  `pychestrate_resource_healed_total{kind}`,
  `pychestrate_resource_inventory_size{kind,state}` (gauge),
  `pychestrate_resource_query_duration_seconds{kind}` (histogram),
  `pychestrate_resource_attribute_validation_failed_total{kind,field}`.
  Log events `pychestrate.resource.registered`,
  `pychestrate.resource.quarantined`, `pychestrate.resource.healed`,
  `pychestrate.resource.retired`. Trace span
  `pychestrate.resource.register` with attribute `kind`.
- **NFR-4 (Reliability):** Registration writes go through
  `unit_of_work` so a kind-validator failure after a partial write rolls
  back. The query path is read-only and safe to serve from a replica once
  Phase 9 lands read replicas.

## Out of Scope

- Resource reservation / checkout semantics (see `4-checkout-checkin`).
- Pool membership and allocation strategies (see `4-resource-pools`).
- Health probes and quarantine triggers (see `4-resource-health`).
- Per-resource usage timelines (see `4-usage-history`).
- Resource creation / provisioning — Pychestrate never provisions
  externally-owned resources; it only tracks them.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-rbac` (for
  `resource.inventory.*` permissions), `1-secrets-vault` (sensitive
  attributes), `2-tagging` (tag model), `E-resource-extensions`.
- **Depended on by:** `4-resource-pools`, `4-checkout-checkin`,
  `4-conflict-deconfliction`, `4-lease-heartbeat`, `4-resource-health`,
  `4-usage-history`, `5-job-dispatch`.
- **Extension points exposed:** `resource: ResourceKindExtension` — the
  flagship per-kind surface of Layer 4; declares `kind_name`, typed
  `attribute_schema`, `identity_attrs`, indexed attributes, default probe
  binding, and per-kind REST serialization overrides.
