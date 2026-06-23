# 9-wc-secret-editor — Design

## Architecture

`9-wc-secret-editor` is a Custom Element that edits secret **metadata** and
triggers server-side mutations. Its defining non-goal is that plaintext
NEVER reaches the browser. The element instantiates with a `secret-id`,
fetches a metadata document that contains zero sensitive fields, and presents
forms for editable metadata (label, description, tags, rotation schedule,
expiry, ACL). A buffered-edits model keeps the user in control: nothing is
sent to the server until they explicitly save, and the UI refuses to render
anything that looks like plaintext even if a misbehaving server sends it.
Ships in **Phase 10** and is hosted by `9-admin-ui`. The
`secrets_backend`-specific capabilities (rotation-support, versioning) are
reported in metadata so the UI can disable what the backend cannot do.

## Data Model

No persistent entities. Runtime state:

- `SecretMetadata` — `{secretId: string, label: string, description: string, tags: string[], owners: Principal[], acl: AclEntry[], rotation: RotationPolicy, expiresAt: string | null, createdAt: string, updatedAt: string, revision: number, backendCapabilities: {rotate: boolean, versioning: boolean, preview: boolean}}`.
- `AclEntry` — `{principalKind: "user"|"group"|"service", principalId: string, rights: string[]}`.
- `RotationPolicy` — `{kind: "disabled"|"interval"|"manual", intervalDays: number | null, lastRotatedAt: string | null}`.
- `EditBuffer` — `{base: SecretMetadata, modified: Partial<SecretMetadata>, reason: string, dirty: boolean}`.
- `EffectiveAccess` — `{principalId: string, rights: string[], viaRoles: string[]}[]`.

## Interfaces

### Public API

**Tag name:** `<pyc-secret-editor>`

**Observed attributes:**

- `secret-id` (string; UUID) — the secret to edit.
- `read-only` (boolean attribute) — force read-only mode regardless of RBAC.
- `require-confirm-label` (boolean attribute) — require typed label confirmation for revoke (default on).
- `aria-label` (string) — accessibility label override.

**Properties (JS):**

- `secretId: string`
- `metadata: SecretMetadata | null`
- `dirty: boolean`
- `reason: string`
- `applyEdit(edit: Partial<SecretMetadata>): void`
- `reset(): void`
- `save(): Promise<SaveResult>`
- `rotate(reason: string): Promise<MutationResult>`
- `revoke(reason: string, confirmLabel: string): Promise<MutationResult>`
- `reload(): Promise<void>`

**Events (bubbling, composed):**

- `pyc-secret-editor-loaded` — `{secretId, revision, backendCapabilities}`.
- `pyc-secret-editor-edited` — `{field, isDirty}`.
- `pyc-secret-editor-saved` — `{secretId, revision}`.
- `pyc-secret-editor-mutation` — `{secretId, kind, actorId, at, reason}`.
- `pyc-secret-editor-mutation-failed` — `{kind, status, error_code, message}`.
- `pyc-secret-editor-policy-violation` — `{reason}` (hard fault; render disabled).
- `pyc-secret-editor-acl-preview` — `{effectiveAccess}`.

**Slots:**

- `slot="header"` — consumer-supplied header (e.g., breadcrumb).
- `slot="audit-link"` — audit-log link placeholder; element populates with the audit URL on load.
- `slot="mutation-error"` — error presentation on failure.
- `slot="danger-zone"` — consumer-supplied danger-zone content for revoke (the element renders confirmation UI inside).

**CSS custom properties respected:**

- `--pyc-secret-editor-bg` → `var(--pyc-color-surface)`
- `--pyc-secret-editor-fg` → `var(--pyc-color-on-surface)`
- `--pyc-secret-editor-input-bg` → `var(--pyc-color-input-bg)`
- `--pyc-secret-editor-input-fg` → `var(--pyc-color-input-fg)`
- `--pyc-secret-editor-input-border` → `var(--pyc-color-border-strong)`
- `--pyc-secret-editor-danger-bg` → `var(--pyc-color-danger-subtle)`
- `--pyc-secret-editor-danger-fg` → `var(--pyc-color-on-danger-subtle)`
- `--pyc-secret-editor-button-primary-bg`, `--pyc-secret-editor-button-primary-fg`
- `--pyc-secret-editor-focus-ring` → `var(--pyc-focus-ring)`
- `--pyc-secret-editor-font-family` → `var(--pyc-font-family-ui)`

**A11y requirements:**

- Root: `role="form"` with `aria-label="Secret editor"` (overridable).
- Each field has an associated `<label for="...">`.
- Mutation buttons have `aria-describedby` pointing at the reason field so screen readers announce required-reason context.
- Keyboard: Tab traverses fields in visual order, `Ctrl/Cmd+Enter` submits when valid, `Esc` reverts current field edit, `Ctrl/Cmd+R` rotates (behind confirmation), `Ctrl/Cmd+Shift+Backspace` revokes (behind confirmation).
- Visually-hidden live region announces `saved`, `rotated`, `revoked`, and any policy violation.

Server REST surfaces consumed (owned by `1-secrets-vault`):

- `GET /api/v1/secrets/{secret_id}/metadata` — metadata only; MUST never include plaintext.
- `PATCH /api/v1/secrets/{secret_id}` — metadata delta.
- `POST /api/v1/secrets/{secret_id}/acl/preview` — preview effective access.
- `POST /api/v1/secrets/{secret_id}:rotate` — trigger rotation.
- `POST /api/v1/secrets/{secret_id}:revoke` — trigger revocation.
- `GET /api/v1/audit?entity=secret&entity_id=<id>&limit=1` — audit count.

