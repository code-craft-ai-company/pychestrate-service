# E-extension-config — Design

## Architecture

E-extension-config is an accessor-façade layer over
`2-global-variables` and `1-secrets-vault`. Each loaded extension
receives a `ExtensionConfigScope` instance bound to its extension name
and manifest. The scope prefixes every lookup with `ext.<name>.`,
enforces capability checks against the manifest for secret reads, and
refuses cross-scope lookups with `SemanticError`. The scope is handed
to each extension during `on_load` as a named parameter; an extension
that does not accept it simply never gets configuration access.

## Data Model

In-memory (no SQL):

- `ExtensionConfigScope` — thin adapter holding:
  - `ext_name: str`
  - `manifest_capabilities: FrozenSet[str]`
  - `variable_api: "GlobalVariableAPI"`   (from `2-global-variables`)
  - `secrets_api: "SecretsVaultAPI"`      (from `1-secrets-vault`)
  - `bus: "MessageBus"`
- `ConfigChangeProposal` — dataclass:
  - `ext_name: str`
  - `key: str`
  - `proposed_value: Any`
  - `author_qualname: str`
  - `submitted_at: datetime`

## Interfaces

### Public API

N/A for REST; the scope is a per-process object handed to extensions.

### Internal API

Code under
`source/site/automojo/pychestrate/webservice/extension/config/`.

```python
# scope.py
class ExtensionConfigScope:
    """
        Scoped view into ext.<name>.* variables and secrets.
    """

    def __init__(self, *, ext_name: str,
                 manifest_capabilities: FrozenSet[str],
                 variable_api: "GlobalVariableAPI",
                 secrets_api: "SecretsVaultAPI",
                 bus: "MessageBus") -> None:
        ...

    def get_variable(self, *, name: str, default: Optional[Any] = None) -> Any:
        ...

    def list_variable_names(self) -> List[str]:
        ...

    def get_secret(self, *, name: str) -> str:
        ...

    def dispatch_config_change(self, *, proposal: "ConfigChangeProposal") -> None:
        ...

    def _require_scoped_key(self, *, relative_name: str) -> str:
        """
            Returns the fully-qualified key 'ext.<name>.<relative>'
            after validating the relative name.
        """
        ...


# factory.py
def build_scope_for_extension(*, ext_name: str,
                              manifest: "ExtensionManifest") -> ExtensionConfigScope:
    ...
```

### Extension Surface

- Reuses the `variable_resolver` and `secret_ref_dereferencer` factory
  protocols declared in `E-factory-protocols` (owned by
  `2-global-variables`). No new factory protocol here.

### Events Emitted

- `extension.config_changed` — `{ext_name: str, keys: List[str]}`
- `extension.secret_rotated` — `{ext_name: str, key: str}`
- `extension.config_permission_denied` —
  `{ext_name: str, capability: str, key: str}`
- `extension.config_change_proposed` — `{ext_name, key, author}`

### Events Consumed

- `entity.variable.changed` — filters to `ext.*` keys; re-emits as
  scoped event; invalidates per-ext caches.
- `entity.secret.rotated` — filters similarly.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/extension/config/
    __init__.py
    scope.py              # ExtensionConfigScope
    factory.py            # build_scope_for_extension()
    proposals.py          # ConfigChangeProposal dataclass
    cache.py              # Per-ext read cache + invalidation
```

## Key Flows

### Flow A — Extension reads a variable

1. During `on_load`, the lifecycle coordinator calls
   `build_scope_for_extension(ext_name=..., manifest=...)` and passes
   the scope to the extension class's `on_load(cls, *, scope)` hook.
2. Extension calls `scope.get_variable(name="retry_max", default=5)`.
3. Scope computes the fully-qualified key `ext.<name>.retry_max` and
   calls `variable_api.get(key=..., default=5)`.
4. If the resolved value is a `$ref:secrets://...`, scope checks the
   capability and raises `PermissionError` if absent.
5. Returns the typed value.

### Flow B — Extension reads a secret

1. Scope rejects when `read:secrets` is not in manifest
   capabilities — `PermissionError` + `extension.config_permission_denied`.
2. Otherwise calls `secrets_api.get(key=..., for_extension=<name>)`,
   which audit-logs via `1-audit-log`.
3. Returns decrypted value; cached in-process for 60 s (configurable
   via `ext.<name>.cache.secret_ttl`).

### Flow C — Config change propagation

1. Admin changes `ext.<name>.retry_max` via the admin API.
2. `2-global-variables` emits `entity.variable.changed`.
3. E-extension-config subscribes, filters, re-emits
   `extension.config_changed`; invalidates the per-ext cache.
4. Extension reads the new value on the next call.

## Error Handling

- `SemanticError` — extension attempts to read a non-scoped key or
  write through the scope; always bubbles.
- `PermissionError` — missing `read:secrets` capability.
- `ConfigurationError` — vault lookup of a scoped key fails with
  not-found or decrypt error.
- Multiline error messages via `os.linesep.join` for all raised
  errors.

## Security Considerations

- Scope enforces capability pre-check before any secret lookup; vault
  API never sees a request from an extension lacking capability.
- Scope never exposes the raw `secrets_api` or `variable_api`
  objects; extensions interact only through scoped methods.
- Secret reads are audit-logged via `1-audit-log` with actor
  `extension:<name>`.
- Rate limit on scoped reads (per-ext, 100 req/s default) to contain
  runaway loops.

## Observability

- Metrics:
  - `pychestrate_extension_config_read_total{ext,kind,result}`
  - `pychestrate_extension_config_permission_denied_total{ext,capability}`
  - `pychestrate_extension_config_cache_hit_total{ext,kind}`
- Log events: `pychestrate_extension_config_changed`,
  `pychestrate_extension_secret_rotated`,
  `pychestrate_extension_config_permission_denied`.
- Trace span: `pychestrate_extension.config.read`,
  `pychestrate_extension.config.dispatch_change`.

## Open Questions

- Should scope support transactional multi-read? Deferred pending
  demand.
- Should proposals from `dispatch_config_change` appear in a built-in
  review queue or only on the bus? Timebox to Phase 10 admin polish.
