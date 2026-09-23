.. _13-00-alpha-deployment:

***********************************
Alpha Deployment — Operator Runbook
***********************************

This document captures the end-to-end deployment recipe for the alpha
release of Pychestrate. It assumes a fresh host (Linux), no Pychestrate
state, and a Postgres instance the operator already controls. SQLite is
supported for development and CI but is **not** the alpha
production target.

Audience: site reliability engineers and operators bringing up the
service for the first time. The companion document
:ref:`12-00-consumer-ui-auth-stack` covers the auth-stack background;
the implementation plan in ``specs/implementation-plan.md`` covers the
phased feature plan.


Prerequisites
=============

* Python 3.12+.
* ``poetry`` (the service uses poetry as its package manager).
* A reachable Postgres 14+ instance with credentials for a database the
  service will own outright (Pychestrate runs DDL via alembic).
* Disk-writable paths for the KEK, password pepper, and UI cookie
  secret material (the alpha bootstrap reads these from operator-owned
  files; the in-tree :mod:`secrets_loader` is pluggable for HSM /
  vault sources but the alpha ships with file + env sources only).
* ``gunicorn`` for production fronting (the in-tree
  ``ccai.webworks.wsgi.server.run_server`` is for development).

Bringing the Postgres instance up out-of-band is the operator's
responsibility. The service makes no assumptions about which Postgres
distro / hosted service is in use; ``psycopg2-binary`` is the only
hard requirement on the client side.


Environment-variable contract
=============================

Every runtime knob the service reads is namespaced ``PYCHESTRATE_*``.
A copy-paste-ready template is shipped at ``development/sample.env``;
the canonical authority is
``source/site/ccai/pychestrate/webservice/runtime_bootstrap.py`` --
operators can ``grep PYCHESTRATE_`` against the source tree to confirm
the live contract.

Required
--------

``PYCHESTRATE_DATABASE_URL``
    SQLAlchemy URL for the production database. For Postgres use
    ``postgresql+psycopg://<user>:<password>@<host>:<port>/<db>``.
    Pychestrate owns the DDL; do not point it at a database that
    carries unrelated tables.

``PYCHESTRATE_RUNTIME_ENVIRONMENT``
    One of ``development`` / ``staging`` / ``production`` /
    ``testing``. The bootstrap **refuses** ``AUTO_CREATE_SCHEMA=true``
    when this is ``production`` -- production must use alembic.

``PYCHESTRATE_KEK_SOURCE``
    ``file`` or ``env``. The KEK encrypts at-rest secrets (see
    :mod:`security.auth.local_flow` and :mod:`secrets`). Rotation is
    out-of-band for the alpha.

``PYCHESTRATE_KEK_ID``
    Operator-assigned label for the currently-active KEK. Logged at
    startup so audit / SIEM tooling can correlate.

``PYCHESTRATE_KEK_FILE_PATH`` (when ``KEK_SOURCE=file``)
    Absolute path to a file holding at least 32 bytes of KEK
    material, owned by the service user with mode ``0600`` (or
    ``0400``). The service refuses to start when the file grants any
    permission to its group or to other users; the error names the
    file, the mode it found, and the ``chmod`` that fixes it.

``PYCHESTRATE_KEK_ENV_VAR`` (when ``KEK_SOURCE=env``)
    Name of the env var carrying the KEK material. The runtime
    reads ``os.environ[<that name>]`` -- never the raw env var
    name itself, which keeps the indirection auditable.

Optional (alpha can ship without these; the auth surface degrades
gracefully)
-----------------------------------------------------------------

``PYCHESTRATE_PASSWORD_PEPPER_SOURCE`` / ``_FILE_PATH`` / ``_ENV_VAR``
    Argon2id pepper for password verification. When unset, the
    auth flow returns 503 on every password verify (login is
    disabled). Production deployments should always set this.

