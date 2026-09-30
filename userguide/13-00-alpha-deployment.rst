.. _13-00-alpha-deployment:

*****************************************
Deploying Pychestrate -- Operator Runbook
*****************************************

This runbook brings up Pychestrate on one Linux host for a team: the
service under gunicorn, a Postgres database managed by alembic, secret
material in files only the service can read, TLS at an nginx reverse
proxy, and the first administrator through the setup wizard. It ends
with smoke tests; the ``docs`` CI workflow runs the same smoke-test
scripts against a freshly installed service on every change.

**Status:** Pychestrate is a developer preview (see `ROADMAP.md
<../ROADMAP.md>`_); it is not yet supported for production use. The
scripts under ``deployment/`` are the automation the project author uses
for the alpha host (see ``deployment/README.md``); this runbook is the
general procedure they automate.

.. contents:: On this page
   :local:
   :depth: 1


What you will build
===================

.. code-block:: text

    browsers ---HTTPS---> nginx :443 --HTTP--> gunicorn 127.0.0.1:8888 ---> Postgres
                          (TLS; client        (pychestrate-service,
                           certificates        several workers)
                           for pods)

* gunicorn runs the service's production WSGI factory,
  ``app_pychestrate_main:build_wsgi_application_for_production()``, and
  listens on the loopback interface only.
* nginx terminates TLS and forwards to gunicorn. Pods (machines running
  ``pychestrate-client``) present client certificates to it.
* Postgres holds all state. SQLite also works for a small, single-host
  installation; the database URL is the only difference.


Prerequisites
=============

* A Linux host and an account the service runs as (this runbook uses
  ``pychestrate``, with its home directory ``/home/pychestrate``).
* Python 3.12, `Poetry <https://python-poetry.org/>`_ 2.x, ``git``,
  ``make``, ``openssl``, and ``curl``.
* Postgres 14 or newer, with an empty database and a user that owns
  it: the service creates and migrates its own tables. The driver,
  ``psycopg2``, is installed with the service's dependencies.
* nginx (or another reverse proxy that terminates TLS) and a
  certificate for the host name users will open.
* Read access to the private Code Craft AI framework packages: see
  `Get access to the dependencies
  <02-00-getting-started.rst#get-access-to-the-dependencies>`_.


Install the service
===================

As the service account, clone the repository and create its virtual
environment:

.. code-block:: bash

    git clone https://github.com/code-craft-ai-company/pychestrate-service.git
    cd pychestrate-service
    repository-setup/rehome-repository --skip-workspaces
    development/setup-environment

``rehome-repository`` writes ``.env``, whose ``PYTHONPATH`` covers
``source/packages``, ``source/site``, and ``source/testroots``;
``setup-environment`` creates ``.venv`` with Poetry, installs the
dependencies, and makes ``.venv/bin/activate`` load ``.env``. The
service's own code is not installed into ``.venv``, so every command
that runs the service needs that ``PYTHONPATH`` -- activate the
environment with ``source .venv/bin/activate`` first.


Provision the secret material
=============================

The service needs three secrets to start, and three more for pods and
jobs:

===================================  ==========================================  ========================
Secret                               Used for                                    Needed when
===================================  ==========================================  ========================
Key-encryption key (KEK)             Encrypting secrets and credentials at rest  Always
Password pepper                      Mixed into every password hash              Always (sign-in answers
                                                                                 503 without it)
UI cookie secret                     Signing the web interface's session cookie  Always (the web UI
                                                                                 answers 503 without it)
Envelope signing key (Ed25519)       Signing the job envelopes pods verify       Pods run jobs
Enrollment CA (certificate and key)  Signing pod client certificates             Pods enroll
Result presign secret                Signing artifact upload URLs                More than one gunicorn
                                                                                 worker
===================================  ==========================================  ========================

Generate the key files into a directory only the service account can
read:

