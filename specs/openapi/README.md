# Pychestrate OpenAPI Specification

This directory holds the **authoritative** OpenAPI 3.1 specification for the
Pychestrate Service REST surface.

## Files

* `pychestrate.yaml` — the single-file OpenAPI 3.1 document covering every
  `/api/v1/*` endpoint exposed by `pychestrate-service`. Operations that are
  not yet implemented in the codebase are marked with the
  `x-pychestrate-status: planned` extension on the operation; everything
  else reflects the live HTTP surface.

## What this spec is used for

The same YAML file drives three independent consumers:

1. **`automojo-restclient-pychestrate` (generated client, future PR).**
   `automojo-restclient-base`'s `RestClientGenerator` reads this spec and
   emits a typed Python client. Tags become `RestApiGroup` subclasses,
   `operationId`s become snake_case method names, and component schemas
   become `SchemaObject` subclasses with `Field` descriptors. Operations
   that declare pagination via `page` / `per_page` query params plus a
   `Page<T>` response are surfaced through the base
   `automojo.restclient.base.pagedlist.PagedList`.
2. **Server-side route implementations.** Route handlers landing in
   subsequent PRs are expected to conform to the request / response
   schemas declared here. Schema drift between this document and the
   handler implementation is a bug.
3. **Documentation for external integrators.** The `description` fields
   on operations and schemas double as the public reference for tooling
   authors.

## Maintenance policy

**Every PR that adds, removes, or modifies a REST endpoint MUST update
`pychestrate.yaml` in the same PR.** Schema drift is the failure mode
this single-file contract is designed to prevent — the validator gate
below is the enforcement seam.

When a new endpoint lands:

1. Add the operation to `pychestrate.yaml` under the matching tag.
2. Reuse schemas from `components.schemas` aggressively; only introduce
   a new schema when no existing one fits.
3. If the endpoint is meant to roll out alongside the client agent or
   other deferred work, mark it with `x-pychestrate-status: planned`.
4. Run `make openapi-validate` and ensure it passes before pushing.

When an endpoint is removed:

1. Delete the operation and any schemas no longer referenced by any
   operation or other schema.
2. Note the removal in the PR description so the (future) generated
   client release notes can capture the deprecation.

## Validation

```sh
make openapi-validate
```

Runs `openapi-spec-validator` against `specs/openapi/pychestrate.yaml`.
The validator is installed via the `dev` Poetry group; if it is not
present in your active venv:

```sh
poetry install --with dev
```

`openapi-spec-validator` was chosen over `npx swagger-cli` because the
repo's CI already provisions a Python environment for the test suite;
adding a Node dependency would have created a second toolchain. The
JavaScript validator remains a valid local alternative — `npx
@apidevtools/swagger-cli validate specs/openapi/pychestrate.yaml` will
produce equivalent output.

## Code generation (future)

The follow-on PR will land `automojo-restclient-pychestrate` and wire
`RestClientGenerator` against this file. The generator's output goes
into a sibling repo and is regenerated from this spec — no hand-edits
to the generated tree.
