# 8-cli — Requirements

## Introduction

`8-cli` is Pychestrate's first-class command-line interface, published
as the `pyc` executable. It is a thin, scriptable client that speaks
*only* through `8-rest-api-v1` — no direct DB access, no bypass of
the API surface. The CLI mirrors the REST API exactly: every
capability in the API is reachable via a command, and no capability
is reachable via the CLI that is not also in the API. Extensions
publish new subcommands through the `CLISubcommandExtension`
resource base, which maps one-to-one onto
`RestEndpointExtension`-contributed routes. Authentication uses
`~/.pychestrate/credentials` (profiles, tokens, optional mTLS
certificate paths). This feature ships in **Phase 10 — Public
Surface & Extensibility Completion**.

## Requirements

### Requirement 1: Command Structure and Parity with REST

**User Story:** As an operator or automator, I want a predictable
`pyc <noun> <verb>` command structure that mirrors the REST API, so
that I never have to guess which commands exist.

**Acceptance Criteria (EARS):**

1. WHEN the CLI is invoked THEN the top-level command structure
   SHALL follow `pyc <noun> <verb> [flags] [positional-args]` where
   `<noun>` is one of the REST resource roots
   (`user`, `project`, `pod`, `client`, `run`, `resource`,
   `reservation`, `artifact`, `metric`) and `<verb>` is one of
   `list | get | create | update | delete | cancel | release |
   download | query` (subset per resource).
2. WHEN `pyc <noun> <verb> --help` is invoked THEN the output SHALL
   be non-empty (> 0 bytes), SHALL include the resolved REST
   endpoint in the description, and SHALL exit with status `0`.
3. IF a REST capability exists at `/api/v1/<resource>/...` THEN the
   CLI SHALL expose an equivalent command reachable under
   `pyc <resource> ...`; the build SHALL fail if a capability-coverage
   check detects a missing command.
4. WHERE a command requires a body the CLI SHALL accept the body
   from `--from-file <path>`, `--set key=value` (repeatable), or
   stdin when invoked with `-`; exactly one of the three SHALL be
   used per call.
5. WHEN `pyc --version` is invoked THEN the output SHALL print the
   CLI package version, the server version discovered at
   `/api/v1/_meta/versions`, and SHALL exit `0`.

### Requirement 2: Credentials File and Profiles

**User Story:** As an automator, I want profile-based credentials in
`~/.pychestrate/credentials`, so that I can switch between staging
and production with a single flag.

**Acceptance Criteria (EARS):**

1. WHEN the CLI starts THEN it SHALL read
   `~/.pychestrate/credentials` (INI-style) and resolve the active
   profile per precedence: `--profile` flag > `PYC_PROFILE` env var
   > `default`.
2. WHEN a profile declares `bearer_token`, `mtls_cert_path`, and
   `mtls_key_path` THEN the CLI SHALL prefer mTLS if both paths
   exist and are readable; otherwise it SHALL use the bearer token.
3. IF the credentials file has mode broader than `0600` THEN the
   CLI SHALL refuse to start, print a single-line error to stderr,
   and exit with status `13`.
4. WHEN `pyc login [--profile=<name>]` is invoked THEN the CLI
   SHALL run the OAuth Device Authorization Grant against
   `/api/v1/auth/oidc/device`, write the returned token to the
   named profile with mode `0600`, and echo the expiry.
5. WHILE a command is run the CLI SHALL NOT write credentials to
   logs, `--verbose` output, or any error message.

### Requirement 3: Output Formats and Scripting

**User Story:** As a pipeline author, I want stable output formats
(JSON, table, yaml, tsv), so that `pyc` output is trivially
parseable.

**Acceptance Criteria (EARS):**

1. WHEN a command supports listing THEN it SHALL accept
   `--output {table,json,yaml,tsv}` with default `table` when
   stdout is a TTY and `json` when it is not.
2. WHEN `--output json` is requested THEN the output SHALL be a
   single JSON document (array for lists, object for singletons),
   UTF-8-encoded, newline-terminated, and parseable by `jq` without
   intermediate human prose.
3. IF `--output table` and the field `--fields a,b,c` are supplied
   THEN the table SHALL render exactly those columns in the given
   order; unknown fields SHALL cause a non-zero exit with
   `exit=2 (usage)`.
4. WHEN any command fails THEN the CLI SHALL print a
   `application/problem+json`-derived message to stderr, write the
   correlation id emitted by the server to stderr, and exit with a
   category-coded status: `2 usage`, `3 auth`, `4 not_found`,
   `5 conflict`, `6 rate_limited`, `7 server_error`.

### Requirement 4: Extension Subcommands

**User Story:** As an extension author, I want to ship `pyc`
subcommands from my package, so that my REST extension endpoints
have a first-class CLI experience.

**Acceptance Criteria (EARS):**

1. WHEN a package declares a `CLISubcommandExtension` with
   `ext_name = "foo"` THEN its commands SHALL be reachable under
   `pyc ext foo <subcommand>` and SHALL NOT pollute the top-level
   noun namespace.
2. IF a `CLISubcommandExtension` declares a subcommand that maps to
   a REST route not mounted at `/api/v1/ext/foo/...` THEN the CLI
   SHALL refuse to load the extension and SHALL print a single
   error.
3. WHEN the CLI is compiled THEN the OpenAPI document at
   `/api/v1/_meta/openapi.json` SHALL be the source of truth for
   command definitions; the CLI SHALL be regeneratable from that
   document plus any `CLISubcommandExtension` registrations.
