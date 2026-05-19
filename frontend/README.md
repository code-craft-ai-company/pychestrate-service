# Pychestrate Frontend

TypeScript build chain for the Pychestrate web components, starting
with `<pyc-site-shell>` (the unified site shell from
`specs/9-site-shell`).

## Layout

```
frontend/
  package.json         npm scripts: build, typecheck, test, clean
  tsconfig.json        ES2022, strict mode
  build.mjs            esbuild driver — bundles each entry to ESM
  src/
    pyc-site-shell/    M1: site shell skeleton
      index.ts
      pyc-site-shell.ts
      styles.css
      permissions/
      sidebar/
      routing/
      chrome/
  tests/               node --test runnable unit tests
```

Built artifacts go under:

```
source/site/automojo/pychestrate/webservice/webinterface/static/javascript/dist/
```

That `dist/` directory **is committed to git**. The Python deploy
does not run Node — it ships the prebuilt bundles as static files.
That keeps the production / staging deploy story unchanged (Python +
pip only).

## Install

```bash
cd frontend
npm install
```

Requires Node 20+ (developed against Node 22). `pnpm` works equally
well if you prefer it; the scripts call `node` and `tsc` only, no
package-manager-specific features.

## Build

```bash
npm run build
```

Emits a single ES module per entry plus a sibling `.css` and source
map under the dist directory above. Re-run the build any time you
edit a `.ts` or `.css` source file.

## Type-check

```bash
npm run typecheck
```

Runs `tsc --noEmit`. CI does not currently run this (defer to the
GH Actions billing thaw); please run locally before pushing.

## Test

```bash
npm run test
```

Uses Node's built-in `node --test` runner. No Jest / Mocha; the
runtime is the test runner.

## Policy

- The committed `dist/` artifacts are the deploy contract. If you
  change a `.ts` file, also commit the rebuilt `dist/`.
- No bundler config DSL beyond `build.mjs` — one entry per
  feature, ESM output, source maps on.
- TypeScript strict mode is on. Public exports carry explicit
  types. Use TSDoc on public APIs.
