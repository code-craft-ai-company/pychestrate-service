# 8-cli — Tasks

## Milestones

- **M1 — Skeleton:** `pyc` entry point, parser generated from
  the OpenAPI document, `pyc --version` and `pyc --help`
  operational, credentials file loader with `0600` enforcement,
  `pyc project list` end-to-end over bearer auth.
- **M2 — Core Behavior:** Every core command
  (`user|project|pod|client|run|resource|reservation|artifact|metric`)
  wired to its OpenAPI operation id, OIDC device login,
  profile switching, four output formats, interactive
  confirmations, resumable `pyc artifact download`,
  `CLISubcommandExtension` surface.
- **M3 — Hardening:** Parity build check (REST ↔ CLI), full
  exit-code mapping, opt-in OTLP telemetry, Sphinx docs,
  out-of-tree extension subcommand exercised.

## Tasks

### M1 — Skeleton

- [x] T1.1 — Stand up the `pychestrate-cli` Python package with
      `pyc` entry point in
      `source/site/automojo/pychestrate/cli/entry.py`.
      *(Package rooted at ``automojo.pychestrate.cli`` with
      ``entry`` / ``parser`` / ``credentials`` / ``transport`` /
      ``openapi_cache`` / ``models`` / ``exit_codes`` /
      ``exceptions`` modules. Console-script registration in
      pyproject.toml lands when packaging is updated.)*
- [x] T1.2 — Implement `openapi_cache.load_or_fetch` with
      server-version-aware invalidation.
      *(Cache keyed by SHA-256(server_url) under
      ``~/.pychestrate/cache/openapi/``; refreshes when the
      server's ``info.version`` changes; falls back to last-good
      on transient fetch failure; raises
      ``OpenApiUnavailableError`` only when both cache and fetch
      miss. ``PYC_OPENAPI_CACHE_DIR`` env override for tests.)*
- [x] T1.3 — Implement `parser.build_command_tree` from an OpenAPI
      document; emit `pyc <noun> <verb>` argparse structure.
      *(Convention: ``operationId = "<noun>_<verb>"``; missing /
      malformed ids skipped (M3 parity check fails the build on
      gaps). ``build_argparse_for_tree`` lifts the tree into a
      live argparse parser; ``lookup_command`` resolves
      ``(noun, verb)`` pairs.)*
- [x] T1.4 — Implement `credentials.load_profile` with `0600`
      enforcement and `--profile` / `PYC_PROFILE` precedence.
      *(``configparser``-based INI loader; refuses any group/other
      bit set; ``PYC_CREDENTIALS_PATH`` env override for tests;
      ``store_token`` writes through with mode 0600 preserved.)*
- [x] T1.5 — Implement `transport.execute_request` with mTLS and
      bearer-token auth modes.
      *(Stdlib ``urllib.request`` opener; bearer header attached
      from profile; ``ssl.SSLContext`` honors ``verify_tls`` and
      loads mTLS keypair; status >= 400 reclassified into the
      documented exception types.)*
- [x] T1.6 — Wire `pyc --version`, `pyc --help`,
      `pyc <noun> --help`, `pyc <noun> <verb> --help` — all
      offline, no network.
      *(``_select_meta_handler`` dispatches all four meta paths
      before any credentials / network code runs.)*
- [x] T1.7 — Implement `pyc project list` (end-to-end) as the
      reference path; assert matches
      `GET /api/v1/projects`.
      *(End-to-end flow: load profile → load_or_fetch OpenAPI →
      build command tree → resolve project_list operation
      (synthetic fallback to ``/api/v1/projects`` when missing)
      → execute_request → emit JSON to stdout. Test seams for
      profile loader, openapi fetcher, and request opener so the
      flow is testable without a live server.)*

### M2 — Core Behavior

- [ ] T2.1 — Implement `pyc login` via OIDC Device Authorization
      Grant against `/api/v1/auth/oidc/device`; write token via
      `credentials.store_token`.
- [ ] T2.2 — Implement `pyc logout` that invalidates the token
      server-side and wipes the profile's token block.
- [ ] T2.3 — Implement `pyc config set` / `get`.
- [ ] T2.4 — Implement every core command for nouns `user`,
      `project`, `pod`, `client`, `run`, `resource`,
      `reservation`, `artifact`, `metric` using the OpenAPI
      operation registry.
- [ ] T2.5 — Implement `renderer.render` for
      `table | json | yaml | tsv`, with TTY-aware default.
- [ ] T2.6 — Implement `--fields` column selector with unknown-
      field rejection (exit `2`).
- [ ] T2.7 — Implement `prompt.confirm` for destructive verbs;
      honor `--yes`.
- [ ] T2.8 — Implement `download.resumable_download` with
      `Range` resume and SHA-256 verification.
- [ ] T2.9 — Declare `CLISubcommandExtension` resource base and
      extend the parser to merge extension subcommands under
      `pyc ext <ext-name>`.
- [ ] T2.10 — Ship the `PycExtExampleSubcommand` reference
      implementation wrapping `ExampleEchoEndpoints`.

### M3 — Hardening

- [ ] T3.1 — Build-time parity check that fails the CLI build if
      any OpenAPI operation id has no CLI command or vice versa.
- [ ] T3.2 — Implement the full exit-code mapping
      (`0|2|3|4|5|6|7|13`).
- [ ] T3.3 — TTY-aware pager for list output > 200 rows; bypass on
      non-TTY.
- [ ] T3.4 — Scrub sensitive query parameters from `--verbose`.
- [ ] T3.5 — Refuse `--insecure` when `CI=true` unless
      `PYC_ALLOW_INSECURE_IN_CI=1`.
- [ ] T3.6 — Opt-in OTLP exporter emitting metrics in NFR-3.
- [ ] T3.7 — stderr log events `cli.invoked`, `cli.succeeded`,
      `cli.failed`, `cli.credentials_refused`,
      `cli.openapi_refreshed`, `cli.download_resumed`,
      `cli.confirmation_prompted`.
- [ ] T3.8 — Add trace spans `cli.parse`, `cli.auth`,
      `cli.request`, `cli.render`, `cli.download`.
- [ ] T3.9 — Sphinx docs for every command path, the
      `CLISubcommandExtension` base, and the credentials file
      format.

## Test Tasks

- [ ] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–5.
- [ ] TT-2 — Hypothesis property tests: Property 1 (`--help`
      totality on all paths), Property 2 (REST ↔ CLI parity),
      Property 3 (output format byte-stability), 1000 cases each.
- [ ] TT-3 — Integration test: spin up a stub server exposing the
      full OpenAPI document; drive every core command; assert
      matching request for each CLI invocation.
- [ ] TT-4 — Extension-point test: load
      `pychestrate-ext-example`'s `PycExtExampleSubcommand` via
      `E-extension-host`, invoke `pyc ext example echo`, assert
      the REST body matches the CLI arguments byte-for-byte.
- [ ] TT-5 — Credentials-permission test: create a mode-`0644`
      credentials file, assert `pyc` refuses with exit `13` and
      a stable stderr string.
- [ ] TT-6 — Resumable-download test: interrupt mid-download, run
      `pyc artifact download` again, assert byte-identical final
      content and matching SHA-256.

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface has `PycExtExampleSubcommand` in-tree
      reference and one test-only override using a different
      `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every
      param, no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for Phase 10 —
      Public Surface & Extensibility Completion in
      specs/implementation-plan.md
