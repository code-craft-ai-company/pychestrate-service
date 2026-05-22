# Pychestrate Frontend

Plain JavaScript web components for the Pychestrate web interface,
starting with `<pyc-site-shell>` (the unified site shell from
`specs/9-site-shell`).

There is **no build step**. The components are authored as plain
ES modules and served directly to the browser. This directory
holds only the test harness; the component source lives in the
served static tree (see Layout).

## Layout

Component source — plain `.js` ES modules, served as-is:

```
source/site/automojo/pychestrate/webservice/webinterface/static/javascript/
  pyc-site-shell/
    index.js
    pyc-site-shell.js
    pyc-site-shell.css
    permissions/
    sidebar/
    routing/
    chrome/
  pyc-admin-bundle/
  pyc-runs-bundle/
  ... (one directory per feature bundle)
```

Each bundle's entry module is `<bundle>/index.js`; the shell
document emits one `<script type="module" src=".../<bundle>/index.js">`
per bundle. The browser resolves the rest of the module graph
natively via relative imports.

Test harness — this directory:

```
frontend/
  package.json         npm scripts: test, bench, a11y
  tests/               node --test runnable unit tests
  bench/               microbenchmarks
  a11y/                axe accessibility audit
```

## Install

```bash
cd frontend
npm install
```

Requires Node 20+ (developed against Node 22). Only the test
harness needs Node — the components themselves run in the browser
with no tooling.

## Test

```bash
npm run test
```

Uses Node's built-in `node --test` runner. No Jest / Mocha; the
runtime is the test runner. Tests import the component modules
directly from the served static tree.

## Policy

- No build step. Edit the `.js` modules in the static tree and
  the change is live — refresh the browser.
- Components are plain ES modules: relative imports, `.js`
  extensions, native `customElements.define`. No bundler, no
  transpiler, no source maps.
