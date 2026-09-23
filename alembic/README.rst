================================================
Alembic migrations for pychestrate-service
================================================

This directory holds the alembic configuration and migration
versions for the production database schema. The runtime layer
under ``source/site/ccai/pychestrate/webservice/`` declares
its own SQLAlchemy metadata via
``PychestratePhase1Base = declarative_base()`` in
``webservice/persistence/schema.py``; alembic walks that metadata
to detect schema diffs.

The ``env.py`` here side-effect-imports the three phase-bootstrap
modules (``webservice.extensions.bootstrap`` / ``phase2_bootstrap``
/ ``phase3_bootstrap``) so every model module under the webservice
tree loads before alembic walks the diff. Without that, alembic
would only see the tables it could discover transitively.

Operator workflow
=================

All targets run from the repo root via ``make``:

* ``make db-upgrade`` — apply all pending migrations to the
  database pointed at by ``PYCHESTRATE_DATABASE_URL``.
* ``make db-downgrade`` — roll back the most recent migration.
* ``make db-current`` — show the current revision applied.
* ``make db-history`` — show the migration history.
* ``make db-revision-autogen MESSAGE='describe change'`` — diff
  the in-tree models against the database and emit a new
  migration script under ``versions/``. **Always review the
  generated script before committing** — autogen catches
  most-but-not-all schema changes (notably it does not detect
  column type-only changes by default; ``compare_type=True`` in
  ``env.py`` enables that, but server-default and check-constraint
  diffs may still need hand edits).

Conventions
===========

* The migration filename pattern is ``%Y_%m_%d_%H%M-<rev>_<slug>.py``
  (set in ``alembic.ini`` ``file_template``); the leading
  timestamp keeps the directory ordered chronologically when
  multiple revisions accumulate between releases.
* Every migration defines ``downgrade()``, and it reverses the
  schema change. Data repairs that cannot be undone are the
  exception: their ``downgrade()`` is a deliberate no-op whose
  docstring says why. Two revisions are like that today --
  ``e3f4a5b6c7d8`` (repair of the admin RBAC bindings) and
  ``f4a5b6c7d8e9`` (normalizing their UUID storage) -- so a
  downgrade across them leaves the repaired rows in place.
* Schema-only migrations are preferred. Data backfills should
  live in service-layer code or one-off scripts under
  ``development/`` so the migration stays fast and reentrant.

Environment variables
=====================

* ``PYCHESTRATE_DATABASE_URL`` — required. The same env var the
  runtime bootstrap reads, so the migration target and the
  running service stay aligned.

Production vs development
=========================

* **Production** uses alembic exclusively. The runtime bootstrap
  refuses ``PYCHESTRATE_AUTO_CREATE_SCHEMA=true`` when
  ``PYCHESTRATE_RUNTIME_ENVIRONMENT=production``.
* **Development / testing** can use either. ``make dev-up``
  defaults to ``auto_create_schema=true`` for fast rebuild;
  switch to ``make db-upgrade`` against the same SQLite file when
  you want to test the migration path itself.
