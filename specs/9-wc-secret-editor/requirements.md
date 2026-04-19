# 9-wc-secret-editor — Requirements

## Introduction

`9-wc-secret-editor` is the ACL-aware Custom Element for managing secret
metadata and triggering server-side mutations in `1-secrets-vault`. It
**never** fetches or renders plaintext — the server never returns plaintext to
the browser for any secret, for any reason. The element edits ACL entries,
rotation schedules, labels, descriptions, tags, expiry policy, and triggers
`set`, `rotate`, and `revoke` operations that are executed on the server
behind audit. Ships in **Phase 10** alongside `9-admin-ui`. Sits between
`1-secrets-vault` / `1-audit-log` / `1-rbac` and the admin page that hosts
it. Authoritative secret state (ciphertext, plaintext, rotation state) lives
in the configured `secrets_backend`; this element is a metadata editor only.

## Requirements

### Requirement 1: Render Metadata, Never Plaintext

**User Story:** As a secrets administrator, I want to see the metadata of a
secret (label, description, owners, ACL, rotation, last-rotated, expiring-at)
without ever seeing its plaintext, so that plaintext stays in the vault and
cannot leak through the UI.

**Acceptance Criteria (EARS):**

1. WHEN the element loads metadata for `secret-id` THEN it SHALL call `GET /api/v1/secrets/{secret_id}/metadata` which SHALL return a document WITHOUT a plaintext field.
2. IF the server response contains any field named `plaintext`, `value`, or `decrypted_value` THEN the element SHALL refuse to render AND emit `pyc-secret-editor-policy-violation` with `{reason: "plaintext_leak_detected"}`.
3. WHEN the user edits any metadata field THEN the element SHALL buffer changes locally AND SHALL NOT transmit anything to the server until the user explicitly submits the form.
4. WHILE no changes are buffered THEN the element SHALL render a read-only view gated by `secrets.metadata.view`; attempting to edit without `secrets.metadata.edit` SHALL render edit affordances as disabled with an `aria-disabled="true"` attribute.

### Requirement 2: ACL Management with Preview

**User Story:** As a secrets administrator, I want to manage per-secret ACL
entries (principals and their rights) and preview the effective access
before saving, so that I can avoid accidental over-privilege.

**Acceptance Criteria (EARS):**

1. WHEN the user adds or removes an ACL entry THEN the element SHALL buffer the change AND SHALL issue `POST /api/v1/secrets/{secret_id}/acl/preview` with the buffered change set to compute `EffectiveAccess`.
2. IF preview reports a principal transition that grants `read:secret` to a new group THEN the element SHALL require an explicit confirm dialog before save SHALL be enabled.
3. WHEN the user submits the change set THEN the element SHALL call `PATCH /api/v1/secrets/{secret_id}` carrying only the delta; on success it SHALL refresh metadata and emit `pyc-secret-editor-saved` with `{secretId, revision}`.
4. WHERE the caller lacks `secrets.acl.edit` THEN ACL editing controls SHALL be hidden; attempting to submit SHALL be a no-op.

### Requirement 3: Rotate and Revoke Without Plaintext

**User Story:** As a secrets administrator, I want to trigger rotation and
revocation from the UI, so that I do not have to drop to the CLI — while
still never seeing plaintext.

**Acceptance Criteria (EARS):**

1. WHEN the user clicks `rotate` THEN the element SHALL call `POST /api/v1/secrets/{secret_id}:rotate` with a reason string AND SHALL show a pending-rotation affordance until the operation completes.
2. IF the configured `secrets_backend` does not support rotation THEN the element SHALL disable the rotate control AND expose `data-pyc-secret-editor-rotation="unsupported"`.
3. WHEN the user clicks `revoke` AND the caller has `secrets.revoke` THEN the element SHALL require typed confirmation of the secret's label AND then call `POST /api/v1/secrets/{secret_id}:revoke` with a reason.
4. WHEN a rotate or revoke succeeds THEN the element SHALL emit `pyc-secret-editor-mutation` with `{secretId, kind: "rotate"|"revoke", actorId, at, reason}` AND SHALL refresh metadata.

### Requirement 4: Audit and Reason-String Discipline

**User Story:** As an auditor, I want every mutation to be accompanied by a
reason string and have the UI surface audit links for each secret, so that
changes are traceable.