.. code-block:: bash

    sudo install -d -m 0700 -o pychestrate -g pychestrate /etc/pychestrate/keys
    sudo -u pychestrate sh -c '
        set -e
        cd /etc/pychestrate/keys
        umask 077
        openssl rand -out active.kek 32
        openssl rand -out password-pepper 32
        openssl rand -out ui-cookie-secret 32
        openssl rand -base64 32 > envelope-signing-key
        openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
            -subj "/CN=pychestrate-enrollment-ca" \
            -keyout enrollment-ca.key -out enrollment-ca.crt 2>/dev/null
        cat enrollment-ca.crt enrollment-ca.key > enrollment-ca.pem
        rm enrollment-ca.key
    '

* Every key file must be readable by the service account only (mode
  ``0600`` or ``0400``; ``umask 077`` above gives ``0600``). The service
  **refuses to start** when the KEK file grants any permission to its
  group or to other users; the error names the file, the mode it found,
  and the ``chmod`` that fixes it.
* The envelope signing key is a base64-encoded 32-byte Ed25519 seed.
* The enrollment CA file holds the CA certificate followed by its
  private key. Keep ``enrollment-ca.crt``: nginx needs it to verify pod
  client certificates.
* The result presign secret is a plain string in the configuration
  below; ``openssl rand -hex 32`` makes a good one.
* Rotation is manual: stop the service, replace the file, change the
  matching ``*_ID`` variable below, and start the service. Replacing
  the KEK makes secrets encrypted under the old KEK unreadable.


Configure the service
=====================

The service reads its configuration from ``PYCHESTRATE_*`` environment
variables. Put them in one file, readable only by the service account,
for example ``/etc/pychestrate/pychestrate.env``;
``development/sample.env`` is a starting point.

.. code-block:: bash

    PYCHESTRATE_RUNTIME_ENVIRONMENT=production
    PYCHESTRATE_DATABASE_URL=postgresql+psycopg2://pychestrate:<password>@db.internal:5432/pychestrate
    PYCHESTRATE_AUTO_CREATE_SCHEMA=false

    PYCHESTRATE_KEK_SOURCE=file
    PYCHESTRATE_KEK_ID=kek-2026-09
    PYCHESTRATE_KEK_FILE_PATH=/etc/pychestrate/keys/active.kek
    PYCHESTRATE_PASSWORD_PEPPER_SOURCE=file
    PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH=/etc/pychestrate/keys/password-pepper
    PYCHESTRATE_UI_COOKIE_SECRET_SOURCE=file
    PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH=/etc/pychestrate/keys/ui-cookie-secret

    PYCHESTRATE_ENVELOPE_SIGNING_KEY_SOURCE=file
    PYCHESTRATE_ENVELOPE_SIGNING_KEY_ID=envelope-2026-09
    PYCHESTRATE_ENVELOPE_SIGNING_KEY_FILE_PATH=/etc/pychestrate/keys/envelope-signing-key
    PYCHESTRATE_ENROLLMENT_CA_SOURCE=file
    PYCHESTRATE_ENROLLMENT_CA_ID=enrollment-ca-2026-09
    PYCHESTRATE_ENROLLMENT_CA_FILE_PATH=/etc/pychestrate/keys/enrollment-ca.pem
    PYCHESTRATE_RESULT_PRESIGN_SECRET=<output of: openssl rand -hex 32>

    PYCHESTRATE_BIND_HOST=127.0.0.1
    PYCHESTRATE_BIND_PORT=8888
    PYCHESTRATE_WORKERS=4
    PYCHESTRATE_THREADS=2

    PYTHONUNBUFFERED=1

The variables, by group. The `Environment Variable Reference
<21-00-environment-reference.rst>`_ lists every variable the service
reads, including the ones a production installation does not need:

``PYCHESTRATE_RUNTIME_ENVIRONMENT``
    ``production``, ``staging``, ``testing``, or ``development``;
    unset means ``production``. Production refuses
    ``PYCHESTRATE_AUTO_CREATE_SCHEMA=true`` and test mode, and always
    marks cookies ``Secure``, so it must be served over HTTPS.

