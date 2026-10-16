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
    the audit log. Six roles come ready for the common ways of working:
    **read-only** (see everything that is safe to see, change nothing),
    **tester** (run tests, keep the test catalog, cancel runs), **developer**
    (what a tester does, plus start builds and pipelines, edit pipelines,
    dashboards, alerts and SLOs, run RPA jobs and keep the secrets of the
    projects they belong to), **release-manager** (start builds and pipelines,
    publish releases to channels, keep release templates), **lab-manager**
    (register and change lab devices, manage pools, reservations and
    allocations) and **platform-operator** (manage environments, provisioning,
    drift checks and guards, pods and clients, and the dashboards, alerts and
    webhooks that watch them). Each is *read-only plus what the role does*, so
    a developer can do everything a tester can. None holds an administrative
    permission: users, roles, secret values, sign-in settings, the audit log,
    the Admin menu and restoring backups stay with **system-admin**. A role
    says which features a person may use; which projects they may use them in
    is still decided by project membership. These six are built in: they
    follow the product as it grows and cannot be edited in place. An
    administrator who holds ``system:rbac.admin`` (the **system-admin** role
    has it) manages roles from **Admin**, **Roles**: create a custom role, edit
    or delete a custom role, or **Copy Role** on a built-in one to get a
    version they can change. Giving a role to a person is done from the
    person's page and needs ``system:users.write``. A custom role with the
    same name as a built-in one is never replaced.
    On the role forms (**Admin**, **Roles**) the permissions
    are grouped by product area (*Builds*, *Resource pools*, ...) with a
    filter box; under each area, *View*, *Start*, *Change* and *Administer*
    are the keys ending ``.read``, ``.create``, ``.write`` and ``.admin``, and
    hovering a row shows the key itself. To make a role that is close to an
    existing one, choose **Copy Role** on that role's page (or on its row in
    the list), or pick it under *Start from an existing role* on the create
    form: its permissions come ticked, the copy is named "<name> copy", and
    nothing is saved until you choose **Create Role**. A built-in role cannot
    be edited, so copying it is how to get a version you can change. A menu
    entry shows only for someone who holds *every* permission it needs, so some
    permissions work in pairs: **Users**, **Roles** and the other entries under
    **Admin** also need *Interface, Admin: see in the menu*; **Resources and
    Pools** needs *Resources, View* and *Resource pools, View*; **Dashboards**
    needs *Metrics, View* and *Dashboards, View*. A role with only one half
    gets no entry and no message, so the form says it under each permission
    involved ("In the menu, Users also needs ..."), and above the list a
    **preview** updates as you tick: *Menu entries this role shows* names the
    entries the ticked permissions open, and *Not shown yet* names the ones that
    have part of what they need, each with the permission still missing. A role's
    page lists who has it (name, username, and whether it applies everywhere or in
    one project) for anyone who may view users; others see only the count.
    For an access review, **Download CSV** on the **Roles** page saves every role with its
    type (built-in or custom), how many permissions and people it has and the permission
    keys themselves, and **Download CSV** on the **Users** page saves every user the
    search matches (not one page) as a spreadsheet: username, email, display name,
    whether the account is active, invited or inactive, the roles held everywhere, and
    when it was created (at most 5,000 users; a longer list is cut and the download says
    so in its ``X-Export-Truncated`` header).
    To answer a data-protection request, first **Deactivate** the account (that ends its
    access and can be undone), then choose **Anonymise** on the user's page. It asks for the
    login name to be typed and cannot be undone: the name, email address, password, MFA
    enrolment, sign-in sessions, API tokens, group and project memberships and roles are erased,
    and the account stays in the list as *Anonymised* so the audit log keeps resolving its id
    (it no longer names the person). An account that owns a project cannot be anonymised until the
    project is transferred or deleted; your own account cannot be anonymised. Entries written to
    the audit log *before* the account was anonymised may still contain the person's login name:
    the log is tamper-evident (each entry is chained to the one before), so entries are not edited;
    old ones leave by a retention policy. A notification rule holds the recipient addresses as they
    were typed, so look for the person's address on **Admin**, **Notifications** and remove it.
    The same three actions are in the REST API for a scripted request:
    ``POST /api/v1/identity/users/{id}/deactivate``, ``/reactivate`` and ``/anonymise`` (need
    ``system:users.write``; a refusal is a 409 that says why and changes nothing).

Secrets and variables
    Credentials and configuration that jobs and integrations use.
    Secrets are encrypted at rest with a key-encryption key (KEK) the
    operator provides; variables are plain configuration values. The **Variables**
    page under **Admin** and the REST API's system-scope variables
    (``/api/v1/variables/system//<name>``) are one store: a variable created on the
    page is the one the service and ``/api/v1/variables/effective`` read, one set
    through the API appears on the page, and each change (page or API) is in the
    variable's history. A variable the product owns, such as the interface profile,
    is shown read-only on the page. Secrets live in the vault under **System**,
    **Secrets**: repositories, webhooks and notification channels all use it.
    The older secret store that used to sit under **Admin** (**Secrets (legacy)** and
    **Secret Scopes (legacy)**) has been removed: nothing read it. If you upgrade from a
    release that still has it and it holds live secrets, the upgrade stops before changing
    anything and says how many would be lost. Deploy that release again, choose
    **Import into the vault** on the legacy list (each secret is stored in the vault,
    service-wide, as ``scope/name``), then upgrade. Deleted secrets and empty scopes do
    not stop the upgrade.

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
