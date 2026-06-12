# 8-cli — Design

## Architecture

`8-cli` is a standalone Python package `pychestrate-cli` installed as
the `pyc` entry point. Its source lives under
`source/site/ccai/pychestrate/cli/` and it depends only on the
published surface of `8-rest-api-v1`. The command tree is generated
at build time from the server's OpenAPI document
(`/api/v1/_meta/openapi.json`) plus the list of
`CLISubcommandExtension` registrations collected at runtime via a
lightweight extension host instance (the CLI runs the same
`E-extension-host` scanner the server uses, but only to enumerate
`CLISubcommandExtension` classes — no factory protocols are
resolved). The CLI has three layers: a *parser* (argparse-based,
populated from OpenAPI + extensions), a *transport* (HTTP client
with profile-driven auth), and a *renderer* (table/JSON/yaml/tsv).
Credentials are read from `~/.pychestrate/credentials`. This feature
ships in **Phase 10 — Public Surface & Extensibility Completion**.

## Data Model

The CLI is stateless on disk except for:

- `~/.pychestrate/credentials` — INI-style:
  ```
  [default]
  server_url = https://pychestrate.example.com
  bearer_token = <token>
  bearer_token_expires_at = 2026-05-01T12:00:00Z
  mtls_cert_path = /home/me/.pychestrate/cert.pem
  mtls_key_path = /home/me/.pychestrate/key.pem
  verify_tls = true

  [staging]
  server_url = https://staging.pychestrate.example.com
  bearer_token = <token>
  ```
  Mode: `0600`. Permissions enforced at load.

- `~/.pychestrate/cache/openapi/<server-url-hash>.json` — cached
  OpenAPI snapshot, refreshed on version mismatch.

- `~/.pychestrate/state/downloads/<artifact_id>.partial` — resumable
  download progress file.

In-memory dataclasses:

```python
@dataclass(frozen=True)
class CliProfile:
    profile_name: str
    server_url: str
    bearer_token: Optional[str]
    bearer_token_expires_at: Optional[datetime]
    mtls_cert_path: Optional[str]
    mtls_key_path: Optional[str]
    verify_tls: bool


@dataclass(frozen=True)
class CommandInvocation:
    profile: CliProfile
    noun: str
    verb: str
    flags: Mapping[str, str]
    positional: list[str]
    output_format: str


@dataclass(frozen=True)
class RestOperation:
    operation_id: str
    method: str
    path: str
    required_permissions: list[str]
    body_schema: Optional[dict]
    response_schema: Optional[dict]
```

## Interfaces

### Public API

CLI commands (core):

- `pyc login [--profile <name>]`
- `pyc logout [--profile <name>]`
- `pyc config set <key> <value> [--profile <name>]`
- `pyc config get <key> [--profile <name>]`
- `pyc version`
- `pyc user list | get <id> | create | update <id> | delete <id>`
- `pyc project list | get <id> | create | update <id> | delete <id>`
  - `pyc project members list | add | remove`
  - `pyc project variables list | set | unset`
- `pyc pod list | get <id> | register | update <id> | delete <id>`
- `pyc client list | get <id> | enroll | update <id> | delete <id>`
- `pyc run list | get <id> | create | cancel <id>`
- `pyc resource list | get <id> | create | update <id> | delete <id>`
- `pyc reservation list | get <id> | create | release <id>`
- `pyc artifact list | get <id> | download <id>`
- `pyc metric query <expr> | definitions`

Extension commands:

- `pyc ext <ext-name> <subcommand>` for every
  `CLISubcommandExtension` registered.

Meta:

- `pyc --help`, `pyc <noun> --help`, `pyc <noun> <verb> --help`.

### Internal API

Module `ccai.pychestrate.cli.parser`:

```python
def build_command_tree(
        *,
        openapi_document: dict,
        extension_subcommands: list[CLISubcommandDescriptor]
    ) -> CommandTree:
    """
        Build the argparse tree from OpenAPI + extension registrations.

        :param openapi_document: Live OpenAPI document as a dict.
        :param extension_subcommands: Subcommand descriptors from
            `CLISubcommandExtension` registrations.

        :returns: The populated CommandTree used by `argparse`.
        :raises: ConfigurationError
    """
    ...


def parse_invocation(
        *,
        tree: CommandTree,
        argv: list[str]
    ) -> CommandInvocation:
    """Parse argv against the command tree."""
    ...
```

