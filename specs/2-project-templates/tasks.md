# 2-project-templates — Tasks

## Milestones

- **M1 — Skeleton:** `ProjectTemplateExtension` base lands, registry
  populates on startup, list/get endpoints return registered templates,
  `projects` table carries `template_id` + `template_version`.
- **M2 — Core Behavior:** Apply at create works inside the project
  create transaction, calling the variable / tag / notification
  services; reapply with all three overwrite policies; in-tree
  reference templates shipped; diff API works.
- **M3 — Hardening:** Atomicity / rollback under injected failures,
  observability, collision detection, reapply confirmation semantics,
  and the Phase-10 exit-criterion end-to-end test.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Add `template_id` (string) and `template_version`
      (string) columns to the `projects` table in `0-persistence`.
- [ ] T1.2 — Implement `entities.py` (`ProjectTemplateRecord`,
      `TemplateVariableSpec`, `TemplateTagSpec`,
      `TemplateNotificationRuleSpec`, `TemplateApplyDiff`).
- [ ] T1.3 — Implement `extensions.py` (`ProjectTemplateExtension`
      base).
- [ ] T1.4 — Implement `registry.py` that loads templates on
      `on_service_ready`, detects `template_id` collisions at equal
      `PRECEDENCE`, and surfaces a readable `ConfigurationError`.
- [ ] T1.5 — Implement `service.list_templates`,
      `service.get_template`.
- [ ] T1.6 — Wire REST endpoints
      `GET /api/v1/project-templates` and
      `GET /api/v1/project-templates/{template_id}`.

### M2 — Core Behavior

- [ ] T2.1 — Extend
      `variables.service.set_variable`,
      `tagging.service.assign_tag`,
      `notifications.service.create_routing_rule` to accept an
      explicit `transaction` handle so they enlist on the caller's
      txn.
- [ ] T2.2 — Implement
      `service.apply_template_to_project(transaction=…)` — atomic
      apply of variables, tags, and notification rules.
- [ ] T2.3 — Integrate the apply call into
      `projects.service.create_project` when the body carries
      `template_id`; stamp `template_id` + `template_version` on the
      project row.
- [ ] T2.4 — Implement `service.diff_template_against_project`.
- [ ] T2.5 — Implement `service.reapply_template` honoring the three
      `overwrite_policy` values.
- [ ] T2.6 — Wire REST endpoint
      `POST /api/v1/projects/{slug}/reapply-template`.
- [ ] T2.7 — Ship `StandardCiTemplate` and
      `ComplianceProjectTemplate` under
      `ccai/extensions/pychestrate/project_templates/`.
- [ ] T2.8 — Emit `entity.project.template_applied` and
      `entity.project.template_reapplied` with
      `TemplateApplyDiff` payload.

### M3 — Hardening

- [ ] T3.1 — Fault-injection test harness — random downstream
      validation failures verify that the whole create transaction
      rolls back with zero template items persisted.
- [ ] T3.2 — Add `project.template.reapply` permission definition
      under `1-rbac` and gate the endpoint.
- [ ] T3.3 — Emit all metrics / logs / trace spans listed in
      design.md Observability.
- [ ] T3.4 — Audit-log entries for `project.template_applied` and
      `project.template_reapplied` including the diff counts.
- [ ] T3.5 — Add UI-facing `recommended_roles` field in
      `POST /projects` response body when a template was applied.
- [ ] T3.6 — Template registration collision detection proven by
      startup test.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in
      requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests for Property 1 (apply atomicity
      under fault injection) and Property 2 (reapply `skip_existing`
      idempotence) using `hypothesis.stateful`.
- [ ] TT-3 — Integration test: create a project with
      `StandardCiTemplate`, verify variables, tags, and notification
      rules exist; reapply with `overwrite_all` after the template
      version bumps and confirm diff reflects the expected writes.
- [ ] TT-4 — Extension-point test: out-of-tree
      `pychestrate-ext-team-alpha` registers `TeamAlphaTemplate`,
      the template appears in `GET /project-templates`, and a
      project created against it has its declared content.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (`ProjectTemplateExtension`) has two in-tree
      reference templates and at least one test-only override at a
      different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 10 in
      specs/implementation-plan.md
