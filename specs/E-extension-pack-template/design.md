# E-extension-pack-template — Design

## Architecture

E-extension-pack-template is a code-generator plus a versioned
template corpus. The generator lives under the admin CLI in the
`pychestrate-service` repository and uses a Jinja2-style renderer to
produce a full source tree for a new extension pack. The corpus is
vendored inside the service source so it participates in the service's
own tests — regressions in the template are caught at service CI time
rather than at extension-author-time.

## Data Model

In-memory (no SQL):

- `PackTemplateManifest` — dataclass:
  - `template_version: int`
  - `files: Tuple[PackTemplateFile, ...]`
- `PackTemplateFile`:
  - `relative_path: str`
  - `source_path: Path`
  - `render_mode: Literal["copy","jinja"]`
- `PackGenerationRequest`:
  - `name: str`
  - `normalized_name: str`
  - `author: Optional[str]`
  - `license: Optional[str]`
  - `protocol_names: Tuple[str, ...]`
  - `resource_base_names: Tuple[str, ...]`
  - `target_dir: Path`

## Interfaces

### Public API

CLI:

- `pychestrate-admin pack-template new --name=<s>
   [--author=<s>] [--license=<s>] [--protocol=<p>]*
   [--resource=<r>]* [--target=<path>]`
- `pychestrate-admin pack-template upgrade [--apply] [--baseline=<int>]`
- `pychestrate-admin pack-template list-versions`

### Internal API

Code under
`source/site/automojo/pychestrate/webservice/extension/pack_template/`.

```python
# generator.py
class PackGenerator:
    """
        Renders the template corpus into a target directory.
    """

    def __init__(self, *, corpus_root: Path) -> None:
        ...

    def generate(self, *, request: PackGenerationRequest) -> Path:
        ...

    def upgrade(self, *, pack_root: Path,
                apply: bool,
                baseline: int) -> "UpgradeDiff":
        ...

    def list_versions(self) -> List[int]:
        ...


def normalize_pack_name(*, raw: str) -> str:
    ...


# corpus.py
def load_template_manifest(*, corpus_root: Path, version: int) -> PackTemplateManifest:
    ...
```

### Template corpus layout

```
source/site/automojo/pychestrate/webservice/extension/pack_template/corpus/
    v1/
        _meta.yaml
        pyproject.toml.jinja
        pychestrate_ext.yaml.jinja
        source/
            packages/
                automojo/
                    factories/
                        pychestrate/
                            __NAME__/
                                sample_factory.py.jinja
                    extensions/
                        pychestrate/
                            __NAME__/
                                sample_resource.py.jinja
        tests/
            contract/
                test_layer_e.py.jinja
            unit/
                test_sample.py.jinja
        .github/workflows/ci.yaml.jinja
        README.rst.jinja
        AGENTS.md.jinja
```

### Extension Surface

None.

### Events Emitted

- `extension.pack_template_generated` — `{name, target}`
- `extension.pack_template_upgrade_applied` —
  `{pack_root, from_version, to_version, files_changed}`

### Events Consumed

- None.

## Component Breakdown

```
source/site/automojo/pychestrate/webservice/extension/pack_template/
    __init__.py
    generator.py
    corpus.py
    cli.py
    corpus/
        v1/ ...
    diff.py                 # UpgradeDiff dataclass and computation
```

## Key Flows

### Flow A — Generate a new pack

1. Caller runs `pychestrate-admin pack-template new --name=s3-object-store
   --protocol=object_store_driver --author="..."`.
2. CLI validates name via `normalize_pack_name`; refuses if empty or
   if the normalized form differs and `--allow-normalize` is not set.
3. `PackGenerator.generate` loads corpus `vN` (latest by default),
   writes to a temp directory, then atomically moves to
   `<cwd>/pychestrate-ext-<name>/`.
4. Emits `extension.pack_template_generated`.

### Flow B — Upgrade in place

1. Inside an existing pack, caller runs
   `pychestrate-admin pack-template upgrade`.
2. Generator reads `TEMPLATE_VERSION` from the pack's `_meta.yaml`;
   if missing, aborts unless `--baseline=<int>` provided.
3. Re-renders corpus `vLatest` into a temp tree with the pack's
   stored parameters.
4. Computes per-file diff; prints the summary.
5. If `--apply`, writes each changed file; does not remove
   user-added files; preserves user modifications in a conflict
   table.

### Flow C — Self-test inside a generated pack

1. `tests/contract/test_layer_e.py` imports the service's test
   harness fixtures (published under `8-plugin-api`).
2. Spins a fixture service; calls
   `fixture.install_pack(pack_root=.)`; asserts the pack loads and
   passes manifest, compat, and (optionally) sandbox checks.
3. Emits a `testrun_summary.json` compatible with `automojo-testbase`.

## Error Handling

- `ConfigurationError` — target directory non-empty; unreadable
  corpus; invalid name. Multiline messages via `os.linesep.join`.
- On render failure: temp dir is deleted before raising; no
  half-written output persists.
- `SemanticError` — upgrade invoked outside a valid pack root;
  bubbles.

## Security Considerations

- Name validation refuses shell metacharacters.
- Generated CI workflow pins action versions to SHAs.
- Template does not embed any secrets; author/license fields are
  user-supplied and HTML-escaped in `README.rst`.

## Observability

- Metrics:
  - `pychestrate_extension_pack_template_generations_total{result}`
  - `pychestrate_extension_pack_template_upgrades_total{result,delta}`
- Log events:
  `pychestrate_extension_pack_template_generated`,
  `pychestrate_extension_pack_template_upgrade_diff`,
  `pychestrate_extension_pack_template_upgrade_applied`.
- Trace span: `pychestrate_extension.pack_template.generate`,
  `pychestrate_extension.pack_template.upgrade`.

## Open Questions

- Should the template be published as its own pip-installable
  generator to enable offline use? Deferred pending demand.
- Should we support multi-language templates (TypeScript-only
  packs)? Deferred.
