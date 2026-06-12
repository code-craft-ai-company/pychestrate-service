# 6-artifact-browser — Tasks

## Milestones

- **M1 — Skeleton:** Listing endpoint + path safety + generic download renderer wired into `9-run-detail-ui`.
- **M2 — Core Behavior:** Renderer protocol + in-tree renderers (log, image, audio, PCAP, flamegraph, markdown) + signed-URL/proxy fallback + audit.
- **M3 — Hardening:** Property tests, metrics/logs/traces, perf benchmarks, classifier-cache integration, docs.

## Tasks

### M1 — Skeleton

- [ ] T1.1 — Create the `source/site/ccai/pychestrate/webservice/orchestration/test/artifact_browser/` package per design.md Component Breakdown.
- [ ] T1.2 — Implement `path_safety.py::normalize(path, root_key)` rejecting `..`, encoded escapes, and non-descendants.
- [ ] T1.3 — Implement `browser.py::ArtifactBrowser.list` calling `ObjectStore.list` and sorting dirs-first.
- [ ] T1.4 — Register `GET /api/v1/runs/{run_id}/artifacts` REST endpoint.
- [ ] T1.5 — Implement `renderer_protocol.py::ArtifactRendererExtension` base and `GenericDownloadRenderer`.
- [ ] T1.6 — Implement `renderer_registry.py` accessor with `extension.reloaded` rebuild.
- [ ] T1.7 — Register `GET /api/v1/runs/{run_id}/artifacts/{path}:renderer` endpoint returning `RendererChoice`.

### M2 — Core Behavior

- [ ] T2.1 — Implement `ArtifactBrowser.sign_download` with `max_presign_expires_seconds` clamping.
- [ ] T2.2 — Implement `proxy.py` streaming endpoint `/api/v1/runs/{run_id}/artifacts/{path}:proxy`.
- [ ] T2.3 — Wire `ClassifierQuery` against `5-result-ingest-watcher` with a 60 s LRU cache.
- [ ] T2.4 — Ship in-tree renderers under `source/site/ccai/extensions/pychestrate/artifact_renderer/`: `PxLogStreamRenderer`, `PxImageRenderer`, `PxAudioRenderer`, `PxPcapRenderer`, `PxFlamegraphRenderer`, `PxMarkdownRenderer`.
- [ ] T2.5 — Emit `entity.test.artifact.accessed` bus events and `1-audit-log` entries for signs and proxy opens.
- [ ] T2.6 — Enforce RBAC `run.artifacts.view` / `run.artifacts.download` on every route.
- [ ] T2.7 — Implement renderer fallback when bundle fails to load (generic download).

### M3 — Hardening

- [ ] T3.1 — Emit Prometheus metrics and OTel spans per design.md Observability.
- [ ] T3.2 — Benchmark NFR-1: list p99 < 150 ms at 10 000 entries; sign p99 < 50 ms; renderer select p99 < 20 ms; proxy >= 20 MiB/s. Fail CI on regression.
- [ ] T3.3 — Enforce `limit <= 1000` in list; reject with `SemanticError`.
- [ ] T3.4 — Sphinx docs for public REST endpoints, `ArtifactBrowser` internal API, and `ArtifactRendererExtension` authoring guide.
- [ ] T3.5 — Verify multiline errors use `os.linesep.join([...])`.
- [ ] T3.6 — Harden proxy endpoint to emit `Content-Disposition: attachment` and disallow caching across projects.
- [ ] T3.7 — Quarantine extensions that raise non-`ConfigurationError` exceptions from `matches(...)`.

## Test Tasks

- [ ] TT-1 — Unit tests covering each EARS requirement in requirements.md (Requirements 1–3).
- [ ] TT-2 — Property-based tests implementing Property 1 (path normalization safety) and Property 2 (stable lex listing) at 1000 cases each.
- [ ] TT-3 — Integration test: Phase 5 scenario — a testbase run has `artifacts/smoke/logs/run.log`, `diagnostics/core.dmp`, `tc-by-products/pcap/cap.pcap`; UI lists each, picks the correct renderer, downloads via signed URL, proxy fallback works.
- [ ] TT-4 — Extension-point test: ship a test-only `ExampleBinaryRenderer` (`PRECEDENCE = 1`) that matches `content_type == "application/x-example"`; assert its component tag is returned ahead of `GenericDownloadRenderer` for matching files.
- [ ] TT-5 — Path-escape fuzz: 10 000 random path strings; none yield a key outside `<result_root_key>/`.
- [ ] TT-6 — Presign-unsupported fallback test: swap the driver for one returning `UnsupportedOperationError` on `presign_get`; signing requests return proxy URLs with matching TTL.

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
