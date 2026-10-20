## What and why

<!-- What was wrong or missing, and what this change does about it. -->

## How it was tested

<!-- The testbase modules you ran or added, and anything checked by hand. -->

## Checklist

See [DEVELOPING.md](../DEVELOPING.md#change-checklist).

- [ ] Tests cover the change, and the single-host suite passes.
- [ ] REST changes are in `specs/openapi/pychestrate.yaml`; `make openapi-validate` passes.
- [ ] Model changes come with an alembic migration.
- [ ] **Docs:** the user manual, README, or runbook describe the change where users or operators will notice it, and `sphinx-build -W --keep-going -b html userguide .output/userguide-html` and `python3 docs/tools/check_doc_links.py` pass.
- [ ] `CHANGELOG.md` has an `[Unreleased]` entry (with upgrade notes if anything breaks).
- [ ] No secrets, `.env` files, or build output other than the committed bundle `index.js` files.
