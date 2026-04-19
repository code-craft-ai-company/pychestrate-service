# 6-environment-registry — Requirements

## Introduction

The `6-environment-registry` feature is the catalog of declared
environments (`dev`, `staging`, `prod`, `hotfix`, site-specific kinds)
plus their current version pointers (`output_digest_sha256`,
`last_applied_run_id`, `frozen`). Runs dispatched by
`6-infra-orchestration` target an environment from this registry;
`6-drift-detection` checks declared-vs-actual against these rows;
`6-blast-radius-guards` evaluate rules with environment attributes as
inputs. Ships in **Phase 7** alongside `6-infra-orchestration`,
`6-drift-detection`, and `6-blast-radius-guards`. Environment *kinds*
are pluggable via `EnvironmentKindExtension`. Authoritative source of
truth for environment declarations and current version state is the
table owned here; the infra tool (Terraform state, etc.) holds the
actual infrastructure state and is consulted by `6-drift-detection`.

## Requirements

### Requirement 1: Declare And List Environments

**User Story:** As an infra owner, I want to declare environments for
a project so that runs and guards can reference them by stable id.

**Acceptance Criteria (EARS):**

1. WHEN `env.declare(project_id, name, kind_name, attrs)` is called AND RBAC `env.declare` passes THEN the system SHALL insert an `Environment` row with a fresh `environment_id: UUID`, `state = "active"`, and `attrs` validated against the declared `EnvironmentKindExtension` schema.
2. WHEN `env.list(project_id, kind_name=None, state=None, limit=, cursor=)` is called THEN the system SHALL return a paginated list ordered by `(name, environment_id)` ascending.
3. IF `attrs` fail the kind's JSON schema THEN the system SHALL raise `SemanticError` listing the schema errors.
4. WHERE the project declares `require_unique_kind_names: True` THEN the system SHALL raise `SemanticError` on an attempt to declare two environments with the same `(kind_name, name)`.
5. WHEN `env.archive(environment_id, reason)` is called THEN the system SHALL set `state = "archived"` and `archived_reason = reason`; archived environments SHALL NOT accept infra runs.

### Requirement 2: Current Version Pointer Maintained By Infra Runs

**User Story:** As a reviewer, I want to see what was last applied to
`staging` so that I can trace production drift back to a specific run.

**Acceptance Criteria (EARS):**

1. WHEN `env.record_apply(environment_id, run_id, output_digest_sha256)` is called AND the caller is `6-infra-orchestration` THEN the system SHALL persist `last_applied_run_id = run_id`, `last_output_digest = output_digest_sha256`, and `last_applied_at = now()`.
2. WHEN `env.mark_destroyed(environment_id, run_id)` is called THEN the system SHALL persist `state = "destroyed"` and `destroyed_at = now()`.
3. WHEN `env.get(environment_id)` is called THEN the system SHALL return the current `EnvironmentView` including its last-applied metadata and any `frozen` flag.
4. WHERE `frozen == True` THEN `env.get` SHALL include `frozen_by: UUID` and `frozen_reason: str` in the view.

### Requirement 3: Kind Extension And Attributes

**User Story:** As an extension author, I want to register a new
environment kind (`k8s-cluster`, `vm-pool`, `cloud-account`), so that
our Pychestrate instance can catalog them with first-class attributes.

**Acceptance Criteria (EARS):**

1. WHEN the extension host discovers an `EnvironmentKindExtension` THEN the system SHALL verify `kind_name: str`, `attrs_schema: dict`, `default_probes() -> list[HealthProbeSpec]`, `default_guards() -> list[GuardRuleRef]` class members AND raise `ConfigurationError` naming missing ones.
2. IF two kinds share `kind_name` AND `PRECEDENCE` THEN the system SHALL raise `ConfigurationError` at load time.
3. WHEN a kind declares `default_probes` THEN newly declared environments of that kind SHALL have those probes attached by default; an admin may override them.
4. WHERE a kind declares `default_guards: list[GuardRuleRef]` THEN newly declared environments SHALL have those guards applied unless overridden via `env.set_guards(...)`.

## Property-Based Test Requirements

### Property 1: Schema Validation Is Deterministic

- **Invariant:** For any `(kind_name, attrs)` pair, repeated `env.declare(...)` attempts yield the same outcome (accept or reject with identical error list) across invocations with equal inputs.
- **Generator:** `hypothesis.strategies.tuples(sampled_from(["k8s-cluster","vm-pool","cloud-account"]), dictionaries(text(min_size=1, max_size=32), one_of(text(), integers(), booleans()), max_size=10))`.
- **Assertion:** `declare(project, name, kind, attrs).normalize() == declare(project, f"{name}-b", kind, attrs).normalize()` in accept-or-reject classification and error messages (names vary).
- **Sample size:** 1000 generated cases

### Property 2: Current Version Pointer Is Monotonic In (applied_at, run_id)

- **Invariant:** For any sequence of `record_apply` calls interleaved arbitrarily, the stored `last_applied_run_id` always reflects the apply with the largest `(applied_at, run_id)` observed.
- **Generator:** `hypothesis.strategies.lists(tuples(uuids(), datetimes()), min_size=1, max_size=50)`.
- **Assertion:** After all calls, `stored.last_applied_run_id == max_by(calls, key=(applied_at, run_id)).run_id`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** `env.declare` p99 < 90 ms; `env.get` p99 < 40 ms; `env.list` p99 < 120 ms at 1 000 envs per project; `record_apply` p99 < 80 ms.
- **NFR-2 (Security):** `env.declare` / `env.archive` / `env.freeze` / `env.set_guards` gated by `env.admin` or kind-specific `env.admin:<kind>`. `record_apply` is internal-only and only `6-infra-orchestration`'s service principal may call it. Attributes never carry secret values; secret refs only.
- **NFR-3 (Observability):** Metrics `pychestrate_infra_environments_total{project,kind,state}` (gauge), `pychestrate_infra_env_declare_duration_seconds{project}` (histogram), `pychestrate_infra_env_freeze_changes_total{project,direction}` (counter), `pychestrate_infra_env_record_apply_total{project,kind}` (counter). Log events `pychestrate.infra.env.declared`, `pychestrate.infra.env.archived`, `pychestrate.infra.env.frozen`, `pychestrate.infra.env.unfrozen`, `pychestrate.infra.env.record_apply`. Trace spans `pychestrate.infra.env.declare`, `pychestrate.infra.env.record_apply`, `pychestrate.infra.env.freeze`.
- **NFR-4 (Reliability):** Concurrent `record_apply` calls SHALL be serialized per environment via row-level locking; the winning call must hold the row lock at commit time to update pointers.

## Out of Scope

- Dispatching infra jobs (see `6-infra-orchestration`).
- Drift detection (see `6-drift-detection`).
- Guard rules and their editing (see `6-blast-radius-guards`).
- Environment provisioning — this feature only catalogs what exists.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `1-rbac`, `1-audit-log`, `2-projects`, `E-extension-host`.
- **Depended on by:** `6-infra-orchestration`, `6-drift-detection`, `6-blast-radius-guards`, `7-orchestration-metrics`.
- **Extension points exposed:** `resource: EnvironmentKindExtension` — k8s cluster, VM pool, cloud account, database-service, custom.
