# {feature-id} — Design

## Architecture

<Paragraph explaining where the feature lives in the stack, what modules own
it, and how it interacts with neighbouring features. Reference
implementation-plan.md layer and phase context. Call out the authoritative
source of truth for each piece of state.>

## Data Model

<Entities, key schemas, relationships, table/index sketches. Use concrete field
names and Python-style type annotations (`run_id: UUID`, `state: RunState`,
`started_at: datetime`). Call out primary keys, foreign keys, unique
constraints, and indices.>

## Interfaces

### Public API

<REST routes with path/method/request/response; or CLI commands; or
WebComponent tag + attributes + events. "N/A" if the feature is purely
internal.>

### Internal API

<Python module-level functions and classes. Signatures must follow AGENTS.md
coding standards: snake_case, type hints on every param, explicit return
annotations, no mutable defaults, named parameter passing.>

### Extension Surface

<Factory protocols declared here (name, classmethod signatures) and
`ResourceExtension` base classes. Each entry should describe the contract and
name at least one reference implementation shipped in-tree. "None" if the
feature declares no extension points.>

### Events Emitted

<Message bus topic names and their payload shape (Python dataclass-style).>

### Events Consumed

<Message bus topics this feature subscribes to.>

## Component Breakdown

<Submodule structure — which Python package owns what. Follow the
codecraftai-webworks layout conventions and the repo's existing
`source/site/ccai/pychestrate/webservice/` tree.>

## Key Flows

<Step-by-step walkthrough of the two or three most important use cases,
including which components participate and which events fire.>

## Error Handling

<Failure modes and how each is handled. Reference AGENTS.md exception rules:
- `SemanticError` must never be caught — always bubbles.
- `ConfigurationError` for environment/config issues.
- Catch-and-reclassify to add context; do not catch-and-swallow.
- Multiline error messages built via `os.linesep.join([...])`.>

## Security Considerations

<Auth, authz (which RBAC permissions gate this feature), input validation,
secrets flow, audit-log hooks, rate limiting.>

## Observability

<Concrete names: metrics (`pychestrate_<feature>_<counter>`), log event names,
trace span names. Dashboards or alerts that consume them.>

## Open Questions

<Unresolved design decisions that must be closed before implementation.
Timebox each question to the phase it blocks.>
