# 1-user-management — Requirements

## Introduction

`1-user-management` owns the canonical identity records for Pychestrate: user
accounts, group memberships, and profile data. It sits in Layer 1 alongside
`1-authentication` (which proves *who* a principal is) and `1-rbac` (which
decides *what* they may do); `1-user-management` is the authoritative registry
the other two read from. It ships in **Phase 1 — Identity & Projects** as a
direct dependency of `2-projects` (project membership is expressed in terms of
users and groups) and is consumed by `1-audit-log` for actor attribution on
every mutation. The feature exposes the `user_directory_source` factory
protocol so enterprises can plug in LDAP, SCIM, or custom HR-system sync
without forking the service.

## Requirements

### Requirement 1: Account Lifecycle

**User Story:** As a platform administrator, I want to create, update, and
deactivate user accounts, so that access to Pychestrate tracks real workforce
membership.

**Acceptance Criteria (EARS):**

1. WHEN an administrator submits a valid `create_user` request with a unique
   `login_name` and a routable `primary_email` THEN the system SHALL persist a
   `User` row, publish `entity.user.created`, and return the new `user_id`.
2. IF a second `create_user` request reuses an existing `login_name` or
   `primary_email` THEN the system SHALL reject the request with a
   `UserAlreadyExistsError` and SHALL NOT publish any event.
3. WHEN an administrator calls `deactivate_user(user_id)` THEN the system
   SHALL set `status = DEACTIVATED`, revoke all active sessions through
   `1-authentication`, publish `entity.user.deactivated`, and preserve the
   historical row for audit.
4. WHERE a deactivated user is re-enabled by an administrator the system
   SHALL publish `entity.user.updated` with a `reactivated` change marker and
   restore group memberships that were in effect at deactivation time.

### Requirement 2: Group Membership

**User Story:** As a project administrator, I want to manage named groups and
assign users to them, so that RBAC assignments scale with team structure.

**Acceptance Criteria (EARS):**

1. WHEN a group is created with a unique `group_name` THEN the system SHALL
   persist the `Group` row and publish `entity.group.created`.
2. IF a user is added to a group they already belong to THEN the system SHALL
   treat the operation as a no-op and return the existing membership record
   rather than raising.
3. WHILE a user is deactivated the system SHALL exclude them from group
   enumeration by default and SHALL require an explicit `include_inactive`
   flag to surface them.
4. WHEN a group is deleted the system SHALL publish
   `entity.group.deleted`, remove all memberships transactionally, and emit
   audit records identifying each affected user.

### Requirement 3: Directory Synchronization

**User Story:** As an operator, I want external directories (LDAP, SCIM,
custom HR) to drive account and group state, so that identity stays
consistent with enterprise systems of record.

**Acceptance Criteria (EARS):**

1. WHEN a `user_directory_source` implementation yields a user record that
   does not exist locally THEN the system SHALL create the user with
   `provisioning_source = <source-name>` and publish `entity.user.created`.
2. WHEN a `user_directory_source` yields an updated record for an existing
   user whose `provisioning_source` matches the source THEN the system SHALL
   apply the delta, publish `entity.user.updated` only if any field changed,
   and preserve fields the source does not own (e.g., `display_preferences`).
3. IF two `user_directory_source` extensions would own the same `login_name`
   THEN the system SHALL reject the second provisioning attempt with a
   `DirectoryCollisionError` identifying both sources.
4. WHERE an external directory explicitly marks a user as terminated the
   system SHALL deactivate the local account within one sync cycle and
   SHALL NOT permit local reactivation while the external record remains
   terminated.

### Requirement 4: Profile Data

**User Story:** As a user, I want to keep my display name, timezone, and
contact preferences current, so that Pychestrate addresses me correctly and
routes notifications to the right channels.

**Acceptance Criteria (EARS):**

1. WHEN a user updates their own profile via the REST API THEN the system
   SHALL validate each field against the `UserProfile` schema and reject any
   unknown keys with a `SemanticError`.
