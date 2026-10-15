# 1-user-management — Tasks

## Milestones

- **M1 — Skeleton:** `users`/`groups` tables live, `create_user` and
  `read_user` work end-to-end with events firing on
  `0-message-bus`; local-only provisioning path verified.
- **M2 — Core Behavior:** Full CRUD, group membership, deactivation /
  reactivation, profile updates with email re-verification, and the
  `user_directory_source` factory protocol with the
  `LocalDatabaseUserDirectorySource` reference implementation.
- **M3 — Hardening:** Out-of-tree directory-source extension loads via
  `E-extension-host`, directory-sync resilience, metrics/logs, Sphinx
  docs, performance baseline.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Define SQLAlchemy models for `User`, `Group`, `GroupMembership`
      under `identity/users/models.py` and ship an
      `EntityMigrationExtension` pack against `0-persistence`.
      *(Models landed in `identity/users/models.py` as `IdentityUser`,
      `IdentityGroup`, `IdentityGroupMembership`, `IdentityEmailVerification`.
      Alembic migration at
      `source/packages/ccai/pychestrate/core/migrations/versions/004_phase1_identity_tables.py`
      covers all four plus the cross-feature Phase-1 tables. A proper
      `EntityMigrationExtension` wrapper lands with the `0-persistence`
      feature work; the Alembic migration is the deployable unit today.)*
- [x] T1.2 — Implement `user_repository.py` with `insert`, `get_by_id`,
      `get_by_login_name`, `get_by_email`, and pagination helpers.
- [x] T1.3 — Implement `user_service.create_user` and `read_user` with
      named-parameter-only signatures and explicit returns.
- [x] T1.4 — Wire the REST controller `users_controller.py` for
      `POST /api/v1/identity/users` and `GET /api/v1/identity/users/{id}`.
- [x] T1.5 — Publish `entity.user.created` through the persistence
      outbox and confirm delivery via a no-op subscriber.
      *(Outbox wired through `messaging/outbox.py` + `messaging/event_bus.py`
      in-process stub; subscriber verification to be added with `0-message-bus`.)*

### M2 — Core Behavior

- [ ] T2.1 — Implement `deactivate_user` and `reactivate_user` with
      session-revocation callback into `1-authentication`.
- [ ] T2.2 — Implement `list_users` with filters and cursor pagination.
- [ ] T2.3 — Build `group_repository.py` and add group CRUD + membership
      endpoints.
- [ ] T2.4 — Implement email re-verification flow with
      `user_email_verifications` table and 24-hour token expiry.
- [ ] T2.5 — Declare the `user_directory_source` `FactoryProtocolBase`
      with classmethod signatures (`iter_user_records`,
      `iter_group_records`, `source_name`) and
      `protocol_schema_version = 1`.
- [ ] T2.6 — Ship `LocalDatabaseUserDirectorySource` at `PRECEDENCE = 1000`
      as the reference in-tree implementation.
- [ ] T2.7 — Implement `directory_sync.run_directory_sync` including
      snapshot diff, outbox event emission, and `DirectorySyncReport`.
- [ ] T2.8 — Add `POST /api/v1/identity/directory/{source_name}/sync`
      controller.
- [ ] T2.9 — Emit PII-tagged structured log events for every mutation.

- [x] T2.10 — `anonymise_identity_user` (Requirement 5): the migration adding
      `identity_users.anonymised_at`, the service function, the admin action
      (`POST /admin/users/{id}/anonymise`, typed confirmation), the
      "Anonymised" status in the list, detail and CSV export, and the
      refusals to reactivate or edit an anonymised user. Tests: every table in
      the design's table is emptied of the user; every refusal changes nothing.
- [x] T2.11 — `POST /api/v1/identity/users/{user_id}/anonymise` (the same service
      function; 409 with the reason when refused) and its OpenAPI entry.
      *Done 2026-10-15, with `deactivate` and `reactivate` beside it (anonymising
      needs a deactivated account, so a script had no way to prepare one): all three
      call the functions the Users pages call, so the rules cannot differ.*
- [~] T2.12 — Scrub the anonymised user's login name and email from earlier
      audit-log payloads and outbox rows by `user_id` (with
      `2-retention-policies`), and from notification routing-rule recipients.
      *Decided 2026-10-15 not to build. Audit records are a hash chain over their
      payloads (`audit.chain_verifier`): rewriting one breaks verification of every
      record after it, and re-chaining would defeat the tamper-evidence the log is for.
      An operator who must remove old entries uses a retention policy, which expires
      whole entries (subject to legal hold), not edited ones. Routing-rule recipients
      are text an administrator typed: the guide tells them to look for the person's
      address on Admin, Notifications when answering a request.*

### M3 — Hardening

- [ ] T3.1 — Add Prometheus metrics listed in requirements.md NFR-3
      (counters plus the sync duration histogram).
- [ ] T3.2 — Add trace spans `user_service.create_user`,
      `user_service.deactivate_user`,
      `directory_sync.run_directory_sync`.
- [ ] T3.3 — Implement `DirectoryCollisionError` handling with a detailed
      multi-line error message built via `os.linesep.join(...)`.
- [ ] T3.4 — Benchmark `list_users` against a 10k-row fixture and hold
      the < 25 ms p95 target.
- [ ] T3.5 — Generate Sphinx docs for the public and internal API.
- [ ] T3.6 — Ship an out-of-tree `pychestrate-ext-fixture-hr-directory`
      sample and load it via `E-extension-host` in the integration suite.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      `requirements.md` Requirements 1–4.
- [ ] TT-2 — Hypothesis-based property tests: Property 1 (create/read
      round trip), Property 2 (directory sync idempotency), Property 3
      (deactivation monotonicity), 1000 cases each.
- [ ] TT-3 — Integration test: admin creates a user, adds to group,
      deactivates, reactivates, confirms each event hits
      `1-audit-log` exactly once and that re-reading the user reflects
      the final state.
- [ ] TT-4 — Extension-point test: a test-only
      `FixtureHrUserDirectorySource` at `PRECEDENCE = 500` overrides the
      local source for its `source_name`, syncs, and produces the
      expected events without touching service source.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has at least one in-tree reference
      implementation (`LocalDatabaseUserDirectorySource`) and one
      test-only override using a different `PRECEDENCE`
      (`FixtureHrUserDirectorySource`)
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 1 —
      Identity & Projects in specs/implementation-plan.md
