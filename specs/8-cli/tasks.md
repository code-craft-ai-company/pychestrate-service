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

Status as of September 2026. `[x]` done, `[~]` partly done (the note
says what is missing), `[ ]` not started. Paths and names in the notes
are the shipped ones where they differ from `design.md`.

### M1 — Skeleton

- [x] T1.1 — Stand up the `pychestrate-cli` Python package with
      `pyc` entry point in
      `source/site/ccai/pychestrate/cli/entry.py`.
      *(Package rooted at ``ccai.pychestrate.cli``; standard library
      only. The standalone ``pychestrate-cli`` distribution is
      ``packages/pychestrate-cli`` (``pipx install
      ./packages/pychestrate-cli``) with the ``pyc`` console script
      ``ccai.pychestrate.cli.entry:console_main``; its version is
      ``cli/version.py`` ``PYC_VERSION``.)*
- [x] T1.2 — Implement `openapi_cache.load_or_fetch` with
      server-version-aware invalidation.
      *(Cache keyed by SHA-256(server_url) under
      ``$XDG_CACHE_HOME/pychestrate/openapi/`` (not
      ``~/.pychestrate/cache/openapi/``); a command uses it for an hour,
      then fetches again and rewrites it when ``info.version``
      changed; falls back to last-good on a failed fetch; ``--help``
      reads it whatever its age and never fetches.
      ``PYC_OPENAPI_CACHE_DIR`` overrides the location.)*
- [x] T1.3 — Implement `parser.build_command_tree` from an OpenAPI
      document; emit `pyc <noun> <verb>` argparse structure.
      *(Names come from the operation's ``x-cli`` extension, else
      ``cli/command_names.py``, else the first tag (noun) and the
      ``operationId`` without it (verb), with ``read`` /
      ``get-by-<x>`` spelled ``get`` and ``patch`` ``update``; the
      derived name stays an alias. Each command builds its own
      argparse parser: path parameters positional, query parameters
      typed ``--kebab-case`` flags, bodies from ``--data`` /
      ``--from-file`` / ``--set``.)*
- [x] T1.4 — Implement `credentials.load_profile` with `0600`
      enforcement and `--profile` / `PYC_PROFILE` precedence.
      *(``configparser``-based INI loader at
      ``$XDG_CONFIG_HOME/pychestrate/credentials`` (the pre-XDG
      ``~/.pychestrate/credentials`` is still read); refuses any
      group/other bit set; ``PYC_CREDENTIALS_PATH`` overrides the
      location.)*
- [x] T1.5 — Implement `transport.execute_request` with mTLS and
      bearer-token auth modes.
      *(Stdlib ``urllib.request``; the bearer token is a ``pyc_...``
      API token, which ``/api/v1`` accepts; ``ssl.SSLContext`` honors
      ``verify_tls`` and loads an mTLS keypair; redirects are never
      followed; every request carries ``X-Request-Id``; status >= 400
      is reclassified into the documented exception types.)*