**Acceptance Criteria (EARS):**

1. WHEN the user initiates a mutation THEN the element SHALL require a non-empty `reason` (length 4..512) AND SHALL block submission until one is provided.
2. WHEN metadata is loaded THEN the element SHALL render a link to `/api/v1/audit?entity=secret&entity_id=<id>` scoped to this secret (displayed as a count + "view audit log" slot).
3. WHILE a mutation is in-flight THEN the element SHALL disable all mutation controls to prevent duplicate submits.
4. IF a mutation fails THEN the element SHALL surface the server's error code and safe message via `slot="mutation-error"` AND SHALL emit `pyc-secret-editor-mutation-failed` with `{kind, status, error_code}`.

## Property-Based Test Requirements

### Property 1: Plaintext Never Leaves the Server

- **Invariant:** For any mutation payload submitted by the element (PATCH / rotate / revoke), the request body contains no field named `plaintext`, `value`, `decrypted_value`, `secret_value`, `cleartext`.
- **Generator:** Random edits across the editable metadata surface (labels, descriptions, ACL edits, tags, rotation schedules, reason strings).
- **Assertion:** For each generated submission, recursive scan of the request body (JSON) yields no forbidden field name (case-insensitive).
- **Sample size:** 1000 generated cases

### Property 2: Buffered Edits Are Reversible

- **Invariant:** For any sequence of edits followed by a `reset()`, the form state equals the last-loaded metadata snapshot.
- **Generator:** Random sequences of edit operations.
- **Assertion:** After `reset()`, the form state equals the baseline snapshot.
- **Sample size:** 1000 generated cases

### Property 3: ACL Preview Is Consistent With Submission

- **Invariant:** For any buffered change set, the `EffectiveAccess` returned by the preview call equals the effective access the server reports after the same change set is submitted and re-read (functional equivalence, given identical server state).
- **Generator:** Random buffered change sets drawn from a principal/right catalog with a stub server.
- **Assertion:** `previewResponse.effective == postSubmitSnapshot.effective`.
- **Sample size:** 1000 generated cases

## Non-Functional Requirements

- **NFR-1 (Performance):** TTI p95 < 250 ms with metadata cached. Preview p95 < 400 ms. Submit p95 < 800 ms. Rotate / revoke are async; UI feedback within 200 ms of user action.
- **NFR-2 (Security):** Same-origin REST; session cookies + CSRF. The element hard-refuses any server response carrying plaintext and emits a policy-violation event. RBAC gates are enforced client-side for affordance visibility AND server-side for effect. Reason strings are required and audited. No local storage of metadata — session-only.
- **NFR-3 (Observability):** Client metrics beaconed: `pychestrate_ui_secret_editor_tti_seconds` (histogram), `pychestrate_ui_secret_editor_save_duration_seconds` (histogram), `pychestrate_ui_secret_editor_mutation_total{kind, outcome}` (counter), `pychestrate_ui_secret_editor_policy_violation_total{reason}` (counter). Log events `pychestrate.ui.secret_editor.opened`, `pychestrate.ui.secret_editor.saved`, `pychestrate.ui.secret_editor.rotated`, `pychestrate.ui.secret_editor.revoked`, `pychestrate.ui.secret_editor.policy_violation`.
- **NFR-4 (Reliability):** If the ACL preview endpoint is down, save is blocked with a banner — the element will not save without a successful preview. If metadata refresh fails after a successful save, the element retains the save confirmation but marks the view as stale.

## Out of Scope

- Reading, displaying, or logging plaintext (forbidden by design).
- Secret creation flows (handled by a sibling `9-wc-secret-create` dialog in `9-admin-ui`).
- Cross-backend migration of secrets (operator tooling only).
- Secret usage telemetry correlation (see `1-audit-log` and `7-metrics-ingest`).

## Dependencies

- **Depends on:** `9-ui-design-tokens`, `1-secrets-vault`, `1-rbac`, `1-audit-log`, `8-rest-api-v1`, `1-authentication`.
- **Depended on by:** `9-admin-ui`.
- **Extension points exposed:** None; `secrets_backend` extensions (`1-secrets-vault`) are transparently honored via server-side capabilities reported in metadata.