Module `ccai.pychestrate.cli.credentials`:

```python
def load_profile(
        *,
        profile_name: Optional[str]
    ) -> CliProfile:
    """
        Load a profile, enforcing mode `0600` on the credentials file.

        :raises: CredentialsFilePermissionError,
                 CredentialsFileNotFoundError,
                 ProfileNotFoundError
    """
    ...


def store_token(
        *,
        profile_name: str,
        bearer_token: str,
        bearer_token_expires_at: datetime
    ) -> None:
    """Write-through update of the named profile; preserves mode 0600."""
    rtnval = None
    return rtnval
```

Module `ccai.pychestrate.cli.transport`:

```python
def execute_request(
        *,
        profile: CliProfile,
        operation: RestOperation,
        path_params: Mapping[str, str],
        query_params: Mapping[str, str],
        body: Optional[dict],
        idempotency_key: Optional[str]
    ) -> RestResponse:
    """
        Drive a single REST call with profile auth and timeouts.

        :raises: AuthenticationError, RateLimitedError,
                 NotFoundError, ConflictError, ServerError
    """
    ...
```

Module `ccai.pychestrate.cli.renderer`:

```python
def render(
        *,
        response: RestResponse,
        output_format: str,
        fields: Optional[list[str]],
        is_tty: bool
    ) -> RenderedOutput:
    """Serialize a response to the requested output format."""
    ...
```

Module `ccai.pychestrate.cli.download`:

```python
def resumable_download(
        *,
        profile: CliProfile,
        artifact_id: str,
        destination_path: str
    ) -> DownloadResult:
    """
        Download an artifact with HTTP Range resume and SHA-256 check.

        :raises: IntegrityMismatchError, ServerError
    """
    ...
```

### Extension Surface

Resource base `CLISubcommandExtension` declared in
`ccai.pychestrate.cli.extensions.cli_subcommand`:

```python
class CLISubcommandExtension(ResourceExtension):
    ext_name: str
    cli_schema_version: int

    @classmethod
    def declare_subcommands(cls) -> list[CLISubcommandDescriptor]:
        """
            Return descriptors for each subcommand under
            `pyc ext <ext_name>`; each descriptor names the REST
            operation_id it wraps.
        """
        ...

    @classmethod
    def required_capabilities(cls) -> list[str]:
        """Sandbox capability keys propagated from the REST endpoint."""
        ...
```

Reference implementation (shipped in the sample extension pack):
`PycExtExampleSubcommand` exposing `pyc ext example echo` over the
`ExampleEchoEndpoints` REST routes.

### Events Emitted

The CLI does not emit entity events; it consumes REST API responses.
Telemetry is emitted via its OTLP exporter (opt-in):

- `cli.invoked`, `cli.succeeded`, `cli.failed`,
  `cli.credentials_refused`, `cli.openapi_refreshed`.

### Events Consumed

None from the message bus. The CLI reacts only to REST responses and
local files.

## Component Breakdown

```
source/site/ccai/pychestrate/cli/
    __init__.py
    entry.py                        # `pyc` entry point
    parser.py                       # argparse builder from OpenAPI
    credentials.py                  # ~/.pychestrate/credentials loader
    transport.py                    # HTTP client with profile auth
    renderer.py                     # table / json / yaml / tsv
    download.py                     # resumable download
    prompt.py                       # interactive confirmations
    openapi_cache.py                # server-version-aware cache
    exit_codes.py                   # enumerated CLI exit codes
    extensions/
        cli_subcommand.py           # ResourceExtension base
    commands/
        core/
            auth.py                 # login/logout
            users.py
            projects.py
            pods.py
            clients.py
            runs.py
            resources.py
            reservations.py
            artifacts.py
            metrics.py
            config.py
            version.py
    models.py                       # CliProfile, CommandInvocation, ...
    exceptions.py
```

## Key Flows

**`pyc login --profile staging`:**

1. `parser.parse_invocation` matches the `login` command.
2. `credentials.load_profile` resolves (or creates) the `staging`
   profile scaffold.
