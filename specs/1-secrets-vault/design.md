# 1-secrets-vault — Design

## Architecture

`1-secrets-vault` lives under
`source/site/automojo/pychestrate/webservice/secrets/`. It exposes a
narrow API (`put_secret`, `read_secret`, `rotate_secret`,
`delete_secret`) that every other feature uses. Behavior is controlled
by a caller-supplied `SecretsAspects` object per AGENTS.md (not by
decorators). Storage is plugged via the `secrets_backend`
`FactoryProtocolBase`; the in-tree `LocalEncryptedSecretsBackend`
implements AES-GCM ciphertext storage in `0-persistence`. A
`secrets_router` maps each `secret_ref` to a backend by matching the
configured `namespace_pattern`s and picking the lower-precedence
registration per `E-extension-precedence`. Every access produces an
`entity.secret.*` event on `0-message-bus` which `1-audit-log`
consumes — the audit path is load-bearing and a failed audit write
rolls back the secret operation. This feature ships in **Phase 1 —
Identity & Projects**.

## Data Model

`secrets` — metadata per `secret_ref`:

- `secret_ref: str` — PK, format `project:<id>:<name>` or
  `system:<name>`.
- `current_version_id: UUID` — FK into `secret_versions`.
- `backend_name: str` — which `secrets_backend` owns the bytes.
- `owner_user_id: UUID`, `owner_project_id: Optional[UUID]`.
- `created_at: datetime`, `updated_at: datetime`.

`secret_versions` — rotation lineage:

- `version_id: UUID` — PK.
- `secret_ref: str` — FK.
- `version_number: int` — monotonically increasing per `secret_ref`.
- `state: SecretVersionState` — `{ACTIVE, SUPERSEDED, EXPIRED}`.
- `ciphertext_ref: Optional[str]` — opaque id returned by backend;
  NULL for delegated backends that hold bytes externally.
- `wrapped_dek: Optional[bytes]` — present only for local backend.
- `kek_id: Optional[str]`.
- `grace_expires_at: Optional[datetime]`.
- `created_at: datetime`, `created_by: UUID`.

`secret_acls` — per-secret ACL rules:

- `acl_id: UUID`, `secret_ref: str`, `effect: PermissionEffect`,
  `principal_kind: PrincipalKind`, `principal_id: UUID`,
  `actions: tuple[SecretAction, ...]` where `SecretAction ∈
  {READ, WRITE, ROTATE, DELETE}`, `created_at: datetime`,
  `created_by: UUID`.

`secret_outbox` — async write buffer for
`aspects.sync = False`:

- `outbox_id: UUID`, `operation: str`, `payload: bytes`,
  `enqueued_at: datetime`, `retry_count: int`, `next_attempt_at:
  datetime`, `status: OutboxStatus`.

`secrets_backend_registrations` — runtime view of registered backends
with `namespace_pattern`, `precedence`, `capabilities`.

## Interfaces

### Public API

REST routes:

- `POST /api/v1/secrets` — create with `{secret_ref, plaintext, acl}`;
  supports `sync` query parameter for `aspects.sync`.
- `GET /api/v1/secrets/{secret_ref}` — read metadata only (never
  returns plaintext over REST — use the CLI or admin flows).
- `POST /api/v1/secrets/{secret_ref}/rotate` — rotate.
- `DELETE /api/v1/secrets/{secret_ref}` — force-expire + delete.
- `GET /api/v1/secrets` — list (subject to `system:secrets.read`).

### Internal API

Module `automojo.pychestrate.webservice.secrets.secrets_service`:

```python
@dataclass(frozen=True)
class SecretsAspects:
    """
        Caller-supplied behavior knobs — AGENTS.md "Aspects" pattern.

        :param sync: If True, wait for durable backend confirmation before returning.
        :param timeout_seconds: Per-call deadline for backend operations.
        :param retry_budget: Number of attempts for transient backend errors.
        :param include_metadata: Return version + rotation metadata alongside bytes.
        :param log_verbosity: NORMAL | DEBUG — never exposes plaintext at any level.
    """
    sync: bool
    timeout_seconds: float
    retry_budget: int
    include_metadata: bool
    log_verbosity: LogVerbosity


def build_default_aspects() -> SecretsAspects:
    """
        Construct the default aspects for routine callers.

        Note: per AGENTS.md we never use mutable defaults; callers
        that want defaults explicitly invoke this function.
    """
    rtnval = SecretsAspects(
        sync=True,
        timeout_seconds=5.0,
        retry_budget=3,
        include_metadata=False,
        log_verbosity=LogVerbosity.NORMAL
    )
    return rtnval


def put_secret(
        *,
        principal: AuthPrincipal,
        secret_ref: str,
        plaintext: SecretBytes,
        acl: SecretACL,
        aspects: SecretsAspects
    ) -> SecretVersion:
    """
        Store a new secret or overwrite as a first write.

        :raises: SecretAlreadyExistsError, SemanticError, SecretAccessDeniedError
    """
    ...


def read_secret(
        *,
        principal: AuthPrincipal,
        secret_ref: str,
        aspects: SecretsAspects
    ) -> SecretRead:
    """
        Resolve a `secret_ref` to plaintext with ACL enforcement.

        :returns: `SecretRead` wrapping `SecretBytes` plaintext and optional metadata.
        :raises: SecretAccessDeniedError, SecretNotFoundError,
                 SecretReadTimeoutError, SecretBackendUnavailableError
    """
    ...


def rotate_secret(
        *,
        principal: AuthPrincipal,
        secret_ref: str,
        new_plaintext: SecretBytes,
        grace_seconds: int,
        aspects: SecretsAspects
    ) -> SecretVersion:
    """
        Rotate a secret, keeping the prior version readable for the grace window.

        :raises: SecretNotFoundError, SemanticError, SecretAccessDeniedError
    """
    ...


def force_expire_secret(
        *,
        principal: AuthPrincipal,
        secret_ref: str,
        aspects: SecretsAspects
    ) -> None:
    """
        Immediately expire every version of a secret.
    """
    rtnval = None
    return rtnval
```

Module `automojo.pychestrate.webservice.secrets.secrets_router`:

```python
def resolve_backend(*, secret_ref: str) -> SecretsBackendProtocol:
    """
        Select the registered `secrets_backend` for the given ref by
        matching `namespace_pattern` and picking the lowest PRECEDENCE.

        :raises: ConfigurationError if no backend matches.
    """
    ...
```

### Extension Surface

Factory protocol `secrets_backend` declared in
`automojo.pychestrate.webservice.secrets.factories.secrets_backend`:

```python
class SecretsBackendProtocol(FactoryProtocolBase):
    factory_protocol_name: str = "secrets_backend"
    protocol_schema_version: int = 1

    @classmethod
    def namespace_pattern(cls) -> str:
        """Glob pattern matched against `secret_ref` to claim a namespace."""
        ...

    @classmethod
    def capabilities(cls) -> BackendCapabilities:
        """Declared caps: supports_native_rotation, supports_audit_tap, ..."""
        ...

    @classmethod
    def write_secret(cls, *, secret_ref: str, plaintext: SecretBytes,
                     aspects: SecretsAspects) -> BackendWriteResult:
        ...

    @classmethod
    def read_secret(cls, *, secret_ref: str, version_id: Optional[UUID],
                    aspects: SecretsAspects) -> BackendReadResult:
        ...

    @classmethod
    def rotate_secret(cls, *, secret_ref: str, new_plaintext: SecretBytes,
                      grace_seconds: int, aspects: SecretsAspects) -> BackendWriteResult:
        ...

    @classmethod
    def delete_secret(cls, *, secret_ref: str, aspects: SecretsAspects) -> None:
        ...
```

Reference implementation: `LocalEncryptedSecretsBackend` at
`PRECEDENCE = 1000`, claiming `namespace_pattern = "*"` — operators
pin higher-priority external backends for specific namespaces. In-tree
examples shipped under `factories/` for guidance:
`HashicorpVaultSecretsBackend` skeleton, `AwsSecretsManagerBackend`
skeleton.

### Events Emitted

