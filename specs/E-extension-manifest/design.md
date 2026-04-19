# E-extension-manifest — Design

## Architecture

E-extension-manifest is a load-time gatekeeper inserted between
`E-extension-host`'s namespace scanner and its type-registration step.
The host scanner produces a candidate list of
`(distribution_name, module_list)`; the manifest layer resolves the
package's `pychestrate_ext.yaml` via `importlib.metadata.Distribution.files`,
parses it under a strict schema, performs version-bound validation, and
returns an `ExtensionManifest` object that downstream Layer E features
consume. The manifest is the authoritative metadata source for an
extension; the host never introspects a package's identity.

## Data Model

In-memory (no SQL):

- `ExtensionManifest` — dataclass:
  - `name: str`                           (required, matches `^[a-z][a-z0-9-]*$`)
  - `version: "packaging.version.Version"`(required, PEP 440)
  - `schema_version: int`                 (required, manifest schema itself, currently `1`)
  - `author: Optional[str]`
  - `homepage: Optional[str]`
  - `license: Optional[str]`
  - `protocols: Tuple[str, ...]`
  - `resources: Tuple[str, ...]`
  - `capabilities: Tuple[str, ...]`
  - `subscriptions: Tuple[str, ...]`
  - `depends_on: Tuple[str, ...]`
  - `min_service_version: "packaging.version.Version"`   (default `0.0.0`)
  - `max_service_version: Optional["packaging.version.Version"]`
  - `distribution_name: str`
  - `manifest_path: Path`
  - `unknown_keys: Tuple[str, ...]`

## Interfaces

### Public API

The manifest schema itself is the public API for extension authors;
versioned by `schema_version`. Documented in `E-extension-docs`.

CLI:

- `pychestrate-admin manifest validate <path-or-dist>` — validates a
  manifest and prints parsed summary or errors.

REST (Phase 10 via `E-extension-registry-ui`):

- `GET /admin/extensions/{name}/manifest` — permission
  `extensions.read`.

### Internal API

Code under
`source/site/automojo/pychestrate/webservice/extension/manifest/`.

```python
# parser.py
def find_manifest_for_distribution(*, distribution_name: str) -> Optional[Path]:
    ...

def parse_manifest(*, manifest_path: Path,
                   distribution_name: str) -> ExtensionManifest:
    """
        Parses and validates a pychestrate_ext.yaml file.

        :raises ConfigurationError: malformed YAML, missing required
                                    fields, invalid PEP 440.
    """
    ...


# validator.py
def validate_version_window(*, manifest: ExtensionManifest,
                            running_service_version: "packaging.version.Version") -> None:
    """
        :raises ConfigurationError: running version outside the window.
    """
    ...

def validate_declared_inventory(*, manifest: ExtensionManifest,
                                loaded_factory_protocols: List[str],
                                loaded_resource_kinds: List[str]) -> None:
    ...


# registry.py
class ManifestRegistry:
    """
        Process-singleton keyed by extension name; holds the parsed
        manifest for every loaded package and for every package refused
        at load time (with the refusal reason).
    """

    def __init__(self) -> None:
        ...

    def register(self, *, manifest: ExtensionManifest) -> None:
        ...

    def record_refusal(self, *, distribution_name: str, reason: str,
                       detail: str) -> None:
        ...

    def get(self, *, name: str) -> Optional[ExtensionManifest]:
        ...

    def list_all(self) -> List[ExtensionManifest]:
        ...

    def list_refusals(self) -> List["ManifestRefusal"]:
        ...


def get_manifest_registry() -> ManifestRegistry:
    ...
```

### Manifest schema (v1) YAML example

```yaml
schema_version: 1
name: pychestrate-ext-s3-object-store
version: 1.2.0
author: "AutomationMojo"
homepage: "https://github.com/automationmojo/pychestrate-ext-s3-object-store"
license: "MIT"
min_service_version: "1.0.0"
max_service_version: "2.0.0"
protocols:
  - object_store_driver
resources: []
capabilities:
  - net:outbound
  - read:secrets
subscriptions:
  - entity.artifact.ingested
depends_on: []
```

### Extension Surface

None directly. This feature defines the manifest file format every
extension must ship.

### Events Emitted

- `extension.manifest_parsed` —
  `{name: str, version: str, capabilities: List[str]}`
- `extension.manifest_rejected` —
  `{distribution_name: str, reason: str, detail: str}`
- `extension.manifest_missing` —
  `{distribution_name: str}`

### Events Consumed

- `extension.scan_started` — kicks off manifest pre-resolution before
  module import.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/extension/manifest/
    __init__.py
    schema.py              # ExtensionManifest dataclass + constants
    parser.py              # YAML → ExtensionManifest
    validator.py           # Version + inventory validators
    registry.py            # ManifestRegistry singleton
    refusals.py            # ManifestRefusal dataclass
    cli.py                 # pychestrate-admin manifest validate
    admin_routes.py        # GET /admin/extensions/{name}/manifest
```

## Key Flows

### Flow A — Load-time manifest pass

1. Host scanner emits candidate list; for each distribution, manifest
   layer calls `find_manifest_for_distribution`.
2. Missing manifest: strict → record refusal + abort; permissive →
   synthesize default + warn.
3. Present manifest: `parse_manifest` under `yaml.safe_load`; required
   field check; PEP 440 parse for version and bounds; unknown-key warn.
4. `validate_version_window` against the running service version;
   refuse on mismatch.
5. Pass the parsed manifest to the host; host performs module import
   and type registration.
6. After import, `validate_declared_inventory` compares declared vs
   delivered protocol and resource names; refuse on mismatch (strict).

### Flow B — Rescan refresh

1. `E-extension-host.rescan` re-walks namespace; manifest layer
   re-resolves files for newly discovered distributions.
2. Existing distributions whose manifest file has not changed on disk
   (mtime + digest) skip re-parse.
3. Changes emit `extension.manifest_parsed` + propagate to downstream
   Layer E features.

## Error Handling

- `ConfigurationError` — malformed YAML, missing required fields,
  invalid PEP 440, version-window mismatch in strict mode, inventory
  mismatch in strict mode.
- Multiline error messages built with `os.linesep.join`; include
  manifest path and distribution name.
- `SemanticError` — manifest registry `get` with an unknown name;
  always bubbles.

## Security Considerations

- `yaml.safe_load` only; no custom tags.
- Manifest path resolved via `importlib.metadata.Distribution.files` —
  never from user input — preventing path traversal.
- Capability lists are recorded only; enforcement is handled in
  `E-extension-sandbox`.
- REST surface gated by `extensions.read`.

## Observability

- Metrics:
  - `pychestrate_extension_manifest_parsed_total{result="ok|rejected"}`
  - `pychestrate_extension_manifest_version_rejected_total`
  - `pychestrate_extension_manifest_missing_total`
  - `pychestrate_extension_manifest_inventory_mismatch_total`
- Log events:
  `pychestrate_extension_manifest_parsed`,
  `pychestrate_extension_manifest_rejected`,
  `pychestrate_extension_manifest_synthesized`,
  `pychestrate_extension_manifest_unknown_key`.
- Trace span: `pychestrate_extension.manifest.parse`.

## Open Questions

- Should we support manifest schema migration (v1 → v2) with a
  warn-and-upgrade flow, or a hard break? Timebox to Phase 10 when
  `E-plugin-api` lands.
- Should the manifest support signed bodies for supply-chain
  integrity? Timebox to Phase 8 alongside `E-extension-sandbox`.