4. WHERE an extension subcommand requires an extension sandbox
   capability (e.g., `dispatch:jobs`) the CLI SHALL surface
   `403 ext.capability_denied` as exit status `3` and SHALL echo
   the capability name in the error.

### Requirement 5: Interactive Modes and Pagination

**User Story:** As a human operator, I want ergonomic interactive
behavior (pagers, confirmations on destructive verbs, resumable
uploads/downloads), so that day-to-day use feels native.

**Acceptance Criteria (EARS):**

1. WHEN `pyc <noun> list` returns more than 200 rows AND stdout is
   a TTY THEN the CLI SHALL page output via `$PAGER` (falling back
   to `less -R`); non-TTY output SHALL never page.
2. WHEN `pyc <noun> delete` or `run cancel` is invoked AND stdout
   is a TTY THEN the CLI SHALL prompt
   `Delete/cancel <resource> '<name>'? [y/N] ` and proceed only on
   affirmative input; `--yes` SHALL bypass the prompt.
3. WHEN `pyc artifact download <artifact_id>` is invoked THEN the
   CLI SHALL support resume (via `HTTP Range`) and SHALL verify the
   downloaded bytes against the server-supplied SHA-256 before
   exiting `0`.

## Property-Based Test Requirements

### Property 1: `--help` Totality

- **Invariant:** For any command path (top-level, noun, verb,
  extension) reachable in the compiled CLI, invoking
  `<command> --help` SHALL produce output > 0 bytes on stdout,
  SHALL touch none of the server (no network call), and SHALL exit
  with status `0`.
- **Generator:** Hypothesis strategy enumerating every command path
  from the compiled command tree plus random `--help` prefix/suffix
  permutations.
- **Assertion:** Zero non-zero exits; zero network calls observed
  at the mocked HTTP layer; stdout byte count > 0 on every path.
- **Sample size:** 1000 generated cases (all distinct paths plus
  repeat samples for regression bias).

### Property 2: REST ↔ CLI Parity

- **Invariant:** For any operation declared in the latest OpenAPI
  document at `/api/v1/_meta/openapi.json`, there SHALL exist a
  corresponding CLI command path; and vice versa, every CLI command
  path (except `login`, `logout`, `config`, `version`) SHALL map
  to exactly one OpenAPI operation id.
- **Generator:** Strategy drawing operation ids from the OpenAPI
  document and command paths from the compiled command tree.
- **Assertion:** Bidirectional mapping is total and one-to-one for
  the non-meta subset; differences are flagged as build errors.
- **Sample size:** 1000 generated cases.

### Property 3: Output Format Stability

- **Invariant:** For any successful list command invocation with
  `--output json` against a fixed dataset, the output SHALL be
  identical byte-for-byte across 1000 invocations (canonical
  ordering, canonical encoding).
- **Generator:** Strategy producing list commands over a fixture
  server returning a fixed dataset with and without the
  `--fields` filter.
- **Assertion:** SHA-256 of stdout is identical across all
  invocations per `(command, fields, dataset)` tuple.
- **Sample size:** 1000 generated cases.

## Non-Functional Requirements

- **NFR-1 (Performance):** `pyc --help` cold start SHALL complete
  in `< 200 ms` on a warm Python cache. A typical `pyc run list`
  round-trip against a low-latency LAN API SHALL complete in
  `< 400 ms` p95.
- **NFR-2 (Security):** Credentials file SHALL be refused if mode
  > `0600`. Tokens SHALL NEVER appear in command-line arguments,
  environment of subprocesses, `--verbose` output, or error
  messages. mTLS key files SHALL be loaded read-only. The CLI
  SHALL verify server TLS certificates by default; a `--insecure`
  flag exists only for development and prints a persistent stderr
  warning on every call.
- **NFR-3 (Observability):** Emit
  `pychestrate_cli_invocations_total{command,outcome}` and
  `pychestrate_cli_duration_seconds` via the same OTLP exporter
  used by the service (opt-in through config), plus stderr log
  events `cli.invoked`, `cli.succeeded`, `cli.failed`,
  `cli.credentials_refused`. Trace spans `cli.parse`, `cli.auth`,
  `cli.request`, `cli.render`.
- **NFR-4 (Reliability):** Interrupted downloads SHALL resume on
  next invocation. A corrupt credentials file SHALL produce a
  deterministic error with a repair hint, not a stack trace. The
  CLI SHALL degrade gracefully when the server's OpenAPI document
  is newer than the CLI's compiled command tree: unknown operations
  respond "server offers newer API; upgrade the CLI" with exit `7`.

## Out of Scope

- In-process programmatic Python API — the CLI is a process; for
  in-process use, callers should drive `8-rest-api-v1` directly.
- TUI (terminal UI) experiences beyond paging — deferred.
- Shell completion scripts — deferred to post-Phase-10.
- Bundled installer for Windows / macOS / Linux — packaging is
  handled by `10-release-channels`.

## Dependencies

- **Depends on:** `8-rest-api-v1` (command source-of-truth via
  OpenAPI), `1-authentication` (OIDC device flow, bearer, mTLS),
  `E-extension-host`, `E-resource-extensions`.
- **Depended on by:** Operators, CI pipelines, and every extension
  that wants a CLI surface.
- **Extension points exposed:** `resource: CLISubcommandExtension`
  — extensions contribute subcommands under `pyc ext <ext-name>`;
  reference implementations `PycExtExampleSubcommand`. See
  implementation-plan.md Layer 8.
