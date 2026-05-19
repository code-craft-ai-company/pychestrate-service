# Site Shell Performance Benchmarks

`shell-bench.mjs` runs five micro-benchmarks against the built
`pyc-site-shell` bundle, driven by a `jsdom` DOM stub. Targets
mirror NFR-1 of `specs/9-site-shell/requirements.md`:

| Case                          | Target (p95) |
| ----------------------------- | ------------ |
| `shell_tti`                   | < 400 ms     |
| `sidebar_render_100`          | < 50 ms      |
| `permission_refetch`          | < 80 ms      |
| `palette_open`                | < 80 ms      |
| `palette_fanout_5_providers`  | < 250 ms     |

## Running

```
npm run bench
```

Output is a JSON document on stdout. Each case includes `p50_ms`,
`p95_ms`, `samples`, and `meets_target`. The current baseline is
checked in at `baseline.json` so regressions can be detected by
diffing the JSON.

## CI gating

CI gating is deferred -- the project's GitHub Actions billing is
currently suspended. When CI is restored, add a workflow step
that runs `npm run bench`, parses the JSON, and fails when any
`meets_target` is `false`.

## Caveats

The bench runs under `jsdom` on Node, not a real browser. The
absolute numbers are not representative of production latency in
a real browser; they are useful for *regression detection*
against the same harness. Real-browser benchmarking belongs in a
Playwright job once CI billing is restored.