- `entity.secret.created` — `{secret_ref, version_id, backend_name, actor_user_id, created_at}`
- `entity.secret.rotated` — `{secret_ref, new_version_id, previous_version_id, backend_name, actor_user_id, rotated_at}`
- `entity.secret.expired` — `{secret_ref, version_id, reason, expired_at}`
- `entity.secret.force_expired` — `{secret_ref, actor_user_id, expired_at}`
- `entity.secret.accessed` — `{secret_ref, version_id, backend_name, principal_id, accessed_at}`
- `entity.secret.access_denied` — `{secret_ref, principal_id, reason, at}`
- `entity.secret.acl.changed` — `{secret_ref, acl_id, change, actor_user_id, at}`

### Events Consumed

- `entity.user.deactivated` — removes personal ACL entries for the
  deactivated user.
- `entity.project.archived` — archives project-scoped secrets (marks
  them read-only and ACL-restricted).
- `entity.audit.sink.unhealthy` — trips the write-blocked flag so new
  writes fail closed (per NFR-4).

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/secrets/
    __init__.py
    secrets_service.py
    secrets_router.py
    secrets_aspects.py              # SecretsAspects dataclass + builder
    secret_bytes.py                 # SecretBytes wrapper (zeroizing, redacted repr)
    acl.py                          # per-secret ACL evaluation
    rotation.py                     # grace window, scheduled expiry
    outbox.py                       # async write outbox
    kek_loader.py                   # KEK bootstrap at startup
    factories/
        secrets_backend.py
        local_backend.py            # LocalEncryptedSecretsBackend reference impl
        vault_backend.py            # HashicorpVaultSecretsBackend (skeleton)
        aws_sm_backend.py           # AwsSecretsManagerBackend (skeleton)
    models.py
    restapi/
        v1/
            secrets_controller.py
    events.py
    exceptions.py
