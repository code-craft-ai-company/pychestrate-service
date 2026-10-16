.. _12-00-consumer-ui-auth-stack:

***********************************************
Consumer-UI Auth Stack — Legacy vs Modern Split
***********************************************

Pychestrate originally carried **two parallel authentication stacks**.
As of PR p13aa the consumer-UI auth flow (login / session validation /
logout) was wired to the modern stack via a small adapter, and as of PR
p13ad the same adapter's ``check_permission`` was rewired onto the
modern ``rbac_evaluator`` against the modern ``rbac_*`` tables. The
legacy ``SecurityManager`` is no longer consulted by any consumer-UI
auth or RBAC path; the auth stack split is closed. This document
captures the historical context of the migration and the residual
legacy-schema usage that survives outside the auth/RBAC slice.

Background
==========

The codebase has been migrated in waves. The web UI consumer surface
(``/config`` / ``/resources`` / ``/projects``) was originally a flask
blueprint backed by ``ccai.pychestrate.core.managers.SecurityManager``,
which in turn queried the ``ccai.pychestrate.core.orm`` model classes
(``User``, ``PasswordHistory``, ``Session``, …). All of those models
live on the older ``PychestrateModelBase`` declarative base.

Layer-1 modernization introduced
``ccai.pychestrate.webservice.persistence.schema.PychestratePhase1Base``
as the canonical declarative base for everything new
(``identity_users``, ``identity_groups``, ``auth_local_credentials``,
``rbac_*``, …) and a parallel auth implementation under
``ccai.pychestrate.webservice.security.auth.local_flow`` /
``factories.password_hasher``. The flask consumer UI was then ported
to webworks across PRs F1..F5; the port preserved every call to the
legacy ``SecurityManager`` 1:1.

PR p13aa introduced
``webinterface.blueprints.config.auth_adapter.ConsumerUISecurityAdapter``,
a thin facade that exposes the same four-method interface
(``authenticate`` / ``validate_token`` / ``logout`` /
``check_permission``) the consumer-UI handlers already use. Three of
those methods now wire to the modern stack (``local_flow`` +
``session_service``); ``check_permission`` continues to delegate to
the legacy ``SecurityManager`` until RBAC is migrated separately.


The two stacks at a glance
==========================

+---------------------------+---------------------------------+----------------------------------+
| Concern                   | Legacy stack                    | Modern stack                     |
+===========================+=================================+==================================+
| Manager class             | ``SecurityManager``             | ``local_flow.verify_local_       |
|                           | (``core.managers``)             | credentials`` +                  |
|                           |                                 | ``factories.password_hasher``    |
+---------------------------+---------------------------------+----------------------------------+
| User table                | ``user``                        | ``identity_users``               |
|                           | (``core.orm.User``)             | (``identity.users.models``)      |
+---------------------------+---------------------------------+----------------------------------+
| Password store            | ``password_history``            | ``auth_local_credentials``       |
|                           | (``core.orm.PasswordHistory``)  | (``security.auth.models``)       |
+---------------------------+---------------------------------+----------------------------------+
| Session table             | ``sessions``                    | ``auth_sessions``                |
|                           | (``core.orm.Session``)          | (``security.auth.models``)       |
+---------------------------+---------------------------------+----------------------------------+
| Declarative base          | ``PychestrateModelBase``        | ``PychestratePhase1Base``        |
|                           | (``core.orm``)                  | (``persistence.schema``)         |
+---------------------------+---------------------------------+----------------------------------+
| Hashing                   | ``webworks.security.passwords`` | ``factories.password_hasher``    |
|                           | (stdlib pbkdf2-sha256;          | (default scrypt; pluggable)      |
|                           | wire-compatible with            |                                  |
|                           | ``werkzeug 2.3``)               |                                  |
+---------------------------+---------------------------------+----------------------------------+
| Pluggable via             | (none)                          | ``E-factory-protocols``          |
| extension                 |                                 | (``password_hasher`` /           |
|                           |                                 | ``auth_provider``)               |
+---------------------------+---------------------------------+----------------------------------+


Who uses which (as of PR p13ad)
===============================