3. `transport.execute_request` hits
   `POST /api/v1/auth/oidc/device` and polls the verification URL.
4. On success, `credentials.store_token` writes the bearer token
   and its expiry with mode `0600`.
5. The CLI prints the expiry and exits `0`.

**`pyc run list --output json --fields run_id,status,started_at`:**

1. Parser resolves the `run list` path to the
   `runs_list` operation id from the cached OpenAPI document.
2. `credentials.load_profile` returns the active profile.
3. `transport.execute_request` issues
   `GET /api/v1/runs?...` with either mTLS or bearer auth.
4. `renderer.render` emits a canonical JSON array filtered to the
   three requested fields.
5. Exit `0`.

**Extension Subcommand:**

1. At first command execution per session, the extension host
   scans for `CLISubcommandExtension` subclasses and merges their
   descriptors into the command tree (cached for the rest of the
   process lifetime).
2. `pyc ext example echo hello` parses, authenticates per the
   active profile, and invokes
   `POST /api/v1/ext/example/echo` with the supplied body.
3. Renderer emits the response per `--output`.

**Resumable Download:**

1. `pyc artifact download <id> -o /tmp/out.bin` checks for an
   existing `~/.pychestrate/state/downloads/<id>.partial` entry.
2. If present, `download.resumable_download` sends
   `Range: bytes=<offset>-` and appends.
3. After the last byte, the computed SHA-256 is compared to the
   server-supplied digest; mismatch → exit `7` with an integrity
   error; match → rename partial to final.

## Error Handling

- `CredentialsFilePermissionError` — mode > `0600`; exit `13`.
- `CredentialsFileNotFoundError` — exit `13` with the path that
  was expected.
- `ProfileNotFoundError` — exit `2` (usage).
- `AuthenticationError` — exit `3`.
- `NotFoundError` — exit `4`.
- `ConflictError` — exit `5`.
- `RateLimitedError` — exit `6`; prints `Retry-After`.
- `ServerError` — exit `7`; includes correlation id.
- `IntegrityMismatchError` — exit `7`.
- `ConfigurationError` — raised by the parser when an extension
  declares a malformed subcommand descriptor; the extension's
  subcommands are skipped and a diagnostic prints to stderr.
- `SemanticError` — raised on internal misuse; never caught;
  bubbles to the CLI's top-level which prints the traceback under
  `--debug` only.
- Error messages assembled with `os.linesep.join([...])` so
  multi-line context prints predictably.

## Security Considerations

- `~/.pychestrate/credentials` refused above mode `0600`.
- Bearer tokens passed via request headers only; never via argv or
  environment for subprocess launches.
- mTLS key files opened read-only with
  `stat.S_IRUSR` required.
- TLS verification defaults on; `--insecure` triggers a persistent
  stderr warning and SHALL NEVER be honored when the CLI is run
  inside CI (detection via `CI=true`; opt-out via
  `PYC_ALLOW_INSECURE_IN_CI=1`).
- OIDC device flow tokens refreshed automatically when within
  60 s of `bearer_token_expires_at`.
- Download bytes verified against server-supplied SHA-256.
- The CLI scrubs sensitive query parameters (`token`, `secret`,
  `signature`) from its `--verbose` output.

## Observability

Metrics (OTLP opt-in):

- `pychestrate_cli_invocations_total{command,outcome}`
- `pychestrate_cli_duration_seconds` (histogram)
- `pychestrate_cli_credential_failures_total{reason}`
- `pychestrate_cli_openapi_refreshes_total`

Stderr log events: `cli.invoked`, `cli.succeeded`, `cli.failed`,
`cli.credentials_refused`, `cli.openapi_refreshed`,
`cli.download_resumed`, `cli.confirmation_prompted`.

Trace spans: `cli.parse`, `cli.auth`, `cli.request`, `cli.render`,
`cli.download`.

## Open Questions

- Do we ship an alias layer for legacy Jenkins-style verbs
  (`build`, `abort`) that redirect to `run create` and
  `run cancel`? Likely no; revisit if users request it.
- Should the CLI bundle a local OpenAPI document to skip the cache
  miss on first run? Trade-off: binary size vs. first-call latency.
  Close during Phase 10 GA.
- Shell completion — at what priority? Defer; tracked under
  post-Phase-10 backlog.