### Internal API

```typescript
class PlaintextGuard {
    scanResponse(payload: unknown): PlaintextScanResult
}

class SecretEditBuffer {
    load(base: SecretMetadata): void
    apply(edit: Partial<SecretMetadata>): void
    reset(): void
    delta(): Partial<SecretMetadata>
    isDirty(): boolean
}

class SecretTransport {
    fetchMetadata(secretId: string): Promise<SecretMetadata>
    previewAcl(secretId: string, delta: Partial<SecretMetadata>): Promise<EffectiveAccess[]>
    patch(secretId: string, delta: Partial<SecretMetadata>, reason: string): Promise<SecretMetadata>
    rotate(secretId: string, reason: string): Promise<MutationResult>
    revoke(secretId: string, reason: string): Promise<MutationResult>
}
```

### Extension Surface

None in this element. The server-side `secrets_backend` factory determines
which operations are supported; the metadata document reports capabilities so
the UI can disable unsupported controls.

### Events Emitted

DOM CustomEvents.

### Events Consumed

None.

## Component Breakdown

All paths rooted at `source/site/ccai/pychestrate/webservice/webinterface/components/pyc-secret-editor/`:

- `pyc-secret-editor.ts` — Custom Element.
- `plaintext-guard.ts` — hard scan against forbidden field names.
- `edit-buffer.ts` — buffered edits with reset.
- `transport/secret-transport.ts` — REST client.
- `acl-editor.ts` — ACL row editor and preview integration.
- `danger-zone.ts` — rotate / revoke flows.
- `keybindings.ts`.
- `styles.css` — multi-line CSS referencing `--pyc-secret-editor-*` tokens.
- `tests/`.

Bundle emitted at `/ui/components/pyc-secret-editor/pyc-secret-editor.js`.

## Key Flows

### Flow 1 — Load and edit metadata

1. Element reads `secret-id`.
2. Transport fetches `/metadata`; `PlaintextGuard.scanResponse` walks the JSON; any match halts rendering and emits `pyc-secret-editor-policy-violation`.
3. `EditBuffer.load` establishes the baseline; form fields render.
4. User edits a field; `pyc-secret-editor-edited` fires; Save button enables when `dirty && reason.length >= 4`.

### Flow 2 — ACL change with preview

1. User adds an ACL entry and types a reason.
2. Element debounces 300 ms; calls `/acl/preview` with the delta.
3. Response rendered in the preview panel; if new `read:secret` grants are detected, confirmation checkbox appears.
4. User submits; Save issues `PATCH` with delta + reason; on success metadata refreshes.

### Flow 3 — Rotate / revoke

1. User opens the danger zone; types the secret's label to match (if `require-confirm-label`).
2. For rotate: element calls `/rotate` with reason; on completion `pyc-secret-editor-mutation` fires.
3. For revoke: element calls `/revoke` with reason; UI becomes read-only with a "revoked" banner.

## Error Handling

- `PlaintextGuard` detection → render disabled; emit `pyc-secret-editor-policy-violation`; log metric; do NOT retry.
- 403 Forbidden → render read-only state with "missing permissions" banner; no retry.
- 409 Conflict (stale `revision`) → reload metadata and surface a merge banner; discard local delta only on explicit user confirmation.
- Preview failure → Save disabled; banner "ACL preview unavailable".
- Rotate/revoke failure → `slot="mutation-error"` populated with server's safe message; `pyc-secret-editor-mutation-failed` emitted; form stays in prior state.
- Multiline client-side errors are surfaced using `\n`-joined strings (the element's string-formatting helper is the JS analog of `os.linesep.join`).

## Security Considerations

- Plaintext is never accepted from the server. The element rejects any response with forbidden field names.
- No metadata or edits are persisted to `localStorage` / `sessionStorage` — state dies with the element.
- Reason strings are required, length-bounded, and HTML-escaped before rendering (when echoed back after save).
- Mutation requests carry the CSRF token and are idempotency-keyed with a client-generated UUID to protect against duplicates.
- Revoke requires typed-label confirmation by default; disabling it requires attribute opt-out AND is logged.
- The element never renders any raw URL derived from the metadata without passing it through an allowlist (audit link scheme/host locked to the current origin).

## Observability

Client metrics beaconed:

- `pychestrate_ui_secret_editor_tti_seconds` — histogram.
- `pychestrate_ui_secret_editor_save_duration_seconds` — histogram.
- `pychestrate_ui_secret_editor_mutation_total{kind, outcome}` — counter.
- `pychestrate_ui_secret_editor_policy_violation_total{reason}` — counter.
- `pychestrate_ui_secret_editor_preview_duration_seconds` — histogram.

Log events: `pychestrate.ui.secret_editor.opened`, `pychestrate.ui.secret_editor.saved`, `pychestrate.ui.secret_editor.rotated`, `pychestrate.ui.secret_editor.revoked`, `pychestrate.ui.secret_editor.policy_violation`.

Trace spans (server-side at ingestion): `pychestrate.ui.secret_editor.metric_ingest`.

## Open Questions

- Should the editor fetch and preview the audit log inline (last 10 events) vs deep-linking only? Timebox: Phase 10 midpoint.
- Typed-label confirmation UX for revoke — does typing the label match exactly (case-sensitive) or fuzzy match? Timebox: Phase 10 kickoff.
- Multi-tenant contexts: should the element scope the audit link by project/tenant? Timebox: Phase 10 exit.
