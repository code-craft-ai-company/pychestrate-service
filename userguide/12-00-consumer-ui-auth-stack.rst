.. _12-00-consumer-ui-auth-stack:

***********************************************
Consumer-UI Auth Stack — Legacy vs Modern Split
***********************************************

Pychestrate currently carries **two parallel authentication stacks**.
Newer code uses one; the consumer-facing web UI uses the other. The
two stacks back onto disjoint database schemas. This document
captures what each stack is, which routes use which, and where the
seams are -- the layout that future contributors should preserve OR
the work needed to converge on a single stack.

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
to webworks across PRs F1..F5 -- but the port preserved every call to
``SecurityManager`` 1:1, so the consumer UI still talks to the
**legacy** stack.


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


Who uses which
==============

**Legacy** (``SecurityManager``) is used by:

* The consumer web UI's login + logout + session-validation handlers
  in ``webinterface.blueprints.config.routes``
  (``handle_login_submit`` / ``handle_logout`` /
  ``_validate_session_via_security_manager``).
* The web UI's permission gating helper
  ``_require_permission_or_redirect`` (calls
  ``SecurityManager.check_permission``).

**Modern** (``local_flow``) is used by:

* The REST API auth route surface under
  ``security.auth.restapi.v1.auth_routes``.
* The Phase-1 bootstrap that loads the password pepper and wires the
  ``password_hasher`` extension.


.. _12-00-production-gap:

The production schema gap
=========================

Alembic targets ``PychestratePhase1Base.metadata`` (see
``alembic/env.py``). It generates migrations only for the modern
stack's tables. The legacy ``user`` / ``password_history`` /
``sessions`` tables that the consumer-UI login flow queries are
**not produced by any migration**.

Therefore, in a production deployment whose schema is alembic-managed:

* ``identity_users`` exists.
* ``user`` does **not** exist (unless an operator created it
  out-of-band).

The consumer UI's first ``POST /config/login`` against such a
deployment will hit ``SecurityManager.authenticate()``, which queries
``User`` (the legacy table). The query raises
``sqlalchemy.exc.OperationalError: no such table: user`` (SQLite) or
``UndefinedTable`` (Postgres). The handler's broad ``except Exception``
swallows the error and the form re-renders 401 with a generic
"Invalid username or password" -- the user can't tell that the
backend has no auth schema at all.

**This is a P0 production correctness bug.** It was discovered while
building the tier-2 e2e tests in PR p13r (#155); the test harness
papers it over by calling ``PychestrateModelBase.metadata.create_all``
on the in-memory SQLite engine, which is not how production runs.


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


Recommendation
==============

Two fix paths exist, in increasing scope:

1. **Stopgap -- include the legacy tables in alembic.** Add the
   ``PychestrateModelBase.metadata`` tree to ``alembic/env.py`` so
   migrations cover ``user`` / ``password_history`` / ``sessions``.
   Production Postgres can then accommodate the legacy auth flow.
   This unblocks login but does NOT address the SQLite-incompatibility
   issues above (which only manifest in tests).

2. **Strategic -- migrate the consumer UI to ``local_flow``.**
   Rewrite ``webinterface.blueprints.config.routes._build_security_manager``
   to return an adapter object whose ``authenticate`` /
   ``validate_token`` / ``check_permission`` methods call
   ``local_flow.verify_local_credentials`` and the modern session /
   RBAC helpers, so the consumer UI uses the same ``identity_users``
   / ``auth_local_credentials`` / ``auth_sessions`` tables as the
   REST API. Eliminates the schema split and obsoletes the
   SQLite-specific patches in the tier-2 e2e harness.

The strategic option is the right long-term direction; the stopgap
is a faster bridge if a production deployment is imminent.

Until one of these lands:

* The consumer UI's login flow is **non-functional** in any
  deployment whose schema came from alembic alone.
* End-to-end tests that exercise the login flow must seed the legacy
  tables themselves (see the ``_ensure_seeded_admin`` helper in
  ``test_p13r_consumer_ui_e2e_authed_m1``).
* New consumer-UI features that need authenticated context should be
  prepared to migrate to the modern stack rather than entrenching
  more callers of the legacy ``SecurityManager``.
