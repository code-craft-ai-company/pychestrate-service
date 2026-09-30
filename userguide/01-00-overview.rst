.. _01-00-overview:

********
Overview
********

Pychestrate is a self-hosted service for teams that build, test, and
operate software on real devices and infrastructure. It does three
things:

* **Keeps an inventory of the lab** -- devices, resource pools, IP
  address pools -- and records who has what checked out or reserved,
  so two people or two jobs never use the same device at once.
* **Organizes the work into projects** -- members, repositories, and
  the saved specifications that builds, tests, infrastructure changes,
  and robotic process automation (RPA) run from.
* **Runs jobs on pods**, the machines that do the work, and collects
  their progress, results, and artifacts so a run can be followed live
  and inspected afterwards.

You use it through a web interface, a REST API under ``/api/v1``, and an
MCP (Model Context Protocol) endpoint for AI agents.

**Status:** developer preview. The service is usable for evaluation
and development; it is not yet supported for production use. See
`ROADMAP.md <../ROADMAP.md>`_ for what works and what does not, and
`CHANGELOG.md <../CHANGELOG.md>`_ for what changed.


How the pieces fit
==================

.. code-block:: text

    browser (web UI) --+
    REST API clients --+--> pychestrate-service ----> database
    AI agents (MCP) ---+    (web UI, /api/v1, MCP)    (SQLite or Postgres)
                                     ^
                                     |  mutual TLS: long-poll for jobs,
                                     |  heartbeat, progress, results,
                                     |  artifacts
                                     |
                            pods running pychestrate-client
                                     |
                                     +--> devices and systems under test

* **pychestrate-service** (this repository) is one Python web service:
  the web interface, the REST API, and the orchestrator that decides
  which pod runs a job. It stores its state in SQLite (development) or
  Postgres, managed through alembic migrations.
* **Pods** are machines that run jobs. Each runs the
  pod client (``pychestrate-client``, a separate repository), which enrolls
  once and then *pulls* work: it long-polls the service for jobs,
  sends heartbeats, streams progress, and uploads results. The service
  never connects to a pod, so pods can sit behind a firewall.
* Pods authenticate with **client certificates**. Enrollment exchanges
  a one-time enrollment token for a certificate signed by the
  service's enrollment CA; after that every pod request is mutual TLS,
  terminated by the reverse proxy in front of the service.
* Every job reaches its pod as a **signed envelope** (Ed25519). The
  client verifies the signature against the key the service publishes
  before it runs anything.


Concepts
========

Project
    The unit that organizes work: its members, repositories,
    specifications, the jobs run from them, releases, pipelines,
    watches, and a calendar. Each member holds a project role:
    ``owner``, ``administrator``, ``developer``, or ``viewer``.

Specification
    The saved definition a job runs from: a build specification, an
    infrastructure specification, a test specification, or an RPA
    specification.

Job (run)
    One execution of a specification. The web interface names them by
    domain -- builds, infrastructure jobs, test jobs, RPA jobs -- and
    the orchestration API calls them *runs*. A run is dispatched to a
    pod, reports progress while it executes, and ends succeeded,
    failed, timed out, or cancelled; its results and artifacts stay
    with it.

Pipeline
    A release workflow made of stages that depend on one another.

Watch
    A trigger on repository or build events. Its *conditions* narrow
    when it fires and its *actions* are what it runs.

Release, release channel, release schedule
    A published version, the channel it is promoted through, and the
    schedule that produces it.

Pod and client
    A pod is a machine registered to run jobs; the client is the
    ``pychestrate-client`` program running on it. The orchestrator picks
    an eligible pod for each job, and RPA job types can require pods
    with particular capabilities.

Resource
    Anything in the lab inventory that is used exclusively or in
    limited number: a device, an IP address, a port, a credential, or a
    generic resource. Resources belong to a **resource pool**. Taking a
    resource is a **check-out** (an *allocation*); a **reservation**
    books it for a future window. An **IP pool** is a CIDR range whose
    addresses are checked out one at a time. Each resource has a
    **health** state (``online``, ``degraded``, ``maintenance``,
    ``offline``).

Surface and UI profile
    The interface is split into four *surfaces* -- Build Automation,
    Testing Automation, Robotic Process Automation, and Infrastructure.
    An administrator sets which surfaces the deployment shows, and each
    user can narrow that further. Hiding a surface never changes what
    anyone is allowed to do; see `Choosing What the UI Shows
    <20-00-ui-profiles.rst>`_.

Users, roles, and permissions
    People sign in with local accounts. What they may do is decided by
    permissions named ``system:<area>.<action>`` (for example
    ``system:users.read``), granted through system roles such as
    ``system-admin`` and ``auditor``. Project roles decide what members
    may do inside a project. Security-relevant changes are recorded in
    the audit log. On the role forms (**Admin**, **Roles**) the permissions
    are grouped by product area (*Builds*, *Resource pools*, ...) with a
    filter box; under each area, *View*, *Start*, *Change* and *Administer*
    are the keys ending ``.read``, ``.create``, ``.write`` and ``.admin``, and
    hovering a row shows the key itself.

Secrets and variables
    Credentials and configuration that jobs and integrations use.
    Secrets are encrypted at rest with a key-encryption key (KEK) the
    operator provides; variables are plain configuration values.

Extensions
    Pychestrate's pluggable parts -- password hashers, auth providers,
    resource kinds, and more -- are extension points that installed
    packages can implement. See `Extending Pychestrate
    <11-00-extensions.rst>`_.


Where to go next
================

* `Getting Started <02-00-getting-started.rst>`_ -- run a development
  server on your machine, finish the setup wizard, and create your
  first project.
* `Deploying Pychestrate <13-00-alpha-deployment.rst>`_ -- the operator
  runbook: Postgres, secrets, gunicorn, TLS, the first administrator,
  and smoke tests.
* `RPA Jobs <19-00-rpa-jobs.rst>`_ and `Choosing What the UI Shows
  <20-00-ui-profiles.rst>`_ -- task guides for two parts of the product.
* The REST API is described by the OpenAPI document
  `specs/openapi/pychestrate.yaml <../specs/openapi/pychestrate.yaml>`_.
  A running service shows it as a searchable reference at ``/api/docs``
  (signed in) and serves the document itself at
  ``/api/v1/_meta/openapi.json``.
* `CONTRIBUTING.md <../CONTRIBUTING.md>`_ -- how to change Pychestrate
  and run its tests.
