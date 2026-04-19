# {feature-id} — Requirements

## Introduction

<One paragraph: what the feature is, where it lives in the layered architecture
(see specs/implementation-plan.md), what problem it solves, which phase it
ships in, and which features it sits between. Reference related features by
their {layer}-{name} id.>

## Requirements

### Requirement 1: <short title>

**User Story:** As a <role>, I want <capability>, so that <benefit>.

**Acceptance Criteria (EARS):**

1. WHEN <trigger event> THEN the system SHALL <observable response>.
2. IF <condition> THEN the system SHALL <observable response>.
3. WHILE <state> the system SHALL <observable response>.
4. WHERE <optional capability present> the system SHALL <observable response>.

### Requirement 2: <short title>

**User Story:** As a <role>, I want <capability>, so that <benefit>.

**Acceptance Criteria (EARS):**

1. WHEN ... THEN the system SHALL ...
2. IF ... THEN the system SHALL ...

### Requirement 3: <short title>

... (minimum 3 requirements per feature; add more when warranted)

## Property-Based Test Requirements

### Property 1: <invariant name>

- **Invariant:** For any <input domain>, <operation> preserves <property>.
- **Generator:** <hypothesis strategy or equivalent — how test inputs are synthesized>
- **Assertion:** <what must hold across all generated inputs>
- **Sample size:** 1000 generated cases

### Property 2: <invariant name>

... (minimum 2 properties per feature)

## Non-Functional Requirements

- **NFR-1 (Performance):** <latency / throughput target, with a concrete number>
- **NFR-2 (Security):** <auth, authz, secrets handling, input validation>
- **NFR-3 (Observability):** <specific metrics, log events, trace spans that must be emitted>
- **NFR-4 (Reliability):** <failure-mode behavior, degradation, recovery>

## Out of Scope

- <What this feature explicitly does not do; points to downstream features when applicable>

## Dependencies

- **Depends on:** <upstream feature ids>
- **Depended on by:** <downstream feature ids>
- **Extension points exposed:** <factory: X · resource: Y · event: Z — see implementation-plan.md>
