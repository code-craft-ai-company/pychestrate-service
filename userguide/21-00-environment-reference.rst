.. _21-00-environment-reference:

******************************
Environment Variable Reference
******************************

Every environment variable the service reads, with its default and what
it changes. The `deployment runbook <13-00-alpha-deployment.rst>`_ shows
how to set the ones a production installation needs and in what order;
this page is the complete list to look a variable up in.

A test compares this page with the variables the code and the scripts
read, so a variable cannot be added without being described here, and a
variable that is removed cannot stay described.

**Where to set them.** In the systemd unit (``Environment=`` or
``EnvironmentFile=``), or in ``.env`` for a development checkout. Five of
them can also come from the ``settings.config`` file in the presence
directory: the database URL, the artifact root, the backup root, the
backup key directory and the public base URL. For those the environment
wins over the file, and the file wins over the default.

**On/off values.** The variables that switch something on take ``true``,
``yes`` or ``1``; anything else is off. Where this page says
"default: on", the variable turns the behaviour off with ``0``,
``false``, ``no`` or ``off``.


Where the service keeps its state
=================================

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Default
     - What it does
   * - ``PYCHESTRATE_PRESENCE_DIR``
     - ``~/pychestrate``
     - The service's state directory. It holds ``settings.config``, the
       setup wizard's ``initial-admin-token`` file, and the defaults for
       the database, artifacts and backups below. The ``--presence-dir``
       command-line flag wins over this variable.
   * - ``PYCHESTRATE_DATABASE_URL``
     - a SQLite file in the presence directory
     - The SQLAlchemy URL of the database, for example
       ``postgresql+psycopg2://user:password@host:5432/pychestrate``. Use
       PostgreSQL for anything shared; SQLite suits one host.
   * - ``PYCHESTRATE_ARTIFACT_ROOT``
     - ``artifacts`` in the presence directory
     - Where the result files pods upload are stored. Keep it outside
       the code checkout, writable by the service account. Backups
       include it.
   * - ``PYCHESTRATE_BACKUP_ROOT``
     - ``backups`` in the presence directory
     - Where backup archives (database and artifacts) are written.
   * - ``PYCHESTRATE_BACKUP_KEYS_DIR``
     - ``backup-keys`` in the presence directory
     - Where each backup's key bundle (the KEK, password pepper and the
       other keys) is written, apart from the archives so the two can be
       stored in different places.
   * - ``PYCHESTRATE_PG_DUMP_PATH``
     - ``pg_dump`` from ``PATH``
     - The ``pg_dump`` program a backup of a PostgreSQL database runs.
   * - ``PYCHESTRATE_PG_RESTORE_PATH``
     - ``pg_restore`` from ``PATH``
     - The ``pg_restore`` program a restore runs.
   * - ``PYCHESTRATE_AUTO_CREATE_SCHEMA``
     - off
     - Create the missing tables when the service starts. For development
       and tests: the service refuses it when
       ``PYCHESTRATE_RUNTIME_ENVIRONMENT`` is ``production``, so real
       installations use the migrations.
   * - ``PYCHESTRATE_SQL_ECHO``
     - off
     - Log every SQL statement with its parameters. For debugging only;
       the log then holds data.
   * - ``PYCHESTRATE_CONFIG_RESOURCE_SPEC_PATH``,
       ``PYCHESTRATE_CONFIG_LANDSCAPE_PATH``,
       ``PYCHESTRATE_CONFIG_TOPOLOGY_PATH``,
       ``PYCHESTRATE_CONFIG_CREDENTIALS_PATH``
     - the ``config`` directory of the presence directory
     - Where the service reads one of the four documents that are
       written outside it (resource specification, landscape, topology,
       credentials). The variable names a file, or a directory of files,
       and wins over the default location. A path that does not exist
       stops the service at start, so a typo cannot go unnoticed.


