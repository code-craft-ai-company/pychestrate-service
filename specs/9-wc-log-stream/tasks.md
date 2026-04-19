# 9-wc-log-stream — Tasks

## Milestones

- **M1 — Skeleton:** `<pyc-log-stream>` registered, connects via SSE, renders records in a non-virtualised list, themed via tokens.
- **M2 — Core Behavior:** Virtualised scroller, follow-tail mode, backoff reconnect, ANSI parsing, keyboard navigation, search, `since` resume, WebSocket transport.
- **M3 — Hardening:** Property tests, client metrics beacon, buffer trimming, accessibility audit, performance benchmarks, Sphinx authoring docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Scaffold `source/site/automojo/pychestrate/webservice/webinterface/components/pyc-log-stream/` with TypeScript build wiring.
- [ ] T1.2 — Implement `pyc-log-stream.ts::PycLogStream` Custom Element with observed attributes `run-id`, `src`, `since`, `follow-tail`, `buffer-cap`, `level-filter`, `aria-label`.
- [ ] T1.3 — Implement `log-transport.ts` SSE transport against `/api/v1/runs/{run_id}/logs.stream`.
- [ ] T1.4 — Author `styles.css` (multi-line per AGENTS.md) mapping `--pyc-log-stream-*` tokens to base `--pyc-*` tokens.
- [ ] T1.5 — Wire `connectedCallback` / `disconnectedCallback` / `attributeChangedCallback` lifecycle.
- [ ] T1.6 — Emit `pyc-log-stream-opened` / `pyc-log-stream-closed` / `pyc-log-stream-record` CustomEvents (composed, bubbling).
- [ ] T1.7 — Serve bundle at `/ui/components/pyc-log-stream/pyc-log-stream.js` via `0-web-app-host` static dispatcher.

### M2 — Core Behavior

- [ ] T2.1 — Implement `log-ring-buffer.ts` with `buffer-cap` enforcement and `trimToCap` returning dropped count.
- [ ] T2.2 — Implement `virtual-scroller.ts` rendering at most 512 DOM rows; integrate with follow-tail.
- [ ] T2.3 — Implement exponential backoff with jitter in `log-transport.ts`; non-retryable 401/403/404 halt retries.
- [ ] T2.4 — Implement `ansi-parser.ts` producing styled spans; collapse 256-color / true-color sequences into token-backed classes.
- [ ] T2.5 — Implement keyboard handler per `keybindings.ts`: `End`, `Home`, `/`, `n`, `N`, `Esc`, `PgUp`, `PgDn`.
- [ ] T2.6 — Implement `search.ts` substring and opt-in regex search with 100 ms regex watchdog.
- [ ] T2.7 — Support WebSocket transport under `src="ws"` against `/api/v1/runs/{run_id}/logs.ws`.
- [ ] T2.8 — Add `slot="empty"`, `slot="toolbar-left"`, `slot="toolbar-right"`, `slot="footer"`.
- [ ] T2.9 — Render visually-hidden live region for search and reconnect announcements.

### M3 — Hardening

- [ ] T3.1 — Beacon client metrics per design.md Observability using `navigator.sendBeacon` to `/api/v1/ui/metrics`.
- [ ] T3.2 — Benchmark NFR-1: TTI p95 < 180 ms, append p95 < 4 ms, end-to-end latency p95 < 500 ms under 50 records/s.
- [ ] T3.3 — Axe / ARIA audit: `role="log"`, `aria-live="polite"`, focus ring honored; fail CI on violations.
- [ ] T3.4 — Implement `level-filter` attribute that filters render without dropping from the ring buffer.
- [ ] T3.5 — Reflect connection status to `data-pyc-log-stream-status` attribute (`connecting`, `open`, `reconnecting`, `closed`).
- [ ] T3.6 — Tab-backgrounded elements reduce reconnect cadence to 30 s.
- [ ] T3.7 — Sphinx authoring doc: tag contract, attributes, properties, events, slots, tokens, a11y, examples.
- [ ] T3.8 — Reject non-UUID `run-id` and skip malformed record frames with counters incremented.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–4).
- [ ] TT-2 — Property-based tests implementing Property 1 (idempotent re-render under attribute churn), Property 2 (viewport ordering under virtualised scroll), Property 3 (token override resolution) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 5 scenario — mount `<pyc-log-stream>` against a stubbed `/logs.stream`, stream 5000 records, scroll, search, reconnect, trim; assert events in the expected order.
- [ ] TT-4 — Browser E2E (Playwright-style): navigate to a staged run detail page, verify records arrive within 500 ms, `End` toggles follow-tail, `/` focuses search, `n` jumps between matches, dark mode toggles palette without reload.
- [ ] TT-5 — Security test: assert log payload containing `<script>` is rendered as text (not executed) and ANSI escapes render as styled spans, not injected HTML.
- [ ] TT-6 — Resilience test: disconnect / reconnect 50 times over 5 minutes; zero records lost across `since` resumes; counters match expected.
- [ ] TT-7 — Accessibility screen-reader snapshot: match count announcements land in the live region, toolbar controls are labeled.

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