``PYCHESTRATE_DATABASE_URL``
    A SQLAlchemy URL. For Postgres:
    ``postgresql+psycopg2://<user>:<password>@<host>:<port>/<database>``
    (the ``postgresql+psycopg://`` form does not work: that driver is
    not installed). For SQLite: ``sqlite:////var/lib/pychestrate/pychestrate.sqlite``.
    Unset, the service uses SQLite in the presence directory.

``PYCHESTRATE_AUTO_CREATE_SCHEMA``
    ``true`` creates missing tables at startup instead of using
    alembic; for development only, and refused in production.

``PYCHESTRATE_KEK_SOURCE``, ``_ID``, ``_FILE_PATH``, ``_ENV_VAR``
    Required. The source is ``file`` (read ``_FILE_PATH``) or ``env``
    (read the variable *named* by ``_ENV_VAR``). ``_ID`` labels the
    active KEK in logs.

``PYCHESTRATE_PASSWORD_PEPPER_SOURCE``, ``_FILE_PATH``, ``_ENV_VAR`` and ``PYCHESTRATE_UI_COOKIE_SECRET_SOURCE``, ``_FILE_PATH``, ``_ENV_VAR``
    Same shape as the KEK. The cookie secret must be at least 32
    bytes.

``PYCHESTRATE_ENVELOPE_SIGNING_KEY_SOURCE``, ``_ID``, ``_FILE_PATH``, ``_ENV_VAR``
    Optional; without it, the service cannot sign job envelopes and its
    signing-key endpoints answer 503. The source ``dev`` generates a
    throwaway key and is only accepted together with
    ``PYCHESTRATE_DEV_MODE=1``.

``PYCHESTRATE_ENROLLMENT_CA_SOURCE``, ``_ID``, ``_FILE_PATH``, ``_ENV_VAR``
    Optional; without it, enrollment-token redemption answers 503, so
    no pod can enroll.

``PYCHESTRATE_RESULT_PRESIGN_SECRET``
    Signs the upload URLs pods use for results and artifacts. Unset,
    each worker process makes up its own, so with more than one worker
    an upload can land on a worker that rejects it.

``PYCHESTRATE_PRESENCE_DIR``
    The service's state directory; it holds the setup wizard's token
    file (and the SQLite database when ``PYCHESTRATE_DATABASE_URL`` is
    unset). Default: ``~/pychestrate`` of the service account.

``PYCHESTRATE_TRUSTED_PROXY_ADDRESSES``
    The reverse proxies whose ``X-Forwarded-Proto`` header the service
    believes, and whose ``X-Client-Cert-CN`` / ``X-Client-Cert-Verify``
    headers identify a pod; see `Put nginx in front`_. Default:
    ``127.0.0.1,::1``.

``PYCHESTRATE_BIND_HOST``, ``PYCHESTRATE_BIND_PORT``, ``PYCHESTRATE_WORKERS``, ``PYCHESTRATE_THREADS``
    Where gunicorn listens and how many worker processes and threads
    it runs. The ``make serve-prod-gunicorn`` default host is
    ``0.0.0.0``; set ``127.0.0.1`` so only nginx can reach it.

``PYTHONUNBUFFERED``
    Not a Pychestrate variable, but set it to ``1``: without it,
    lines the service prints at startup (such as the setup token's
    path) sit in a buffer instead of reaching the log.

The remaining variables are for development and tests
(``PYCHESTRATE_DEV_MODE``, ``PYCHESTRATE_SQL_ECHO``, and the
``PYCHESTRATE_TEST_*`` test-mode variables, which inject a known
administrator and are refused in production). ``grep -rn PYCHESTRATE_
source/site`` lists every variable the code reads.


Create the database schema
==========================

As the service account, load the configuration into your shell and
apply the migrations:

.. code-block:: bash

    cd ~/pychestrate-service
    set -a; . /etc/pychestrate/pychestrate.env; set +a
    make db-upgrade
    make db-current

``make db-upgrade`` runs ``alembic upgrade head`` against
``PYCHESTRATE_DATABASE_URL``; run it again after every upgrade.
``make db-current`` prints the revision the database is at, and
``make db-history`` the whole migration chain. The schema holds the
modern tables (``identity_users``, ``auth_*``, ``rbac_*``,
``audit_records``, ...) and the legacy ``PychestrateModelBase`` tables
(``user``, ``sessions``, ...) that some web pages still use; both come
from the same migration chain.


Start the service
=================

In the same shell, with the configuration loaded as above:

.. code-block:: bash

    source .venv/bin/activate
    make serve-prod-gunicorn

The log shows gunicorn's ``Listening at: http://127.0.0.1:8888`` and,
once per worker, where the setup token is (``Initial-admin token path:
/home/pychestrate/pychestrate/initial-admin-token`` with the default
presence directory). Stop it with Ctrl+C.

To keep the service running, let a process supervisor start the same
command. A systemd unit, as a starting point:

.. code-block:: ini

    [Unit]
    Description=Pychestrate
    After=network-online.target
    Wants=network-online.target

    [Service]
    User=pychestrate
    Group=pychestrate
    WorkingDirectory=/home/pychestrate/pychestrate-service
    EnvironmentFile=/etc/pychestrate/pychestrate.env
    Environment=PYTHONPATH=/home/pychestrate/pychestrate-service/source/packages:/home/pychestrate/pychestrate-service/source/site
    ExecStart=/home/pychestrate/pychestrate-service/.venv/bin/gunicorn app_pychestrate_main:build_wsgi_application_for_production() --chdir source/site --bind 127.0.0.1:8888 --workers 4 --threads 2
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target

``deployment/pychestrate.service.template`` is the author's alpha unit;
it runs ``development/run-staging-gunicorn`` in the ``staging``
environment with generated development secrets, so do not use it as is
for a team.


Put nginx in front
==================

gunicorn serves plain HTTP on the loopback interface; nginx terminates
TLS and forwards to it. It must pass three headers:

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
* ``X-Forwarded-For`` -- the sign-in flow records it as the client
  address for rate limiting and session fingerprints.
* ``Host`` -- preserved for the absolute URLs the service builds.

A minimal ``server`` block:

.. code-block:: nginx

    server {
        listen 443 ssl http2;
        server_name pychestrate.example.com;

        ssl_certificate     /etc/pychestrate/tls/fullchain.pem;
        ssl_certificate_key /etc/pychestrate/tls/privkey.pem;

        client_max_body_size 50M;

        location / {
            proxy_pass http://127.0.0.1:8888;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_redirect off;
        }
    }