Running the server
==================

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Default
     - What it does
   * - ``PYCHESTRATE_RUNTIME_ENVIRONMENT``
     - ``production``
     - ``production``, ``staging``, ``testing`` or ``development``.
       Production refuses ``PYCHESTRATE_AUTO_CREATE_SCHEMA`` and test
       mode, and always marks the session cookie ``Secure``; the other
       three mark it ``Secure`` only for requests that arrived over
       HTTPS, so sign-in keeps working over plain HTTP there. An unset
       value is production, the safer reading.
   * - ``PYCHESTRATE_BIND_HOST``
     - ``127.0.0.1``
     - The address the built-in server and the gunicorn scripts listen
       on. Keep it on the loopback interface when nginx fronts the
       service.
   * - ``PYCHESTRATE_BIND_PORT``
     - ``8888``
     - The port they listen on.
   * - ``PYCHESTRATE_WORKERS``
     - ``1`` for the built-in server, ``4`` for the gunicorn scripts
     - Worker processes. More than one needs
       ``PYCHESTRATE_RESULT_PRESIGN_SECRET``.
   * - ``PYCHESTRATE_THREADS``
     - ``8`` for the built-in server, ``2`` for the gunicorn scripts
     - Threads in each worker. A pod's long poll holds one for up to
       30 seconds, so keep a few spare per worker.
   * - ``PYCHESTRATE_PUBLIC_BASE_URL``
     - empty
     - The scheme and host pods and browsers reach the service at, for
       example ``https://pychestrate.lab.internal``. It is signed into
       job envelopes as the issuer and as the progress and summary URLs.
       Empty makes the issuer host-less and the URLs relative to the
       service, which only works when nothing has to reach back in from
       elsewhere.
   * - ``PYCHESTRATE_TRUSTED_PROXY_ADDRESSES``
     - ``127.0.0.1`` and ``::1``
     - Comma-separated addresses or networks of the reverse proxies the
       service believes about ``X-Forwarded-Proto`` and about a pod's
       client certificate (``X-Client-Cert-CN`` and
       ``X-Client-Cert-Verify``). ``*`` believes those headers from any
       peer, so a client could claim to be a pod; use it only where the
       network already keeps everyone else out. Set it when nginx runs
       on another host.
   * - ``PYCHESTRATE_TEMPLATE_STRICT_UNDEFINED``
     - on
     - A page template that reads a value its handler did not supply
       fails loudly. ``0`` renders the value as blank instead, to keep a
       release running while a template is fixed.


Keys and secrets
================

Each of the five key materials is located the same way. Set the
``_SOURCE`` variable to ``file`` and name the file with ``_FILE_PATH``,
or set it to ``env`` and name, with ``_ENV_VAR``, the *other* variable
that holds the key. The variable holds a name, never the key itself.
``_ID`` is a label you choose for the active key, so a later rotation is
visible in logs and records. The runbook has the commands that create the
keys.

.. list-table::
   :header-rows: 1
   :widths: 30 24 46

   * - Variables
     - Needed
     - What the key is for
   * - ``PYCHESTRATE_KEK_SOURCE``, ``PYCHESTRATE_KEK_ID``,
       ``PYCHESTRATE_KEK_FILE_PATH``, ``PYCHESTRATE_KEK_ENV_VAR``
     - always; source and id are required
     - The key-encryption key. Secrets and credentials are encrypted
       with it at rest, so without it none decrypts.
   * - ``PYCHESTRATE_PASSWORD_PEPPER_SOURCE``,
       ``PYCHESTRATE_PASSWORD_PEPPER_FILE_PATH``,
       ``PYCHESTRATE_PASSWORD_PEPPER_ENV_VAR``
     - always
     - Mixed into every password hash. Without it no password verifies
       and sign-in answers 503. Changing it invalidates every password.
   * - ``PYCHESTRATE_UI_COOKIE_SECRET_SOURCE``,
       ``PYCHESTRATE_UI_COOKIE_SECRET_FILE_PATH``,
       ``PYCHESTRATE_UI_COOKIE_SECRET_ENV_VAR``
     - always
     - Signs the web interface's session cookie. Without it the web
       interface answers 503. A new one signs everyone out.
   * - ``PYCHESTRATE_ENVELOPE_SIGNING_KEY_SOURCE``,
       ``PYCHESTRATE_ENVELOPE_SIGNING_KEY_ID``,
       ``PYCHESTRATE_ENVELOPE_SIGNING_KEY_FILE_PATH``,
       ``PYCHESTRATE_ENVELOPE_SIGNING_KEY_ENV_VAR``
     - when pods run jobs
     - The Ed25519 key that signs job envelopes; pods verify them with
       its public half. The source may also be ``dev``, which generates
       a throwaway key in memory and is honoured only with
       ``PYCHESTRATE_DEV_MODE``.
   * - ``PYCHESTRATE_ENROLLMENT_CA_SOURCE``,
       ``PYCHESTRATE_ENROLLMENT_CA_ID``,
       ``PYCHESTRATE_ENROLLMENT_CA_FILE_PATH``,
       ``PYCHESTRATE_ENROLLMENT_CA_ENV_VAR``
     - when pods enroll
     - The certificate authority that signs each pod's client
       certificate. Until it is set, enrolling a pod answers 503. The
       reverse proxy verifies pods' certificates against its certificate.