```

## Key Flows

**Put Secret (sync):**

1. Caller constructs `SecretsAspects(sync=True, timeout_seconds=5,
   retry_budget=3, include_metadata=False, log_verbosity=NORMAL)`.
2. `secrets_service.put_secret` validates `secret_ref`, resolves
   backend via `secrets_router`, checks `system:secrets.admin` or
   project-scoped `project:<id>:secrets.write` via `1-rbac`.
3. For `LocalEncryptedSecretsBackend`: generates a fresh DEK,
   AES-GCM-encrypts the plaintext, wraps the DEK with the loaded
   KEK, inserts `secrets` + `secret_versions` rows plus an outbox
   event for `entity.secret.created` in a single transaction.
4. Commit triggers bus publish; `1-audit-log` writes an
   `audit.secret.created` row; the call returns the `SecretVersion`.

**Read Secret:**

1. Caller invokes `secrets_service.read_secret(principal,
   secret_ref, aspects)`.
2. ACL evaluation runs against per-secret ACL (combined with
   `1-rbac`'s `project:<id>:secrets.read` or
   `system:secrets.read`).
3. Backend returns ciphertext + wrapped DEK; service unwraps and
   decrypts into a `SecretBytes` wrapper.
4. `entity.secret.accessed` stages to outbox; audit row writes
   transactionally — if the audit path is unhealthy, the read fails
   with `AuditUnavailableError` (NFR-4).
5. Plaintext is returned inside `SecretBytes`; bytes are zeroized
   when the wrapper is dropped.

**Rotate:**

1. `secrets_service.rotate_secret` inserts a new `ACTIVE` version,
   marks the previous `SUPERSEDED` with
   `grace_expires_at = now + grace_seconds`, publishes
   `entity.secret.rotated`.
2. A scheduled sweeper (owned by `rotation.py`) runs every 60
   seconds, flips superseded versions to `EXPIRED` when their grace
   expires, and schedules crypto-erasure.

**Delegated Backend (External Vault):**

1. Router picks `HashicorpVaultSecretsBackend`.
2. Backend calls `aspects.retry_budget` with backoff (0.25s, 1s, 4s)
   against Vault's API.
3. On `SecretBackendTransientError`, the service catches + reclassifies
   with context and either retries (if budget remaining) or raises
   `SecretBackendUnavailableError`.

## Error Handling

Failure modes:

- `SecretAlreadyExistsError` — HTTP 409 on duplicate create.
- `SecretNotFoundError` — HTTP 404 on read/rotate/delete.
- `SecretAccessDeniedError` — HTTP 403 with no detail beyond the
  denied `secret_ref`.
- `SecretReadTimeoutError` — HTTP 504.
- `SecretBackendUnavailableError` — HTTP 503 with backend name.
- `SecretVersionExpiredError` — HTTP 410 when a reader references a
  version past its grace expiry.
- `AuditUnavailableError` — HTTP 503 when audit sink is unhealthy;
  writes fail closed (NFR-4).
- `SemanticError` — malformed `secret_ref` or illegal aspect values;
  NEVER caught.
- `ConfigurationError` — raised at startup if the KEK cannot be
  loaded or no backend matches `*`.

Multi-line error messages use the AGENTS.md pattern:

```python
err_msg_lines = ["Secret backend unavailable after retries."]
err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
err_msg_lines.append("BACKEND: {}".format(backend_name))
err_msg_lines.append("ATTEMPTS: {}".format(attempts))
err_msg_lines.append("LAST_CAUSE: {}".format(last_cause))
err_msg = os.linesep.join(err_msg_lines)
raise SecretBackendUnavailableError(err_msg) from last_cause
```

Plaintext never appears in any error message, trace, or log —
`SecretBytes` is opaque to `repr`.

## Security Considerations

- Plaintext lives inside `SecretBytes` from decryption until consumer
  hand-off; `SecretBytes.__repr__` is the literal `"<redacted>"`.
- AES-GCM with a random 96-bit nonce per encrypt; DEK rotation on
  every write.
- KEK loaded at startup from an operator-owned key source (file,
  KMS, HSM shim); the service does not generate the KEK.
- RBAC permissions: `system:secrets.admin`,
  `system:secrets.read`, `project:<id>:secrets.read`,
  `project:<id>:secrets.write`, `project:<id>:secrets.rotate`.
- Writes and reads audit unconditionally — there is no bypass
  path. A failed audit rolls back the secret operation.
- Extensions loading `secrets_backend` must declare the
  `read:secrets` and/or `write:secrets` capability when
  `E-extension-sandbox` arrives (Phase 8); in Phase 1 the hooks are
  already in the registry for forward compatibility.
- Rate limiting on `read_secret` per principal (default 100 rps) to
  blunt exfiltration.

## Observability

Metrics:

- `pychestrate_secrets_reads_total{backend,outcome}`
- `pychestrate_secrets_writes_total{backend,outcome}`
- `pychestrate_secrets_read_duration_seconds{backend}` (histogram)
- `pychestrate_secrets_read_timeouts_total{backend}`
- `pychestrate_secrets_rotations_total{backend}`
- `pychestrate_secrets_backend_errors_total{backend,kind}`
- `pychestrate_secrets_outbox_depth` (gauge)
- `pychestrate_secrets_outbox_retries_total`

Log events: `secret.read.allowed`, `secret.read.denied`,
`secret.write.accepted`, `secret.rotated`, `secret.expired`,
`secret.force_expired`, `secret.backend.failed`,
`secret.outbox.retried`. Every log record includes `secret_ref` and
never `secret.value`.

Trace spans: `secrets.put`, `secrets.read`, `secrets.rotate`,
`secrets.backend.call`, `secrets.outbox.flush`.

## Open Questions

- Do we expose ciphertext export for backup/DR, or rely on
  application-level re-wrap? Initial decision: export ciphertext +
  wrapped DEK, never plaintext; revisit in `10-backup-dr`.
- How do we handle pod-scoped ephemeral secrets that outlive no
  parent project? Tentative: allow `pod:<id>:<name>` namespace added
  by `3-pod-scoped-config` in Phase 2.
- Should rotations fan out automatically to active sessions/caches
  in other features? For Phase 1 we publish the rotation event and
  leave subscribers to invalidate; a push-subscribe API can come
  later.