Pods authenticate to the orchestration endpoints with client
certificates signed by the enrollment CA, which nginx verifies
(``ssl_client_certificate`` pointing at ``enrollment-ca.crt``,
``ssl_verify_client optional``). nginx passes the verified identity on
in two headers that every ``location`` proxying to the service must
set: ``X-Client-Cert-CN`` (the certificate's common name, which is the
pod's client id) and ``X-Client-Cert-Verify`` (``$ssl_client_verify``).
The service believes them only from a trusted proxy, like
``X-Forwarded-Proto``. The nginx configuration that
``deployment/deploy-alpha-to-host.sh`` generates
(``deployment/pychestrate.nginx.conf.template``) is the reference for
that part of the setup.

The machines themselves are set up from the client's own guide, ``userguide/01-00-quickstart.rst`` in the
``pychestrate-client`` repository: installing the client, enrolling it with a token from **Admin**,
**Enrollment Tokens**, running it as a service, and upgrading it.


Create the first administrator
==============================

A new deployment has no accounts. At first start the service writes a
one-time token to ``<presence directory>/initial-admin-token`` (mode
``0600``) and logs its path; until the first administrator exists,
every request except ``/setup/*``, ``/static/*``, and
``/favicon.ico`` is redirected to ``/setup/unlock``.

#. Open ``https://pychestrate.example.com/``; you land on **Unlock
   Pychestrate**.
#. On the host, print the token: ``cat
   /home/pychestrate/pychestrate/initial-admin-token``. Paste it and
   choose **Continue**.
#. Enter the administrator's username, email, display name, and a
   password of at least 12 characters, twice. Choose **Create
   administrator**.

The wizard then lands on the sign-in page (``/login``), deletes the
token file, and disappears for good (``/setup/unlock`` answers 404).
Sign in, and create the other accounts under **Admin**, **Users**.

To create the administrator without a browser -- from a provisioning
script, for example -- post the same two forms. Set ``ADMIN_USER``,
``ADMIN_EMAIL``, and ``ADMIN_PASSWORD``, and run:

.. code-block:: bash
   :name: setup-wizard-headless

    #!/usr/bin/env bash
    # Complete the setup wizard without a browser.
    set -euo pipefail
    BASE="${BASE:-http://127.0.0.1:8888}"
    TOKEN_FILE="${TOKEN_FILE:-$HOME/pychestrate/initial-admin-token}"
    : "${ADMIN_USER:?}" "${ADMIN_EMAIL:?}" "${ADMIN_PASSWORD:?}"
    jar="$(mktemp)"
    trap 'rm -f "$jar"' EXIT

    # Unlock: the token earns a short-lived cookie scoped to /setup.
    curl -fsS -c "$jar" -o /dev/null \
        --data-urlencode "token=$(cat "$TOKEN_FILE")" "$BASE/setup/unlock"

    # Create the administrator; success redirects to /login.
    test "$(curl -sS -b "$jar" -o /dev/null -w '%{http_code} %{redirect_url}' \
        --data-urlencode "login_name=$ADMIN_USER" \
        --data-urlencode "email=$ADMIN_EMAIL" \
        --data-urlencode "display_name=$ADMIN_USER" \
        --data-urlencode "password=$ADMIN_PASSWORD" \
        --data-urlencode "password_confirm=$ADMIN_PASSWORD" \
        "$BASE/setup/admin")" = "303 $BASE/login"

    echo "administrator $ADMIN_USER created"


Smoke-test the deployment
=========================

Two scripts check a deployment from the host. Run them with ``bash``;
each stops at the first failed check and prints a success line when
every check passes. Set ``BASE`` to test through nginx instead of
directly (for example ``BASE=https://pychestrate.example.com``).

Right after the first start, before the setup wizard is finished:

.. code-block:: bash
   :name: smoke-before-setup

    #!/usr/bin/env bash
    # Smoke test for a new deployment, before the setup wizard is done.
    set -euo pipefail
    BASE="${BASE:-http://127.0.0.1:8888}"

    # Every page sends visitors to the setup wizard.
    test "$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' "$BASE/")" = \
        "302 $BASE/setup/unlock"

    # The wizard's unlock page renders.
    curl -fsS "$BASE/setup/unlock" | grep -F 'name="token"' > /dev/null

    echo "smoke test passed: the setup wizard is waiting"

After the first administrator exists (set ``ADMIN_USER`` and
``ADMIN_PASSWORD`` to that account):

.. code-block:: bash
   :name: smoke-after-setup

    #!/usr/bin/env bash
    # Smoke test for a deployment whose setup wizard is done.
    set -euo pipefail
    BASE="${BASE:-http://127.0.0.1:8888}"
    : "${ADMIN_USER:?}" "${ADMIN_PASSWORD:?}"
    jar="$(mktemp)"
    trap 'rm -f "$jar"' EXIT

    # The sign-in page renders, and anonymous visitors are sent to it.
    curl -fsS "$BASE/login" | grep -F 'name="username"' > /dev/null
    test "$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' "$BASE/")" = \
        "303 $BASE/login?next=%2F"

    # The REST API refuses anonymous callers.
    test "$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/api/v1/system/health")" = "401"

    # Sign in as a browser does: read the form's CSRF token, then post it.
    csrf="$(curl -fsS -c "$jar" -b "$jar" "$BASE/login" |
        sed -n 's/.*name="csrf_token" value="\([^"]*\)".*/\1/p')"
    test "$(curl -sS -c "$jar" -b "$jar" -o /dev/null -w '%{http_code} %{redirect_url}' \
        --data-urlencode "username=$ADMIN_USER" \
        --data-urlencode "password=$ADMIN_PASSWORD" \
        --data-urlencode "csrf_token=$csrf" \
        "$BASE/login")" = "303 $BASE/"

    # Signed in, the system health endpoint reports the subsystems healthy.
    curl -fsS -b "$jar" "$BASE/api/v1/system/health" | grep -F '"status": "ok"' > /dev/null

    echo "smoke test passed: sign-in, the web interface, and the REST API work"

The in-repository equivalent is the production-startup test, which
migrates a throwaway SQLite database, builds the production WSGI
application in a subprocess, and probes it:

.. code-block:: bash

    source .venv/bin/activate
    testbase testing run --root source/testroots/ccai \
        --includes=ccai.tests.singlehost.pychestrate.webservice.phase10.test_p13ab_production_startup_smoke_m1 \
        --output=.output/smoke


Back up and restore
===================

A backup is two files, written under the presence directory
(``~/pychestrate`` unless ``PYCHESTRATE_PRESENCE_DIR`` says otherwise):

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - File
     - Holds
   * - ``backups/<id>.backup.tar.gz`` and its ``.sha256``
     - A consistent snapshot of the database (SQLite's online backup, or
       ``pg_dump`` for PostgreSQL) and every run artifact, with a manifest
       of checksums and row counts.
   * - ``backup-keys/<id>.keys.tar``
     - The keys the database is useless without: the key-encryption key,
       the password pepper, the cookie secret, the job-envelope signing key
       and the enrollment CA.

The archive holds **no key bytes**. Keep the two files in **different
places**, so a copied archive alone cannot decrypt the secrets inside it, and
copy both off the host after every run: a backup that stays on the host is
lost with its disk.

Run the commands from the service checkout, in the same environment as the
service, so they find the same database and keys:

.. code-block:: bash

   python -m ccai.pychestrate.admin backup create --note "before upgrade"
   python -m ccai.pychestrate.admin backup list

A backup is safe to take while the service runs. To take one every night, run
``backup create --keep 14`` from a systemd timer;
``deployment/pychestrate-backup.service.template`` and ``.timer.template``
are the reference, and the alpha deploy installs them. ``--keep 14`` deletes
all but the newest 14 archives.

Check that a backup can be restored, without touching the live system:

.. code-block:: bash

   python -m ccai.pychestrate.admin backup verify \
       ~/pychestrate/backups/<id>.backup.tar.gz \
       --keys ~/pychestrate/backup-keys/<id>.keys.tar

It checks the archive checksum, the manifest, the database (an integrity
check and the recorded row counts), the artifact count, the key
fingerprints, and that the key-encryption key unwraps the stored data keys.
A good backup ends with ``result: restorable``. Do this on a schedule, not
only after an incident.

A restore replaces the database, the artifacts and the key files, so the
service must be **stopped**:

.. code-block:: bash

   sudo systemctl stop pychestrate.service
   python -m ccai.pychestrate.admin backup restore \
       /path/to/<id>.backup.tar.gz --keys /path/to/<id>.keys.tar --yes
   sudo systemctl start pychestrate.service

The restore verifies the backup first and changes nothing if a check fails.
It keeps what it replaces (``pre-restore-<timestamp>`` next to the database,
and ``artifacts.pre-restore-<timestamp>``); delete them when you are
satisfied. Sign in and open a secret afterwards to confirm the keys are right.
On a rebuilt host, deploy first, stop the service, and restore with
``--overwrite-keys`` so the backed-up keys replace the fresh ones. The full
procedure, including PostgreSQL client tools and every location setting, is
in ``deployment/README.md`` ("Backup and restore").


Monitor the service
===================

Two probes need no credentials and reveal nothing but a status word and check
names, so they can sit behind a load balancer or a container orchestrator:

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Endpoint
     - Answers
   * - ``GET /livez``
     - ``200`` with ``{"status": "live"}`` while the process serves HTTP. Use
       it to decide whether to restart the process.
   * - ``GET /readyz`` (also ``/healthz``)
     - ``200`` with ``{"status": "ready"}``, or ``503`` when the database
       does not answer within 3 seconds. Use it to decide whether to send
       traffic.

``GET /metrics`` serves Prometheus text and needs
``Authorization: Bearer <token>``, where the token is the contents of the file
named by ``PYCHESTRATE_METRICS_TOKEN_FILE``. Without it the answer is ``401``.
Among the metrics is ``pychestrate_backup_last_success_timestamp_seconds``:
alert when it is older than about 26 hours, so a backup that silently stopped
does not go unnoticed. Counters and latency histograms are per gunicorn
worker, so sum series across the ``pid`` label.

.. code-block:: yaml

   scrape_configs:
     - job_name: pychestrate
       scheme: https
       authorization:
         credentials_file: /etc/prometheus/pychestrate-metrics-token
       static_configs:
         - targets: ["pychestrate.example.com"]

The service writes ``~/.pychestrate/server.log`` and, if you run the scheduled
backup, ``~/.pychestrate/backup.log``; ``deployment/pychestrate.logrotate.template``
rotates them daily.


Upgrade
=======

#. Read the **Upgrade notes** of every `CHANGELOG.md
   <../CHANGELOG.md>`_ section between your version and the new one.
#. Back up (see `Back up and restore`_): ``backup create --note "before
   upgrade"``, then copy the two files off the host. A copy of the
   database alone is not enough; the keys and artifacts are part of the
   state.
#. Stop the service, update the checkout (``git fetch`` and ``git checkout``
   the new tag), then run ``development/setup-environment`` to install
   changed dependencies.
#. Load the configuration, run ``make db-upgrade``, and start the
   service. Run the smoke test after setup, and confirm ``/readyz`` answers
   ``200``.


CI prerequisite: dependency access
==================================

The CI workflows install the service's dependencies before running
anything, so the runner needs the same access to the private Code
Craft AI packages a person does:

* **Package index** (``pyproject.toml`` declares a
  ``[[tool.poetry.source]]`` named ``codecraftai``): store the index
  username and token as repository secrets and expose them to the
  install step as ``POETRY_HTTP_BASIC_CODECRAFTAI_USERNAME`` and
  ``POETRY_HTTP_BASIC_CODECRAFTAI_PASSWORD``.
* **Git repositories** (``pyproject.toml`` lists ``git = ...``
  dependencies under ``github.com/automationmojo``): the default
  ``GITHUB_TOKEN`` cannot read other private repositories, so the
  workflows in ``.github/workflows/`` read a fine-grained personal
  access token with **Contents: Read-only** on those repositories from
  the ``CODECRAFTAI_REPO_TOKEN`` secret, and install it as a git
  ``url.<base>.insteadOf`` rewrite before ``poetry install``. A missing
  secret fails the job with an ``::error::`` annotation that names it.


Known limitations
=================

* **Single host.** The message bus is in-process, so the service runs
  as one gunicorn process tree on one host; several hosts would need a
  message bus that spans them, which does not exist yet.
* **No high availability.** Restarting the service drops in-flight
  requests; signed-in sessions survive because they are stored in the
  database.
* **Legacy tables.** Some web pages still read the legacy
  ``PychestrateModelBase`` tables, which the migrations keep in step
  with the modern ones.
* **No audit retention.** Audit records are kept indefinitely.
