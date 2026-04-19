# {feature-id} — Tasks

## Milestones

- **M1 — Skeleton:** <narrowest shippable slice; proves the wiring>
- **M2 — Core Behavior:** <main user value; feature is usable end-to-end>
- **M3 — Hardening:** <edge cases, observability, perf, docs, extension examples>

## Tasks

### M1 — Skeleton

- [ ] T1.1 — <concrete task>
- [ ] T1.2 — <concrete task>
- [ ] T1.3 — <concrete task>

### M2 — Core Behavior

- [ ] T2.1 — <concrete task>
- [ ] T2.2 — <concrete task>
- [ ] T2.3 — <concrete task>

### M3 — Hardening

- [ ] T3.1 — <concrete task>
- [ ] T3.2 — <concrete task>

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md
- [ ] TT-2 — Property-based tests implementing each Property-N in requirements.md
- [ ] TT-3 — Integration test against <specific end-to-end scenario>
- [ ] TT-4 — Extension-point test: an out-of-tree sample extension registers and is exercised

## Definition of Done

- [ ] All EARS requirements have passing acceptance tests
- [ ] Property-based tests pass across 1000+ generated cases each
- [ ] Extension surface (if any) has at least one in-tree reference
      implementation and one test-only override using a different `PRECEDENCE`
- [ ] Metrics / logs / traces emitted per requirements.md NFR-3
- [ ] Sphinx docs generated for public and internal APIs
- [ ] Code conforms to AGENTS.md coding standards (no mutable defaults,
      explicit returns, named parameter passing, type hints on every param,
      no behavior-modifying decorators)
- [ ] No TODO / FIXME left in shipped code
- [ ] Feature listed in the Definition of Done for its owning phase in
      specs/implementation-plan.md
