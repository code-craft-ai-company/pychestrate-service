.. _18-00-ui-glossary:

=========================
Consumer UI Glossary
=========================

The consumer web UI uses one word for one thing. This page is the
reference the templates, flash messages, and button labels follow;
when a page disagrees with it, the page is wrong.

Verbs
=====

``Create``
    Making a new record of any kind (project, build specification,
    watch, user, role, secret, resource, IP pool, reservation).
    Buttons read ``Create <thing>``; the list page's primary action
    is ``Create <thing>``, never ``New <thing>`` or ``Add <thing>``.

``Add``
    Reserved for attaching an existing thing to another: adding a
    *member* to a project, adding a *tag* to a resource.

``Delete``
    Permanently removing a record. Every Delete confirms first and
    names what goes with it ("Its trigger history is removed with
    it").

``Remove``
    Reserved for detaching without destroying: removing a member from
    a project. Repositories, watches, and specifications are
    *deleted*.

``Run``
    Starting a build, infrastructure, test, or RPA job from its
    specification. ``Test`` is reserved for the watch dry-run and the
    repository connectivity check.

``Check out`` / ``Check in``
    Taking and returning a resource or IP address from a pool for the
    current user. ``Reserve`` is the scheduled, future-dated form of
    check out; ``Release`` is not used.

``Sign in`` / ``Sign out``
    The session verbs on every surface (login page, shell header,
    flash messages). ``Log in`` / ``Logout`` are not used in copy.

Nouns
=====

``Project``
    The organising unit for repositories, specifications, jobs,
    releases, and members.

``Pod`` / ``Client``
    A pod is a machine registered to run jobs. The client is the
    ``pychestrate-client`` program running on it: it enrolls once, then
    pulls work, sends heartbeats and progress, and uploads results. Copy
    says *client* or *pod client*, never *agent*. The word survives only in
    the name ``agent rollout``, an API resource for updating clients, which
    is not usable yet.

``Pychestrate updates``
    Releases of the Pychestrate service and its pod client, published to
    the canary, beta and stable channels that installations follow (Admin,
    **Pychestrate Updates**). A project's own releases and channels are a
    different thing: see ``Release`` / ``Release channel`` below, which
    live under the project.

``Environment``
    A target that builds and provisioning runs act on, registered under
    Orchestration, **Environments** (for example a Kubernetes cluster).
    Not the *environment variables* a build or job runs with (key and value
    settings on its specification), and not the service's *runtime
    environment*, the ``PYCHESTRATE_RUNTIME_ENVIRONMENT`` setting
    (``production``, ``staging``, ``testing`` or ``development``).

``Build specification`` / ``Infrastructure specification`` / ``Test specification``
    The saved definition a job runs from. Abbreviate to ``spec`` only
    inside a table column header where space is short, never in a
    heading or button.

``RPA job type`` / ``Version`` / ``Work packet``
    An RPA job type is a deployment-wide, versioned automation; a
    version is one published release of it; the work packet is the JSON
    document a job processes. ``RPA specification`` and ``RPA job``
    follow the specification / job pattern of the other domains.

``Surface`` / ``UI profile``
    A surface is one automation domain's slice of the interface (Build
    Automation, Testing Automation, Robotic Process Automation,
    Infrastructure). The UI profile is the set of surfaces shown: the
    deployment default set by an administrator, narrowed by a user's
    own preferences. Hiding a surface never removes access.

``Build`` / ``Infrastructure job`` / ``Test job``
    One execution of a specification. Page headings use the full
    noun (``Test Jobs``); breadcrumbs may use the section name
    (``Tests``).

``Pipeline`` / ``Pipeline run``
    A release workflow definition and one execution of it.

``Release`` / ``Release channel`` / ``Release schedule`` / ``Release event``
    A published version, the distribution channel it is promoted to,
    the cron-driven trigger that produces it, and its calendar window.

``Watch``
    A repository or build event trigger that runs actions. Its
    *trigger* is the event source; its *conditions* narrow when it
    fires; its *actions* are what it runs.

``Resource`` / ``Resource pool`` / ``IP pool``
    A checkout-able device or capacity, the grouping it belongs to,
    and a CIDR range whose addresses are checked out individually.

``Allocation`` / ``Reservation``
    An allocation is a current check-out. A reservation is a future-dated
    claim on a resource; it becomes an allocation when it is checked out,
    and is never itself the check-out.

``Member``
    A user with a role on a project (``owner``, ``admin``,
    ``developer``, ``viewer``). Page heading: ``Project Members``.

``Health``
    A resource's operational state: ``online``, ``degraded``,
    ``maintenance``, ``offline``.

Headings and navigation
=======================

* The page heading (``<h1>``) matches the navigation label that leads
  to it: ``Users`` not ``User Management``, ``Variables`` not ``Global
  Variables``, ``Sessions`` not ``Active Sessions``.
* Detail pages are headed by the entity's own name; the section name
  lives in the breadcrumb.
* Secondary actions on a form read ``Cancel`` and return to the list;
  ``Back to <thing>`` is used only on read-only pages.

Status vocabulary and colour
============================

The ``status_badge`` macro maps every status to one tone so the same
value is the same colour on every page:

===========  ===================================================
Tone         Statuses
===========  ===================================================
success      succeeded, passed, completed, published, online,
             enabled, active, healthy, approved, available
danger       failed, error, offline, cancelled, timeout,
             deprecated, rejected, revoked, expired
info         running, in progress, started, provisioning,
             checked out, allocated
warning      pending, queued, scheduled, degraded, draft,
             maintenance, waiting approval, reserved
secondary    skipped, disabled, unknown, inactive, released
===========  ===================================================

Red is reserved for errors and destructive actions; an allocation's
*exclusive* mode is informational and renders with the ``info`` tone.

Dates and identifiers
=====================

* Every timestamp renders through the ``format_datetime`` filter: a
  ``<time>`` element with the ISO value, the visible text in
  ``YYYY-MM-DD HH:MM`` (seconds only on detail pages), and the zone
  spelled out.
* Absent values render as an em dash, never as ``None``, ``N/A``, or
  an empty cell.
* Long identifiers (commit SHAs, checksums, UUIDs) render through
  ``truncate_id``: twelve characters, the full value in the title.