2. IF a profile update affects `primary_email` THEN the system SHALL mark
   the email as `unverified`, publish `entity.user.updated`, and require
   re-verification before the new address is used for notifications.
3. WHEN a user's `timezone` changes THEN the system SHALL update the user's
   audit trail view to render timestamps in the new timezone on subsequent
   requests.

### Requirement 5: Erasure by Anonymisation (data-protection requests)

**User Story:** As a platform administrator handling a data-protection request,
I want to remove a person's personal data from Pychestrate without breaking the
audit trail, so that the request can be met and history stays attributable.

**Acceptance Criteria (EARS):**

1. WHEN an administrator anonymises a `DEACTIVATED` user THEN the system SHALL,
   in one transaction, replace the user's `login_name`, `primary_email` and
   `display_name` with values derived from the `user_id` only, clear
   `external_id`, stamp `anonymised_at`, and publish `entity.user.anonymised`
   carrying only `{user_id, actor_user_id, anonymised_at}`.
2. WHEN a user is anonymised THEN the system SHALL delete the user's local
   credentials, password and email-verification tokens, MFA enrolments,
   sign-in sessions, API tokens, group memberships, direct role bindings and
   project memberships, and SHALL scrub the same personal fields from the
   legacy `user` mirror row.
3. IF the user is not `DEACTIVATED`, is the acting administrator, is already
   anonymised, or owns a project THEN the system SHALL refuse with a message
   that says what to do first (deactivate; ask another administrator;
   nothing to do; transfer or delete the project), and SHALL change nothing.
4. WHEN a user has been anonymised THEN the system SHALL keep the row and its
   `user_id` (audit records reference it), SHALL refuse to reactivate, edit or
   invite it, and SHALL show it as "Anonymised" wherever a user is listed or
   exported.
5. The administrator interface SHALL require the user's login name to be typed
   before it performs the action, and SHALL say that it cannot be undone.

### Requirement 5a: Deleting an Account (decided 2026-10-17)

**User Story:** As an administrator, I want to delete a user and have them gone,
so that the Users list holds the people who can use the system and nothing else,
without breaking the audit trail.

**Decision.** *Delete* is the administrator's name for the erasure of Requirement 5.
Nothing new is erased and no second mechanism is added: a user is not a free-standing
record, so removing the row would leave the audit log, "created by" and "triggered by"
fields and other records pointing at an id that names nothing. What changes is what the
administrator sees and what is hidden.

**Acceptance Criteria (EARS):**

