.. _12-00-consumer-ui-auth-stack:

***********************************************
Consumer-UI Auth Stack — Legacy vs Modern Split
***********************************************

Pychestrate carries **two parallel authentication stacks**.  As of PR
p13aa the consumer-UI auth flow (login / session validation / logout)
is wired to the modern stack via a small adapter; permission checking
(``check_permission``) still routes through the legacy stack. This
document captures what each stack is, which routes use which, and the
remaining work needed to converge on a single stack.

Background
==========

The codebase has been migrated in waves. The web UI consumer surface
(``/config`` / ``/resources`` / ``/projects``) was originally a flask
blueprint backed by ``automojo.pychestrate.core.managers.SecurityManager``,
which in turn queried the ``automojo.pychestrate.core.orm`` model classes
(``User``, ``PasswordHistory``, ``Session``, …). All of those models
live on the older ``PychestrateModelBase`` declarative base.

Layer-1 modernization introduced
``automojo.pychestrate.webservice.persistence.schema.PychestratePhase1Base``
as the canonical declarative base for everything new
(``identity_users``, ``identity_groups``, ``auth_local_credentials``,
``rbac_*``, …) and a parallel auth implementation under
``automojo.pychestrate.webservice.security.auth.local_flow`` /
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
| Hashing                   | ``werkzeug.security``           | ``factories.password_hasher``    |
|                           | (``generate_password_hash``)    | (default scrypt; pluggable)      |
+---------------------------+---------------------------------+----------------------------------+
| Pluggable via             | (none)                          | ``E-factory-protocols``          |
| extension                 |                                 | (``password_hasher`` /           |
|                           |                                 | ``auth_provider``)               |
+---------------------------+---------------------------------+----------------------------------+


Who uses which (as of PR p13aa)
===============================

**Modern stack** (``local_flow`` + ``session_service``) is used by:

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
* The Phase-1 bootstrap that loads the password pepper and wires the
  ``password_hasher`` extension.

**Legacy stack** (``SecurityManager``) is still used by:

* The consumer-UI's permission gating helper
  ``_require_permission_or_redirect``, which calls
  ``ConsumerUISecurityAdapter.check_permission``.  The adapter
  delegates to the legacy ``SecurityManager.check_permission``,
  which walks ``user.roles`` (CSV) -> ``system_roles`` ->
  ``permissions`` (many-to-many).

Migrating RBAC to ``rbac_evaluator`` against the modern
``rbac_*`` tables is the natural next step; once that lands the
legacy schema can be retired entirely.


.. _12-00-production-gap:

The production schema gap (closed in PR #160 + p13aa)
=====================================================

Alembic originally targeted ``PychestratePhase1Base.metadata`` only,
so the legacy ``user`` / ``password_history`` / ``sessions`` tables
that the consumer-UI's *legacy* login flow queried were not produced
by any migration. The consumer UI's first
``POST /config/login`` against an alembic-managed deployment would
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


Status (post p13aa)
===================

The two-step plan called out earlier in this document has now landed:

1. **Stopgap -- legacy tables in alembic.** Done in PR #160. The
   ``PychestrateModelBase.metadata`` tree is now part of the alembic
   target, so a fresh deployment's ``alembic upgrade head`` produces
   the legacy ``user`` / ``password_history`` / ``sessions`` /
   ``permissions`` / ``system_roles`` / ``role_permissions`` tables.
2. **Strategic -- consumer UI on ``local_flow``.** Done in this PR
   (p13aa) for the auth-flow half: ``ConsumerUISecurityAdapter``
   (``webinterface/blueprints/config/auth_adapter.py``) wires
   ``authenticate`` / ``validate_token`` / ``logout`` to the modern
   ``security.auth.local_flow`` + ``session_service`` stack so login,
   session validation, and logout query
   ``identity_users`` + ``auth_local_credentials`` +
   ``auth_sessions`` -- the same tables the REST API uses.

What's still legacy
-------------------

* **Permission checking.** The adapter's ``check_permission``
  delegates to the legacy ``SecurityManager.check_permission``,
  which queries ``user.roles`` -> ``system_roles`` ->
  ``permissions``. Migrating that path to ``rbac_evaluator`` against
  the modern ``rbac_*`` tables is the natural follow-up; once it
  lands the legacy schema can be retired entirely.

* **CSRF token storage.** The legacy ``SecurityManager.authenticate``
  stored a per-session CSRF token alongside the session row; the
  modern ``AuthSession`` has no CSRF column. The adapter generates a
  fresh CSRF at ``authenticate`` time and the consumer-UI handlers
  carry it on the cookie session payload (cookie is the source of
  truth). ``validate_token`` returns an empty CSRF; the handler
  preserves the cookie value rather than overwriting.

* **The harness's SQLite shims** (``patch_legacy_pk_columns_for_sqlite``
  + ``patch_utc_now_for_sqlite_tz_compat``) are still required while
  RBAC keeps the legacy schema in scope for tests. They become dead
  code once RBAC migrates.