**Modern stack** (``local_flow`` + ``session_service`` +
``rbac_evaluator``) is used by:

* The REST API auth route surface under
  ``security.auth.restapi.v1.auth_routes``.
* The consumer-UI's login flow (``handle_login_submit`` -- via
  ``ConsumerUISecurityAdapter.authenticate`` -> ``verify_local_credentials``
  + ``open_session``).
* The consumer-UI's session validation
  (``_validate_session_via_security_manager`` -> adapter ->
  ``resolve_session``).
* The consumer-UI's logout (``handle_logout`` -> adapter ->
  ``close_session``).
* **The consumer-UI's permission gating** -- as of PR p13ad,
  ``_require_permission_or_redirect`` -> adapter ->
  ``rbac_evaluator.check_permission`` against
  ``rbac_role_bindings`` / ``rbac_role_permissions`` /
  ``rbac_roles``. Consumer-UI gates pass canonical
  ``system:<action>`` permission keys (e.g.
  ``"system:resources.manage"``); the catalog they reference is
  produced by the in-tree ``CorePermissionExtension`` /
  ``SystemAdminRole`` packs registered during Phase-1 bootstrap.
* The Phase-1 bootstrap that loads the password pepper, wires the
  ``password_hasher`` extension, and registers the in-tree RBAC
  permission/role packs.

**Legacy stack** (``SecurityManager`` + ``core.orm`` user/sessions/
roles tables) is no longer consulted by any consumer-UI auth or RBAC
path. Other consumer-UI surfaces still call into legacy ``core.managers``
helpers (``routes_users.py`` -> ``UserManager``, ``routes_secrets.py``
-> ``SecretManager``, ``routes_sessions.py`` -> ``SecurityManager``'s
session listing helper, ``routes_audit.py`` -> ``AuditLogger``;
``projects/`` blueprint -> ``ProjectManager`` /
``RepositoryManager`` / ``BuildManager`` / ``TestManager`` /
``ReleaseManager`` / ``InfrastructureManager``); those are tracked as
separate migrations and keep the legacy ``PychestrateModelBase`` schema
in production scope until they retire.


.. _12-00-production-gap:

The production schema gap (closed in PR #160 + p13aa)
=====================================================

Alembic originally targeted ``PychestratePhase1Base.metadata`` only,
so the legacy ``user`` / ``password_history`` / ``sessions`` tables
that the consumer-UI's *legacy* login flow queried were not produced
by any migration. The consumer UI's first
``POST /config/login`` (the sign-in route at the time; it has been
``/login`` since PR #200) against an alembic-managed deployment would
hit ``OperationalError: no such table: user``, the handler's broad
``except Exception`` would swallow it, and the form would re-render
401 with a generic "Invalid username or password".  That was a P0
production correctness bug.

PR #160 (the alembic stopgap) added a second migration that creates
every table on ``PychestrateModelBase.metadata`` so the legacy schema
exists in production deployments.

PR p13aa took the strategic step: the consumer-UI's login flow now
queries ``identity_users`` + ``auth_local_credentials`` +
``auth_sessions`` via ``ConsumerUISecurityAdapter``. Production deployments
get a working login flow against the modern schema regardless of
whether the legacy migration has been applied. The legacy schema is
now only required by ``check_permission`` (RBAC), and the migration
from #160 keeps it covered.


SQLite testing implications
===========================

The legacy stack is also incompatible with SQLite in two specific
ways that the modern stack avoids. The tier-2 e2e harness in
``tests.singlehost.pychestrate.webservice.phase10.test_p13r_*``
patches around them (and the helpers will move to a shared
``phase10/_e2e_harness.py`` in a follow-up):

BigInteger primary-key autoincrement
------------------------------------

``Session.id`` and ``PasswordHistory.id`` are ``BigInteger`` columns
with ``autoincrement=True``. SQLAlchemy emits the DDL as
``BIGINT NOT NULL, PRIMARY KEY (...)``. SQLite only auto-fills
``INTEGER PRIMARY KEY`` columns -- a separate ``PRIMARY KEY (...)``
constraint with the type ``BIGINT`` does not become a rowid alias --
so an ``INSERT`` without an explicit id raises ``IntegrityError:
NOT NULL constraint failed``. The tier-2 harness rewrites the column
type to ``Integer`` and sets the table's
``dialect_options["sqlite"]["autoincrement"] = True`` before
``create_all`` runs.

DateTime tz round-trip
----------------------

``Session.expires_at`` / ``Session.last_activity`` are
``DateTime(timezone=True)`` columns and ``utc_now()`` returns
timezone-aware UTC. Postgres preserves the tzinfo on read-back;
SQLite strips it. Once the row reads back naive,
``SecurityManager.validate_token`` compares ``session.expires_at <
utc_now()`` and raises ``TypeError: can't compare offset-naive and
offset-aware datetimes``, which the handler swallows -- every
authenticated request silently falls back to the unauthenticated
branch. The tier-2 harness monkey-patches ``utc_now`` in
``defaults`` and ``security_manager`` to return naive UTC.

Both bugs have the same root cause: the legacy stack's models were
written for a Postgres-only environment and were never tested against
SQLite. The modern stack's models do work on SQLite (which is why
the unit tests in p13a..p13o all pass without any of these patches).


Status (post p13ad)
===================

The strategic auth-stack split is closed:

1. **Stopgap -- legacy tables in alembic.** Done in PR #160. The
   ``PychestrateModelBase.metadata`` tree is part of the alembic
   target, so ``alembic upgrade head`` produces the legacy
   ``user`` / ``password_history`` / ``sessions`` /
   ``permissions`` / ``system_roles`` / ``role_permissions``
   tables. The migration stays on disk because non-auth surfaces
   (``routes_users.py``, ``routes_secrets.py``,
   ``routes_sessions.py``, ``routes_audit.py``, ``projects/``)
   still query ``core.orm`` and ``core.managers``; their migrations
   are tracked separately.
2. **Strategic -- consumer UI auth flow on ``local_flow``.** Done in
   PR p13aa: ``ConsumerUISecurityAdapter`` wires
   ``authenticate`` / ``validate_token`` / ``logout`` to
   ``security.auth.local_flow`` + ``session_service``.
3. **Strategic -- consumer UI RBAC on ``rbac_evaluator``.** Done in
   PR p13ad: the same adapter's ``check_permission`` was rewired to
   ``rbac_evaluator.check_permission`` against the modern
   ``rbac_role_bindings`` / ``rbac_role_permissions`` /
   ``rbac_roles`` tables. Consumer-UI gates pass canonical
   ``system:<action>`` permission keys; the in-tree
   ``CorePermissionExtension`` ships
   ``system:resources.manage`` and the ``SystemAdminRole`` preset
   grants it.

What's still legacy
-------------------

* **CSRF token storage.** The legacy ``SecurityManager.authenticate``
  stored a per-session CSRF token alongside the session row; the
  modern ``AuthSession`` has no CSRF column. The adapter generates a
  fresh CSRF at ``authenticate`` time and the consumer-UI handlers
  carry it on the cookie session payload (cookie is the source of
  truth). ``validate_token`` returns an empty CSRF; the handler
  preserves the cookie value rather than overwriting.

* **Other consumer-UI managers.** ``routes_users.py``,
  ``routes_secrets.py``, ``routes_sessions.py``, ``routes_audit.py``,
  and the ``projects/`` blueprint still call into legacy
  ``core.managers.*`` modules. Those migrations are tracked outside
  this document; the harness's
  ``patch_legacy_pk_columns_for_sqlite`` +
  ``patch_utc_now_for_sqlite_tz_compat`` shims remain in place while
  legacy ``core.orm`` rows are still consulted by tests, but
  ``check_permission`` no longer requires them.


.. _12-00-legacy-import-audit:

Legacy import surface (audit)
=============================

A targeted ``grep`` over ``source/site/`` for
``from ccai.pychestrate.core`` produces 306 import lines.
Categorizing them clarifies what is genuine legacy debt versus
shared utility, and scopes the remaining migration work for
post-alpha planning.

Tier A — shared utilities (not legacy debt)
-------------------------------------------

**225 import lines across 167 files.** These reference
``ccai.pychestrate.core.defaults`` (date/uuid helpers
``utc_now`` / ``new_uuid``) and
``ccai.pychestrate.core.orm.SerializableModel`` (a base
class for SQLAlchemy models, used by both legacy and modern
schemas).

These are not part of the legacy auth/data stack -- they are
infrastructure utilities that happen to live inside the
``core`` package for historical reasons. Modern stack code
(``security/auth/``, ``security/rbac/``, ``identity/``,
``audit/``) imports them too. They do **not** force the legacy
schema to exist.

Future cleanup: relocate them to a non-``core`` namespace so
the package boundary is honest. Tractable as a single PR but
touches ~167 files, so probably best deferred until the rest of
``core`` is gone (point of relocation becomes obvious then).

Tier B — legacy managers (real legacy data path)
-------------------------------------------------

**81 import lines across 21 files.** These reference
``ccai.pychestrate.core.managers.*`` modules:

================================  ================
Manager                           Imports
================================  ================
``resource_manager``                          11
``project_manager``                           11
``watch_manager``                              7
``repository_manager``                         7
``allocation_manager``                         7
``user_manager``                               5
``secret_manager``                             5
``ip_pool_manager``                            5
``build_manager``                              4
``test_manager``                               2
``release_manager``                            2
``health_monitor``                             2
``audit_logger``                               2
``infrastructure_manager``                     2
Subtotal of ``orm`` types
``SystemRole``                                 5
``Permission``                                 2
``AuditEventType``                             2
================================  ================

The 21 consumer files cluster as:

* ``webinterface/blueprints/config/`` -- ``routes_users.py``,
  ``routes_secrets.py``, ``routes_sessions.py``,
  ``routes_audit.py``, ``routes_variables.py``,
  ``routes_scopes.py`` (admin/config surface).
* ``webinterface/blueprints/projects/`` -- ``routes.py``,
  ``routes_builds.py``, ``routes_calendar.py``,
  ``routes_infrastructure.py``, ``routes_releases.py``,
  ``routes_repositories.py``, ``routes_tests.py``,
  ``routes_watches.py`` (project management surface).
* ``webinterface/blueprints/resources/`` -- ``routes.py``,
  ``routes_allocations.py``, ``routes_health.py``,
  ``routes_ip_pools.py``, ``routes_pools.py``,
  ``routes_reservations.py``, ``routes_tags.py`` (resource
  management surface).

Each of these imports a domain-specific manager that wraps a
chunk of the legacy ``core.orm`` schema (``Project``,
``Repository``, ``Resource``, ``Allocation``, ``IPPool``,
``HealthCheckConfig``, ``ProjectVariable``, ``User``,
``SystemRole``, etc.). Migrating them off ``core.managers``
requires a modern-stack equivalent for each manager **and** a
data-layer story for each domain.

Scope assessment: this is **Phase-2/3 territory**, not alpha
cleanup. Each domain (projects, resources, builds, releases,
test-orchestration) is a wave in the implementation plan
(see ``specs/implementation-plan.md``). Migrating the consumer
UI off ``core.managers`` happens incrementally as each layer's
modern services land.

For the alpha, the legacy schema continues to ship via the
``include_legacy_core_orm_tables`` migration (PR #160; PR #175
fixed Postgres FK ordering). The userguide's
``13-00-alpha-deployment.rst`` documents the legacy-schema
co-residency as a known limitation.

Until the modern services for projects / resources / builds /
releases / tests have shipped, attempting to retire any one
``core.managers`` consumer in isolation produces inconsistent
state (e.g., projects on modern data, resources still on legacy
``core.orm.Resource``). The right cadence is to migrate
**per-blueprint** in lockstep with the layer's modern service
landing.

Out of scope for ``check_permission`` retirement
------------------------------------------------

The RBAC migration (PR p13ad / #167) retired
``SecurityManager.check_permission`` from the consumer-UI auth
path -- the adapter now routes RBAC through
``rbac_evaluator``. But ``ProjectManager.check_permission``
(used by ``projects/`` blueprint for project-scoped checks)
still calls into the legacy ``core.managers`` layer. That is a
**different** ``check_permission`` -- a domain-specific check,
not the RBAC top-level gate -- and lives downstream of the
project-data migration above.