- [x] T1.6 — Wire `pyc --version`, `pyc --help`,
      `pyc <noun> --help`, `pyc <noun> <verb> --help` — all
      offline, no network.
      *(Help for API commands is written from the cached document or
      pyc's built-in commands; unknown commands exit 2 with "did you
      mean".)*
- [x] T1.7 — Implement `pyc project list` (end-to-end) as the
      reference path; assert matches
      `GET /api/v1/projects`.
      *(``pyc projects list`` (``project`` accepted) sends
      ``GET /api/v1/projects`` with ``Authorization: Bearer pyc_...``
      and prints the items.)*

### M2 — Core Behavior

- [~] T2.1 — Implement `pyc login` via OIDC Device Authorization
      Grant against `/api/v1/auth/oidc/device`; write token via
      `credentials.store_token`.
      *(``pyc login`` stores an API token the user creates in the web
      UI (prompt without echo, ``--with-token`` on stdin, or
      ``PYC_TOKEN``) after checking it against ``GET /api/v1/me``.
      The device flow is not implemented: the service has no
      ``/api/v1/auth/oidc/device`` endpoint.)*
- [x] T2.2 — Implement `pyc logout` that invalidates the token
      server-side and wipes the profile's token block.
      *(``pyc logout --revoke``; without ``--revoke`` the token is
      only forgotten locally.)*
- [x] T2.3 — Implement `pyc config set` / `get`.
      *(Also ``init``, ``unset``, ``profiles``, ``path``.)*
- [x] T2.4 — Implement every core command for nouns `user`,
      `project`, `pod`, `client`, `run`, `resource`,
      `reservation`, `artifact`, `metric` using the OpenAPI
      operation registry.
      *(Every operation of the served document is a command; nouns
      are the plural REST resources (``users``, ``projects``,
      ``pods``, ``clients``, ``runs``, ``resources``, ``artifacts``,
      ``metrics``; reservations are ``resource-pools``
      ``create-reservation`` / ``list-reservations`` /
      ``release-reservation``).)*
- [x] T2.5 — Implement `renderer.render` for
      `table | json | yaml | tsv`, with TTY-aware default.
      *(Plus ``raw``; lists print as JSON arrays.)*
- [x] T2.6 — Implement `--fields` column selector with unknown-
      field rejection (exit `2`).
- [ ] T2.7 — Implement `prompt.confirm` for destructive verbs;
      honor `--yes`.
- [ ] T2.8 — Implement `download.resumable_download` with
      `Range` resume and SHA-256 verification.
      *(``pyc artifacts get`` prints the entry; there is no resumable
      download.)*
- [x] T2.9 — Declare `CLISubcommandExtension` resource base and
      extend the parser to merge extension subcommands under
      `pyc ext <ext-name>`.
      *(Routes resolve from the server's ``GET /api/v1/ext``
      listing.)*
- [x] T2.10 — Ship the `PycExtExampleSubcommand` reference
      implementation wrapping `ExampleEchoEndpoints`.

### M3 — Hardening

- [x] T3.1 — Build-time parity check that fails the CLI build if
      any OpenAPI operation id has no CLI command or vice versa.
      *(A test, ``test_p27p_pyc_command_names_m3``, against
      ``specs/openapi/pychestrate.yaml``.)*
- [x] T3.2 — Implement the full exit-code mapping
      (`0|2|3|4|5|6|7|13`).
      *(Plus ``8`` unreachable, ``10`` / ``11`` for ``--wait``.)*
- [ ] T3.3 — TTY-aware pager for list output > 200 rows; bypass on
      non-TTY.
- [ ] T3.4 — Scrub sensitive query parameters from `--verbose`.
      *(There is no ``--verbose``.)*
- [ ] T3.5 — Refuse `--insecure` when `CI=true` unless
      `PYC_ALLOW_INSECURE_IN_CI=1`.
      *(There is no ``--insecure``; a profile with
      ``verify_tls = false`` is warned about on every command.)*
- [ ] T3.6 — Opt-in OTLP exporter emitting metrics in NFR-3.
- [ ] T3.7 — stderr log events `cli.invoked`, `cli.succeeded`,
      `cli.failed`, `cli.credentials_refused`,
      `cli.openapi_refreshed`, `cli.download_resumed`,
      `cli.confirmation_prompted`.
- [ ] T3.8 — Add trace spans `cli.parse`, `cli.auth`,
      `cli.request`, `cli.render`, `cli.download`.
- [~] T3.9 — Sphinx docs for every command path, the
      `CLISubcommandExtension` base, and the credentials file
      format.
      *(User guide chapter ``userguide/14-00-pyc-command-line.rst``;
      commands are documented by their generated ``--help``.)*

## Test Tasks

- [~] TT-1 — Unit tests covering every EARS acceptance criterion in
      Requirements 1–5.
      *(``test_p10f``, ``test_p26c``, ``test_p27p``..``test_p27s``;
      the unimplemented criteria above are not covered.)*
- [~] TT-2 — Hypothesis property tests: Property 1 (`--help`
      totality on all paths), Property 2 (REST ↔ CLI parity),
      Property 3 (output format byte-stability), 1000 cases each.
      *(Properties 1 and 2 are checked exhaustively over every
      command of the contract instead of sampled; Hypothesis is not a
      dependency.)*
- [~] TT-3 — Integration test: spin up a stub server exposing the
      full OpenAPI document; drive every core command; assert
      matching request for each CLI invocation.
      *(Every command is built and parsed from the full document;
      requests are driven for representative commands only.)*
- [x] TT-4 — Extension-point test: load
      `pychestrate-ext-example`'s `PycExtExampleSubcommand` via
      `E-extension-host`, invoke `pyc ext example echo`, assert
      the REST body matches the CLI arguments byte-for-byte.
- [x] TT-5 — Credentials-permission test: create a mode-`0644`
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
