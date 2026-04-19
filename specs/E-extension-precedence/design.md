# E-extension-precedence — Design

## Architecture

E-extension-precedence is a small post-registration transformation
applied by `E-extension-host` before it builds the sorted chain. The
precedence layer owns `PrecedenceOverrideTable`, which holds the parsed
site pin file and applies its values as the factor chain is constructed.
The layer is intentionally stateless beyond that table: it exposes a
single `apply(chain)` function that returns a re-sorted tuple. The
`snapshot_digest` of the host includes effective precedence values, so
any drift between nodes is detectable.

## Data Model

In-memory (no SQL):

- `PrecedencePin` — dataclass:
  - `qualname: str`
  - `effective_precedence: int`
  - `source: Literal["site_file","env_override"]`
  - `source_path: Optional[Path]`
- `PrecedenceOverrideTable`:
  - `pins: Dict[str, PrecedencePin]`
  - `file_sha256: Optional[str]`
  - `loaded_at: datetime`

## Interfaces

### Public API

CLI:

- `pychestrate-admin precedence show [--qualname=<q>]` — print the
  effective chain and pin sources.
- `pychestrate-admin precedence validate --file=<path>` — dry-run-
  validate a pin file without applying it.

REST (Phase 10 via `E-extension-registry-ui`):

- `GET /admin/extensions/precedence` — permission `extensions.read`.

### Internal API

Code under
`source/site/automojo/pychestrate/webservice/extension/precedence/`.

```python
# table.py
class PrecedenceOverrideTable:
    """
        Holds pin values sourced from etc/pychestrate/extension_precedence.yaml
        (or PYCHESTRATE_PRECEDENCE_FILE) and provides effective-precedence lookup.
    """

    def __init__(self) -> None:
        ...

    def load_from_file(self, *, path: Path) -> None:
        ...

    def effective_precedence_for(self, *, qualname: str,
                                 declared_precedence: int) -> int:
        ...

    def list_pins(self) -> List[PrecedencePin]:
        ...

    def diff(self, *, other: "PrecedenceOverrideTable") -> Dict[str, Tuple[Optional[int], Optional[int]]]:
        ...


def get_precedence_override_table() -> PrecedenceOverrideTable:
    ...


# apply.py
def apply_precedence(*, factory_classes: List[Type["FactoryExtension"]],
                     table: PrecedenceOverrideTable,
                     manifests: Mapping[str, "ExtensionManifest"]) -> Tuple[Type["FactoryExtension"], ...]:
    """
        Returns the sorted tuple of factory classes after applying site pins.

        :raises ConfigurationError: reserved-band violation without capability.
    """
    ...
```

### Pin file schema (v1)

```yaml
schema_version: 1
pins:
  - qualname: pychestrate_ext_s3_object_store.S3ObjectStoreDriver
    precedence: 150
  - qualname: pychestrate_ext_hvac_secrets.VaultSecretsBackend
    precedence: 10
```

### Extension Surface

- `PRECEDENCE` — the class-level attribute already supplied by
  upstream `FactoryExtension`.
- Reserved bands:
  - `[0, 99]` — platform-only (requires capability
    `pychestrate.platform.precedence_low`).
  - `[100, 999]` — third-party production overrides.
  - `[1000, 1999]` — in-tree reference implementations (default band).
  - `[2000, +)` — opt-in fallback.

### Events Emitted

- `extension.precedence_loaded` — `{pin_count: int, file_sha256: str}`
- `extension.precedence_override_changed` —
  `{added: List, removed: List, changed: Dict[qualname, (old, new)]}`
- `extension.precedence_pin_unresolved` — `{qualname: str}`
- `extension.precedence_reserved_band_violation` —
  `{qualname: str, precedence: int}`

### Events Consumed

- `extension.rescan_completed` — reloads the pin file and re-applies.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/extension/precedence/
    __init__.py
    table.py              # PrecedenceOverrideTable singleton
    apply.py              # apply_precedence
    file_loader.py        # YAML pin-file parser
    bands.py              # Band definitions + capability check
    cli.py                # pychestrate-admin precedence ...
    admin_routes.py       # GET /admin/extensions/precedence
```

## Key Flows

### Flow A — Bootstrap

1. `E-extension-host` finishes module load and produces raw factory
   classes.
2. Precedence layer calls `load_from_file(path=...)` using
   `PYCHESTRATE_PRECEDENCE_FILE` or the default site path; absent file
   → empty table.
3. `apply_precedence` builds `(effective_precedence, qualname)` keys
   per class, validates reserved bands against the class's
   manifest.capabilities, then returns the sorted tuple.
4. Host stores the sorted chain; `snapshot_digest` includes effective
   values.

### Flow B — Pin-file change on rescan

1. Admin edits the file; calls `POST /admin/extensions/rescan`.
2. Host rescans; precedence layer reloads the file; compares sha256
   against previous.
3. If changed, emits `extension.precedence_override_changed` with a
   diff; otherwise no event.
4. Host rebuilds the sorted chain atomically.

## Error Handling

- `ConfigurationError` — duplicate pin entries, reserved-band
  violations without capability, malformed YAML.
- Multiline error messages via `os.linesep.join`.
- Warn-only for unresolved pins (qualname not loaded).

## Security Considerations

- Pin file must resolve under `/etc/pychestrate/` or the env-specified
  path; no path traversal.
- File parsed with `yaml.safe_load`.
- Reserved `[0, 99]` band requires explicit capability, so a
  mis-configured third-party pack cannot pin itself above core.
- Admin REST gated by `extensions.read`.

## Observability

- Metrics:
  - `pychestrate_extension_precedence_pins_active{qualname}`
  - `pychestrate_extension_precedence_override_file_reads_total`
  - `pychestrate_extension_precedence_reserved_band_violations_total`
- Log events: `pychestrate_extension_precedence_loaded`,
  `pychestrate_extension_precedence_pin_unresolved`,
  `pychestrate_extension_precedence_override_changed`.
- Trace span: `pychestrate_extension.precedence.apply`.

## Open Questions

- Should pins support range patterns (`pychestrate_ext_*.*`) as well
  as exact qualnames? Timebox to Phase 10 when third-party density
  rises.
- Should a pin carry an expiration date to signal temporary overrides?
  Deferred pending demand.