``PYCHESTRATE_UI_COOKIE_SECRET_SOURCE`` / ``_FILE_PATH`` / ``_ENV_VAR``
    HMAC key for signing the consumer-UI session cookie. Must be at
    least 32 bytes. When unset, the consumer UI returns 503; the
    REST API continues to serve. Set this for any deployment that
    serves browser traffic.

``PYCHESTRATE_AUTO_CREATE_SCHEMA``
    ``true`` to short-circuit alembic at boot. **Refused in
    production**; intended for ``dev-up`` and CI.


KEK / pepper / cookie-secret provisioning
=========================================

For the alpha, all three are 32-byte random files under a directory
the service user owns 0600. A representative provisioning flow:

.. code-block:: bash

    sudo install -d -m 0750 -o pychestrate /etc/pychestrate/keys
    sudo -u pychestrate openssl rand -out /etc/pychestrate/keys/active.kek 32
    sudo -u pychestrate openssl rand -out /etc/pychestrate/keys/password-pepper 32
    sudo -u pychestrate openssl rand -out /etc/pychestrate/keys/ui-cookie-secret 32
    sudo chmod 0600 /etc/pychestrate/keys/*.kek /etc/pychestrate/keys/password-pepper /etc/pychestrate/keys/ui-cookie-secret

These files survive service restarts. A rotation tool is out of
scope for the alpha; the rotation procedure is "stop the service,
replace the file, increment ``PYCHESTRATE_KEK_ID``, restart". A live
rotation flow (KEK rolling without downtime) is tracked as a
post-alpha enhancement.


Schema setup (alembic)
======================

Alembic is the production schema source of truth. The Makefile wraps
the common operations against ``PYCHESTRATE_DATABASE_URL``:

.. code-block:: bash

    export PYCHESTRATE_DATABASE_URL="postgresql+psycopg://pychestrate:..."
    make db-current     # show the current revision
    make db-history     # show the migration ladder
    make db-upgrade     # apply every migration in order

The alpha ships two migration trees:

* The Phase-1 modern schema
  (``identity_users`` / ``auth_*`` / ``rbac_*`` / ``audit_records`` /
  ``secrets_*`` / ``flags_*`` / ``projects_*`` / ``variables_*``).
* The legacy ``PychestrateModelBase`` schema (``user`` /
  ``password_history`` / ``sessions`` / ``permissions`` /
  ``system_roles`` / ``role_permissions`` / etc.) covered by the
  stopgap migration ``2026_05_06_0514-340748287bde``.

The legacy schema is required while non-auth surfaces
(``routes_users.py``, ``routes_secrets.py``, ``routes_sessions.py``,
``routes_audit.py``, the ``projects/`` blueprint) still query
``core.managers``. The auth + RBAC slice is on the modern schema
exclusively (see :ref:`12-00-consumer-ui-auth-stack`).


Running the service
===================

Development
-----------

``make dev-up`` boots a SQLite-backed local instance with auto-create
schema enabled and in-tree dev secrets. Single binary, single host,
no out-of-band setup. **Not** for production.

Production (gunicorn)
---------------------

The alpha production fronting is gunicorn. The Makefile target
``serve-prod-gunicorn`` invokes the ``build_wsgi_application_for_production``
factory from ``app_pychestrate_main`` -- the same factory the
production-startup smoke test (``test_p13ab``) drives:

.. code-block:: bash

    export PYCHESTRATE_DATABASE_URL="..."
    export PYCHESTRATE_RUNTIME_ENVIRONMENT=production
    export PYCHESTRATE_KEK_SOURCE=file
    export PYCHESTRATE_KEK_ID=prod-2026q2
    export PYCHESTRATE_KEK_FILE_PATH=/etc/pychestrate/keys/active.kek
    export PYCHESTRATE_PASSWORD_PEPPER_SOURCE=file
    export PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH=/etc/pychestrate/keys/password-pepper
    export PYCHESTRATE_UI_COOKIE_SECRET_SOURCE=file
    export PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH=/etc/pychestrate/keys/ui-cookie-secret
    export PYCHESTRATE_AUTO_CREATE_SCHEMA=false

    make db-upgrade
    make serve-prod-gunicorn   # binds 0.0.0.0:8888 by default

Override ``PYCHESTRATE_BIND_HOST`` / ``PYCHESTRATE_BIND_PORT`` /
``PYCHESTRATE_WORKERS`` / ``PYCHESTRATE_THREADS`` for custom
binding and worker count. The exact gunicorn invocation is documented
inline in the Makefile; pin and tune it once the load profile of
the deploy is understood.


Reverse proxy + TLS
===================

The alpha does not terminate TLS in-process; gunicorn binds an HTTP
listener and the operator fronts it with nginx / traefik / a managed
load balancer. Required header pass-through:

* ``X-Forwarded-Proto: https`` -- tells the service the browser used
  HTTPS, so every cookie it sets (the UI session cookie and the
  setup-wizard unlock cookie) carries the ``Secure`` attribute. The
  header is believed only from a trusted proxy: an address listed in
  ``PYCHESTRATE_TRUSTED_PROXY_ADDRESSES`` (comma-separated addresses
  or CIDR networks, ``*`` for any peer). Unset, the list is the
  loopback addresses ``127.0.0.1`` and ``::1``, which covers nginx on
  the same host proxying to ``127.0.0.1:8888`` as below. With
  ``PYCHESTRATE_RUNTIME_ENVIRONMENT=production`` cookies are always
  ``Secure``, whatever the header says; in ``development``,
  ``staging`` and ``testing`` they are ``Secure`` exactly when the
  request arrived over HTTPS, so a plain-HTTP test server keeps a
  working sign-in.
* ``X-Forwarded-For`` -- the modern auth flow's
  ``RequestFingerprint`` derives an IP fingerprint hash from this
  for replay-mitigation.
* ``Host`` -- preserved for ``url_for``-generated absolute URLs.

A representative nginx ``server`` block:

.. code-block:: nginx

    server {
        listen 443 ssl http2;
        server_name pychestrate.example.com;

        ssl_certificate     /etc/pychestrate/tls/fullchain.pem;
        ssl_certificate_key /etc/pychestrate/tls/privkey.pem;

        location / {
            proxy_pass http://127.0.0.1:8888;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_redirect off;
        }
    }


Smoke-testing the deployment
============================

After ``serve-prod-gunicorn`` is up:

.. code-block:: bash

    # Hello-world handler -- proves the app is dispatching.
    curl -fsS http://127.0.0.1:8888/ | head -c 80

    # Login form -- proves the consumer UI templating environment loaded.
    curl -fsS http://127.0.0.1:8888/config/login | grep -F 'name="username"'

    # Anonymous dashboard -- must redirect to /config/login.
    curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' \
        http://127.0.0.1:8888/config

    # REST API health probe (if /api/v1 routes are registered).
    curl -fsS http://127.0.0.1:8888/api/v1/flags | head -c 80

The ``test_p13ab_production_startup_smoke`` test is the harness's
equivalent: it forks a subprocess, runs ``alembic upgrade head``
against a tempfile SQLite DB, drives ``GET /`` against
``build_wsgi_application_for_production()``, and asserts a 2xx
response. Run it on a clean checkout to confirm the production
bootstrap path is intact:

.. code-block:: bash

    poetry run testbase testing run \
        --root source/testroots/ccai \
        --includes=ccai.tests.singlehost.pychestrate.webservice.phase10.test_p13ab_production_startup_smoke_m1 \
        --output=./.output/smoke


Seeding the first admin user
============================

The alpha ships with no built-in admin user. The bootstrap process
is:

1. Stand up the service against a fresh DB (``make db-upgrade``,
   ``make serve-prod-gunicorn``).
2. Seed the first :class:`IdentityUser` +
   :class:`AuthLocalCredentials` row through the REST API
   ``/api/v1/auth/users`` (or directly via a one-shot Python script
   that calls :func:`local_flow.hash_password` and writes the
   row).
3. Bind the in-tree ``"system-admin"`` :class:`RbacRole` to the new
   user via :class:`RbacRoleBinding` (``principal_kind=USER``,
   ``scope_kind=SYSTEM``).
4. The user can now log in via ``POST /config/login`` and the
   adapter's ``check_permission`` will admit them past the
   ``system:resources.manage`` gate.

A first-run admin-bootstrap CLI is tracked as a beta enhancement.
For the alpha, the operator runs the seed step out-of-band.


CI prerequisite — ``CODECRAFTAI_REPO_TOKEN`` secret
================================================

The repo's :file:`pyproject.toml` declares git-source dependencies
on nine private repositories under the ``automationmojo`` org
(``codecraftai-errors``, ``codecraftai-runtime``, ``codecraftai-arcli``,
``codecraftai-credentials``, ``codecraftai-dataprofiles``,
``codecraftai-storage-database``, ``codecraftai-testbase``,
``codecraftai-webworks``, ``pychestrate-core``). GitHub Actions'
default ``GITHUB_TOKEN`` only authorizes against the repo it runs
in, so ``poetry install`` fails on a fresh runner with::

    Failed to clone https://github.com/automationmojo/codecraftai-arcli.git,
    check your git configuration and permissions for this repository.

Setup (one-time, per repo):

1. Create a **fine-grained Personal Access Token** at
   https://github.com/settings/personal-access-tokens.
   - Resource owner: ``automationmojo`` org.
   - Repository access: **All repositories** (or at minimum every
     ``codecraftai-*`` and ``pychestrate-core`` private repo).
   - Permissions → Repository permissions → **Contents: Read-only**.
   - Expiration: pick a rotation cadence the team can sustain
     (90d is reasonable; the workflow fails fast with a clear
     error if the secret is missing).
2. Add the PAT as a repo secret on
   ``automationmojo/pychestrate-service`` named
   ``CODECRAFTAI_REPO_TOKEN``.

The :file:`.github/workflows/test.yml` workflow then injects the
PAT into a global ``url.<base>.insteadOf`` rewrite right before
each ``poetry install`` step::

    git config --global \\
      url."https://x-access-token:${CODECRAFTAI_REPO_TOKEN}@github.com/automationmojo/".insteadOf \\
      "https://github.com/automationmojo/"

so every clone of an ``https://github.com/automationmojo/<repo>``
URL is silently authenticated.

If the secret is unset, the workflow exits with a typed
``::error::`` annotation pointing at this section -- it does
*not* silently skip.

When the alpha graduates and the dependency tree is converted to
published wheels (post-alpha; tracked alongside the legacy-schema
retirement in the limitations section below), this prerequisite
goes away.


Known alpha limitations
=======================

* **Single-host only.** The alpha runs as a single gunicorn
  process tree on one host. The persistence layer is centralized
  (Postgres) but the message bus is the in-process stub from
  :mod:`messaging.event_bus`; multi-host deploys require the
  Phase-2 bus implementation.
* **Legacy schema co-resident with modern.** The ``user`` /
  ``sessions`` / ``permissions`` / ``system_roles`` /
  ``role_permissions`` tables are still produced by alembic and
  consulted by ``routes_users.py`` / ``routes_secrets.py`` /
  ``routes_sessions.py`` / ``routes_audit.py`` /
  ``projects/`` blueprint. Migrating those surfaces off
  ``core.managers`` is post-alpha.
* **No audit retention policy.** The audit subscriber writes
  every captured event to ``audit_records`` indefinitely. Pruning
  / archival is a Phase-2 admin concern.
* **No HA story.** Process restart drops in-flight requests; the
  consumer UI session cookie survives because the
  :class:`AuthSession` row persists, but the in-process bus loses
  any non-yet-captured event between subscriber and downstream.
