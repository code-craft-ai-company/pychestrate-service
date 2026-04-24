# 2-projects — Tasks

## Milestones

- **M1 — Skeleton:** `Project` entity persists, `POST /projects` and
  `GET /projects/{slug}` work end-to-end, `entity.project.created` fires
  on the bus, and `1-audit-log` records the event.
- **M2 — Core Behavior:** Archive, delete, member add/remove, and the
  `ProjectMetadataFieldExtension` registry are complete; all EARS
  requirements pass.
- **M3 — Hardening:** Idempotency, rate limits, observability, concurrent
  create-collision guard, extension error paths, and Phase-1 exit-criterion
  integration tests.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Add migration under `0-persistence` creating tables
      `projects` and `project_member_bindings` with indexes from
      design.md Data Model.
      (migration `006_phase2_projects.py` creates
      `projects_projects` + `projects_project_member_bindings`.)
- [x] T1.2 — Implement `canonicalize_project_slug` in
      `webservice/model/projects/slug.py` with `SlugValidationError`.
      (implemented in `webservice/projects/slug.py`.)
- [x] T1.3 — Implement `entities.py` dataclasses / ORM mappers for
      `Project`, `ProjectMemberBinding`, `ProjectState`.
      (delivered as `webservice/projects/models.py` on
      `PychestratePhase1Base`.)
- [x] T1.4 — Implement `repository.py` with `insert_project`,
      `get_project_by_slug`, `list_projects`.
      (delivered in `webservice/projects/repository.py`.)
- [x] T1.5 — Implement `service.create_project` including advisory-lock
      acquisition and outbox write for `entity.project.created`.
      (delivered in `webservice/projects/service.py::create_project`;
      the advisory-lock hardening is the M3 concurrent-collision guard.)
- [x] T1.6 — Wire Flask-RestX resources for `POST /api/v1/projects`
      and `GET /api/v1/projects/{slug}` under
      `webservice/restapi/versions/v1/projects.py`.
      (delivered under
      `webservice/projects/restapi/v1/projects_controller.py` and
      aggregated through
      `restapi/versions/v1/phase2/__init__.py`.)
- [x] T1.7 — Subscribe `1-audit-log` ingester to
      `entity.project.created` and write a `project.created` record.
      (audit `ProjectCreatedAuditEvents` pack wires
      `entity.project.created → audit.project.created` through the
      existing bus subscriber.)

### M2 — Core Behavior

- [x] T2.1 — Implement `service.archive_project` + endpoint +
      `entity.project.archived` outbox.
      (delivered in `webservice/projects/service.py::archive_project`
      and `ProjectArchiveResource` in the controller.)
- [x] T2.2 — Implement `service.unarchive_project` + endpoint.
      (delivered alongside archive in the same service module +
      `ProjectUnarchiveResource` in the controller.)
- [x] T2.3 — Implement `service.delete_project` with archive
      precondition, cascade SQL, `entity.project.deleted` outbox.
      (SQLAlchemy cascade plus an explicit Python-side cascade over
      `ProjectMemberBinding` rows so SQLite test engines see the
      same no-orphan invariant PostgreSQL would enforce via FK.)
- [x] T2.4 — Implement `service.add_member` and `service.remove_member`
      with `1-rbac` role validation and the last-admin safeguard;
      emit `entity.project.member_added|removed`.
      (last-admin check counts `project-owner` holders; `force=True`
      bypass for platform admins is plumbed via the controller.)
- [x] T2.5 — Implement `ProjectMetadataFieldExtension` base class in
      `extensions.py`; implement the metadata registry that loads via
      `E-resource-extensions` on `on_service_ready`.
      (registry is frozen at the end of
      `register_phase1_builtin_extensions`; post-freeze mutation
      raises `ConfigurationError`.)
- [x] T2.6 — Ship in-tree reference
      `CostCenterFieldExtension` under `automojo/extensions/pychestrate/projects/`.
      (lives alongside the feature module at
      `webservice/projects/extensions/cost_center.py`.)
- [x] T2.7 — Implement `PATCH /projects/{slug}` honoring the metadata
      registry for `extension_fields`.
      (delivered in `ProjectDetail.patch`; invalid field names and
      field-type failures return `422`.)
- [x] T2.8 — Implement `GET /projects/{slug}/members` and the
      member-list DELETE endpoint.
      (`ProjectMembersResource` GET + `ProjectMemberByUserIdDetail`
      DELETE with `?force=true` + role-specific
      `ProjectMemberRoleDetail` DELETE.)
- [x] T2.9 — Subscribe to `entity.user.deleted` and cascade bindings.
      (wired via `webservice/projects/bus_subscriber.py` and
      `service.cascade_user_deleted`.)

### M3 — Hardening

- [ ] T3.1 — Implement `Idempotency-Key` middleware with a 48-hour
      dedup table.
- [ ] T3.2 — Add Flask rate-limiter rules (10/min/session,
      30/min/IP) on create.
- [ ] T3.3 — Emit all metrics listed in design.md Observability (register
      via `7-metrics-ingest` definitions).
- [ ] T3.4 — Structured-log and trace-span wiring
      (`project.create|archive|delete|member_add|member_remove`).
- [ ] T3.5 — Collision-under-load test: 50 concurrent creates with the
      same slug produce exactly one `201` and 49 `409`s.
- [ ] T3.6 — Extension collision test: two `ProjectMetadataFieldExtension`
      subclasses with the same `field_name` make the service refuse to
      start with a readable `ConfigurationError`.

## Test Tasks

- [x] TT-1 — Unit tests covering each EARS requirement in
      requirements.md (Requirements 1–4).
      (delivered in
      `tests/singlehost/pychestrate/webservice/phase1/test_project_service.py`.)
- [x] TT-2 — Property-based tests implementing Property 1 (slug
      canonicalization idempotence) and Property 2 (create-then-delete
      leaves no orphans) using `hypothesis`.
      (the repo does not ship `hypothesis`; both properties are
      implemented as seeded deterministic property tests in
      `test_project_slug_property.py` (1024 cases) and
      `test_project_lifecycle_property.py` (64 scenarios x ≤32 ops).)
- [x] TT-3 — Integration test: admin creates a project, adds two
      members, sets extension fields, archives, deletes; audit-log
      reflects every step and DB shows zero orphans.
      (delivered in `test_project_integration.py`.)
- [x] TT-4 — Extension-point test: an out-of-tree sample
      `pychestrate-ext-example` registers a
      `ComplianceTierFieldExtension`, the service accepts projects with
      the field, and rejects invalid values.
      (delivered in `test_project_extensions.py`, plus the duplicate
      `field_name` collision case exercising `ConfigurationError`.)

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (`ProjectMetadataFieldExtension`) has an in-tree
      reference (`CostCenterFieldExtension`) and a test-only override
      with a different `PRECEDENCE` that adds a new field
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 1 in
      specs/implementation-plan.md