Two more secrets are single values:

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Default
     - What it does
   * - ``PYCHESTRATE_RESULT_PRESIGN_SECRET``
     - a random value per worker
     - The secret that signs the URLs pods upload result files to. With
       one worker the default works. With several, each worker would
       invent its own and an upload fails whenever a different worker
       receives it, so set one shared value. The readiness check reports
       it.
   * - ``PYCHESTRATE_EMBED_SIGNING_SECRET``
     - a random value per process
     - The secret that signs the URLs of embeddable views. Unset, a URL
       stops working after a restart and on any other worker.
   * - ``PYCHESTRATE_DEV_MODE``
     - off
     - Lets ``PYCHESTRATE_ENVELOPE_SIGNING_KEY_SOURCE=dev`` use a
       throwaway signing key. Development only: every restart makes a
       new key.


Monitoring
==========

The liveness and readiness probes (``/livez``, ``/readyz``, ``/healthz``)
need nothing. ``/metrics`` shows how the service is running, so it is off
until you choose how to expose it:

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Default
     - What it does
   * - ``PYCHESTRATE_METRICS_TOKEN_FILE``
     - unset
     - A file holding the bearer token scrapers send as
       ``Authorization: Bearer <token>``.
   * - ``PYCHESTRATE_METRICS_TOKEN``
     - unset
     - The token itself. Prefer the file: a value in the environment is
       readable to anything that can read the process's environment.
   * - ``PYCHESTRATE_METRICS_PUBLIC``
     - off
     - Serve ``/metrics`` without a token, for a deployment that
       restricts the path at the proxy or the network.

With none of the three set, ``/metrics`` answers 403 and says how to turn
it on.


Set by the service, not by you
==============================

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Variable
     - What it is
   * - ``PYCHESTRATE_GIT_USERNAME``, ``PYCHESTRATE_GIT_TOKEN``
     - The service puts a repository's credentials in these for the
       ``git`` commands it runs, and its credential helper reads them
       back. They exist only in that child process; setting them in the
       service's own environment does nothing.


Development and tests
=====================

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Variable
     - Default
     - What it does
   * - ``PYCHESTRATE_TEST_MODE``
     - off
     - Seeds a known administrator at start and marks the setup wizard
       complete, so a test suite can sign in. It is a backdoor by design:
       the service refuses it in production, and it must never run on a
       server anyone else can reach.
   * - ``PYCHESTRATE_TEST_ADMIN_LOGIN``
     - ``admin``
     - The seeded administrator's login name.
   * - ``PYCHESTRATE_TEST_ADMIN_PASSWORD``
     - none
     - Its password. Required when test mode is on.
   * - ``PYCHESTRATE_TEST_ADMIN_EMAIL``
     - ``admin@example.com``
     - Its email address.
   * - ``PYCHESTRATE_TEST_ADMIN_DISPLAY_NAME``
     - ``Test Admin``
     - Its display name.
   * - ``PYCHESTRATE_SEED_ADMIN_EMAIL``
     - ``admin@example.com``
     - The email address ``development/seed-test-admin.sh`` gives the
       administrator it creates in an existing database. That script also
       reads ``PYCHESTRATE_TEST_ADMIN_LOGIN`` and
       ``PYCHESTRATE_TEST_ADMIN_PASSWORD``.
   * - ``PYCHESTRATE_TEST_BASE_URL``
     - unset
     - The address of the running server the live-deployment test suites
       (phase 11 and 12) drive. The default is the maintainers' own
       alpha deployment, which you cannot reach, so point it at your own
       server or leave those suites out.
   * - ``PYCHESTRATE_KEK_MATERIAL``,
       ``PYCHESTRATE_UI_COOKIE_SECRET_MATERIAL``
     - none
     - Names used only in ``development/sample.env``, as examples of
       what ``PYCHESTRATE_KEK_ENV_VAR`` and
       ``PYCHESTRATE_UI_COOKIE_SECRET_ENV_VAR`` can point at. The service
       reads no variable of these names by itself.