1. The Users pages SHALL offer **Delete**, not "Anonymise", on a deactivated account (in the
   list row and on the account's page), with the confirmation and the rules of Requirement 5
   (login name typed, cannot be undone, deactivate first, not your own account, not a
   project's owner). Its confirmation SHALL say what is erased and that only an id with no
   name stays behind.
2. WHEN an account is deleted THEN the system SHALL do exactly what Requirement 5 says for
   anonymising: the login name and email become values derived from the id (so the person's
   login name and email address can be used again), and credentials, sessions, tokens,
   memberships and role bindings are removed.
3. A deleted account SHALL NOT appear in the Users list or its CSV export unless the
   administrator asks for deleted accounts (`?show_deleted=1` on the page; `include_deleted=true`
   on the REST list). It SHALL show as "Deleted" wherever it is listed or named, and its page,
   reached by its id (for example from an audit record), SHALL say that it was deleted and
   cannot be edited or reactivated.
4. The REST API SHALL accept `DELETE /api/v1/identity/users/{user_id}` with the same rules and
   the same effect as `POST /api/v1/identity/users/{user_id}/anonymise`, which stays (data-
   protection requests name "anonymise") and answers `anonymised: true` as before; `DELETE`
   answers the same body with `deleted: true` added (`status` stays `anonymised`: one account
   never reads as two statuses).
5. The event published SHALL stay `entity.user.anonymised` (consumers of it are unchanged); the
   audit record of a delete made from the Users pages SHALL read as the user having been
   anonymised, because that is what was done to the data.

**Not part of this decision.** Removing the identity row itself. It would need every plain-id
reference in the system (the audit log, about fifty "by" columns, the legacy mirror's foreign
keys) to be found, rewritten or refused first; the stub row costs nothing and keeps all of
them true.

## Property-Based Test Requirements

### Property 1: Create-Then-Read Round Trip

- **Invariant:** For any syntactically valid `CreateUserRequest`, immediately
  fetching the resulting `user_id` returns a `User` whose normalized fields
  equal the normalized request fields.
- **Generator:** A hypothesis composite strategy producing unicode display
  names (`min_size=1, max_size=128`), RFC-5321 local-part compliant emails
  under a bounded domain set, and IANA timezone strings drawn from
  `zoneinfo.available_timezones()`.
- **Assertion:** `read_user(user_id=created.user_id) == expected_user` under
  the feature's canonical normalization (NFC on display name, lowercase on
  email local-part's ASCII prefix only).
- **Sample size:** 1000 generated cases.

### Property 2: Directory Sync Idempotency

- **Invariant:** For any sequence of `sync_directory_source` calls replayed
  against the same source snapshot, the resulting `User` and
  `GroupMembership` row sets are identical and the number of
  `entity.user.updated` events equals the count of records whose payload
  actually changed.
- **Generator:** A snapshot strategy producing between 1 and 200 user
  records, each with stable `external_id`, then a permutation strategy
  replaying the snapshot 1–5 times in shuffled order.
- **Assertion:** Final DB state is permutation-invariant and event count
  equals the diff count between consecutive snapshots.
- **Sample size:** 1000 generated cases.

### Property 3: Deactivation Monotonicity

- **Invariant:** For any user, once `status` transitions through
  `DEACTIVATED` without an intervening explicit reactivation, the user's
  session count remains zero and group enumeration with default flags never
  surfaces them.
- **Generator:** Random interleavings of `{create, add_to_group, login,
  deactivate}` events for a fixed user across 1–50 steps.
- **Assertion:** After every step, the invariant holds for every step in
  which the most recent administrative action was `deactivate`.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** `read_user` and `list_users` with up to 10,000
  rows SHALL complete in < 25 ms p95 on a warm connection pool;
  `create_user` SHALL complete in < 40 ms p95 including event publish.
- **NFR-2 (Security):** All write endpoints SHALL require
  `system:users.write` via `1-rbac`; profile reads of *other* users are
  gated on `system:users.read`; email addresses SHALL be treated as PII and
  SHALL never appear in structured log fields outside the `audit_log`
  sink.
- **NFR-3 (Observability):** The feature SHALL emit
  `pychestrate_users_created_total`,
  `pychestrate_users_deactivated_total`,
  `pychestrate_groups_membership_changes_total`,
  `pychestrate_users_directory_sync_duration_seconds` (histogram, per
  source name), and log events `user.created`, `user.updated`,
  `user.deactivated`, `group.created`, `group.membership.changed`.
- **NFR-4 (Reliability):** Directory sync failures SHALL NOT block
  unrelated write traffic; a failed sync cycle SHALL leave the last-good
  snapshot intact, emit `pychestrate_users_directory_sync_failures_total`,
  and retry on the next scheduled cycle.

## Out of Scope

- Password storage and credential verification — owned by
  `1-authentication`.
- Permission evaluation — owned by `1-rbac`.
- Project membership semantics — owned by `2-projects`; this feature only
  supplies the user and group primitives the project layer references.
- MFA enrollment metadata — owned by `1-authentication` through the
  `MFAMethodExtension` surface.

## Dependencies

- **Depends on:** `0-persistence`, `0-message-bus`, `E-extension-host`,
  `E-factory-protocols`.
- **Depended on by:** `1-authentication`, `1-rbac`, `1-audit-log`,
  `2-projects`, `2-notification-hub`.
- **Extension points exposed:** `factory: user_directory_source` —
  LDAP / SCIM / custom HR sync; reference implementation
  `LocalDatabaseUserDirectorySource` ships in-tree. See
  implementation-plan.md Layer 1.
