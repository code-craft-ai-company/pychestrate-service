.. _16-00-running-and-reading-work:

********************************
Running and Reading Work
********************************

This guide is for the person who starts jobs and wants to know what happened
to them: how to start a test run or a build, how to follow it, how to read the
result, and what each state means. It assumes a project exists and at least
one pod is enrolled and running; see `Getting Started
<02-00-getting-started.rst>`_ for the project, and the pod guide in the
``pychestrate-client`` repository (``userguide/01-00-quickstart.rst``) for the
pod. RPA jobs have their own chapter: `RPA Jobs <19-00-rpa-jobs.rst>`_.

Every job is a **run**. The service never runs a job itself: it signs the job
and hands it to a pod, and the pod runs it and reports back. So a run moves
through states as the pod's answers arrive, and a run that no pod can take
waits.


Start a test run
================

Open **Orchestration**, **Test Catalog** and choose the project. The catalog
lists the tests a project can run, one entry per test include.

To add tests, choose **Import from testbase** and fill in the form:

* **Test includes (one per line)**: the names ``testbase testing run
  --includes`` takes, for example ``ccai.tests.singlehost.feature.test_module``.
  Each include becomes one catalog entry.
* **Testbase root on the pod** and **Branch**, optional: where the test roots
  are and which branch to use.
* **Required capability tags**, optional and comma separated: only a pod that
  advertises them is given the run.
* **Importer**, which is ``testbase-project`` unless you have added another.

Choose **Run import**. The entries appear in the table. To run one, choose
**Trigger Run** on its row. A message confirms it and links to **View run**.
A retired entry cannot be run; tick **Include retired** to see them.

The service refuses to start a run that no pod can take, and says so: "No
enrolled pod matches the job's capability requirements -- enroll a client/pod
first." Check that a pod is enrolled in the project, is running (its client
shows *Alive* under **Fleet**, **Clients**), and advertises any capability tags
the entry requires. A pod's tags are the ``capability_tags`` in its client's
``config.json`` (read when the client starts); the client's page under **Fleet**,
**Clients** lists what it advertised. A run that requires a tag no pod advertises
is refused with "No candidate pod satisfies the catalog entry's required
capabilities", naming the tags it needed.


Start a build
=============

Open **Orchestration**, **Builds**, choose the project, and choose **Trigger
Build**:

* **Source integration**: where the source comes from. If the project has
  none, choose "None" and name the source in the runner inputs.
* **Runner kind**, required: ``makefile`` is the usual one.
* **Runner inputs (JSON)**: what the runner needs, for example
  ``{"targets": ["all"]}``.

A build must name its source, one of three ways: a source integration, a
``git_url`` (with an optional ``git_ref``) in the runner inputs, or a
``source_dir`` for a tree already on the pod. A build that names none is
refused when you trigger it, and the message says so, rather than failing later
on the pod.

The build's page shows its steps and lets you retry it. Pipelines, which chain
builds and tests, are under **Orchestration**, **Pipelines**. To start a saved
pipeline, open it and choose **Run**: the dialog says how many stages will start
and from which commit (the one it was saved from), and the page then says the run
started, or why it did not (for example that no enrolled pod in the project
matches), and lists it under **Runs**. Scripts do the same with ``POST
/api/v1/projects/{id}/pipeline-runs`` and ``{"pipeline_id": "<id>"}``.


Follow a run
============

**Orchestration**, **Runs** lists runs newest first. Filter by **State** or by
**Project**, and choose **Refresh** to reload; the page notes when it last did.
The columns are **Job** (what ran: the job's name, which links to the run's
page, and the short id after it for quoting), **Type** (for example *Test ·
testbase* or *Build · makefile*), **Project**, **State**, **Triggered by** (the
user who started a test run or a build; a dash when no user did, for example a
run a pipeline started), **Created** and
**Duration** (how long it ran, or how long so far while it is running; a dash
for a run that has not started). The **Builds** and **Provisioning runs** pages
lead the same way: a build with its runner and target (*makefile · docs*) and
the source it came from (*main @ github.com/acme/widgets*), a provisioning run
with its action and driver (*apply · terraform*). On a narrow screen the table
scrolls sideways as one piece.

**Download CSV**, beside Refresh, saves the whole list as the filters now
show it (not just the page on screen) as a spreadsheet: run id, project, job
name and type, state, outcome, when it was created, started and completed, how
long it ran, the pod, and who triggered it. It holds at most 5,000 runs; a longer list is cut and
the download says so in its ``X-Export-Truncated`` header. Cells that a
spreadsheet could read as a formula are written as text. The same file is
``GET /api/v1/runs?format=csv`` (with the same ``project_id`` and ``state``
filters) for scripts.

A run that has been sent to a pod that is not answering shows that it is
waiting for that pod, and when the pod was last heard from. It starts when the
pod comes back.


Read a run
==========

Open a run from the list. The page shows:

* The run's short id and its **state**, coloured by the outcome.
* Its facts: **Project**, **Pod**, **Job type**, **Job name**, **Triggered by**
  (when a user started it), **Dispatch attempt**, and the times it was **Created**, **Dispatched**, **Started** and
  **Completed**.
* **Terminal outcome** and **Reason**, once the run has ended. The reason says
  why. For a failed test run it is the pod's account, for example "1 of 2 tests
  failed.", and the same text is in the failed-run notification; when the pod
  gave none (a run that passed, or a build) it is "testbase result manifest:
  outcome=success" (or "build result manifest: outcome=failure"). A run that
  overran its hard deadline is ended by the service, and the reason says so:
  "hard deadline ... passed".
* **Progress**: tiles for **Passed**, **Failed**, **Errored**, **Skipped** and
  **Total**, and a bar, updated live while the run is going.
* **Test results**: for a test run that has ended, the totals ("1 failed - 31
  passed") and the tests themselves, failing ones first. A failing test opens to
  show the exception and its message; **Stack** lists the frames with the
  source lines around each. **Show failed tests only** narrows the list, and
  **Show more** loads the next fifty tests. This is what the pod reported for
  each test; a run that failed before any test ran says no individual results
  were recorded. The same list is ``GET /api/v1/runs/{run_id}/results``.
* **Artifacts**: a one-line outcome, for example "Outcome failure - 0 passed -
  1 failed", and every file the run produced, each a link. For a test run
  these include the summary and the full results (``testrun_results.json``),
  and the log (``testrun.log``).

The page says when live updates are interrupted and reconnects, and when the
run has finished and live updates have ended.

A failed run's **Reason** is the first thing to read. If the job never ran at
all, the state is one of the *dispatch* states below, and the fault is between
the service and the pod rather than in the job.


Cancel a run
============

While a run has not finished, its page has **Cancel run**. Choose it and
confirm; the page reports "Cancellation requested." For a run a pod has been
given, the service passes the request to the pod, which stops the job on its
next heartbeat and reports back, and the run moves through *cancel_requested*
and *cancelling* to *cancelled*. If the job happens to finish first, the run
ends *completed* or *failed* instead, as the pod reports it. A system
administrator can cancel any run.

A run that has already finished cannot be cancelled.


See what is broken across your projects
=======================================

Open **Projects**, **Projects Dashboard**. **Needs attention** comes first: the
runs that failed, were lost, could not be sent to a pod or need someone to look
at them in the last seven days, newest first, each a link to the run with its
project. If none did it says so; on a new installation it says there are no runs
yet.

Below it the **Projects** table lists each project with its latest run (the
state, linking to the run, and when). A project that has runs needing attention
shows how many beside its latest run ("2 need attention"), even when its latest
run succeeded, and those projects are listed first. The table shows the first
ten projects by name and says how many there are; a project past the tenth
still appears under **Needs attention**, but has no count in the table until you
open the full list under **All Projects**.


Be told when a run fails
========================

The service can send a message when a run ends: an email, or a message to
Slack, Microsoft Teams, PagerDuty or any webhook. It sends nothing until a
system administrator sets up two things on **Admin**, **Notifications**
(which needs the ``system:notifications.write`` permission; people with
``system:notifications.read`` can look but not change). Only run results
are sent today: a run failing, and a run completing. Reservations expiring,
devices being quarantined, outbound webhooks and alert rules do not send
messages yet.

**A channel** is where messages go. Choose **Add Channel**, pick the type
(Email, Slack, Microsoft Teams, PagerDuty or Webhook), and fill in its form.
Anything that works like a password is stored in the secrets vault, never in
the channel: the SMTP password, a Slack or Teams webhook address (the address
itself is the credential), a PagerDuty integration key, a webhook's
authorization header. Type it once, or choose a secret that is already in
the vault; afterwards the page shows only where it is stored and never the
value. If a form has mistakes, every one is listed together and marked beside
its field, and nothing is saved. On the channel's page:

* **Send a test message** sends one through the channel with its real
  settings and says whether it arrived, how long it took, and, if not, the
  reason the far end gave. Do this once after adding a channel.
* **Replace a secret** stores a new value as a new version of the same vault
  secret; the channel follows it, so a password change is one step.
* **Turn Off** stops everything sent through the channel without deleting it.
* **Delete Channel** removes it, the messages recorded through it and the
  secrets stored for it (not a vault secret it merely pointed at). A channel
  that a rule still sends through cannot be deleted; delete the rules first.

A channel made before secrets moved to the vault keeps working, but shows
**Secret stored unprotected**; replace the secret and the old value is removed.

**A rule** says which event goes through which channels to whom. Choose
**Add Rule** (it needs a channel first), tick **A run fails** and/or **A run
completes** (each gets a rule with the message text that fits it), choose the
channels, a project or **Every project**, and who it goes to: one per line,
addresses for email, a channel such as ``#builds`` for Slack, any label for the
others. An optional limit caps how many messages the rule sends in a minute, so
a burst of failures does not flood one inbox. A rule can be turned off and on
or deleted from the same page. The page also lists the most recent messages with
their result, so you can see what was sent and why anything was not.

The message names the run and the project and gives the reason. It is sent by a
background thread of the service, never by the request that receives the pod's
result, so a slow mail relay cannot hold a run up. A message that cannot be
delivered is recorded with its error and parked as a dead letter
(``GET /api/v1/notifications/dead-letter`` lists them); it does not stop the other
messages, and it does not change the run. If the secret behind a channel has
been removed from the vault, the message fails with a note naming the channel and
the setting, never the value. Failures are also in the service log
(``pychestrate.notifications.delivery_failed``). Adding, changing, switching and
deleting channels and rules are recorded in the audit log, with the names of the
settings that changed and never a secret.

The same operations are in the REST API (and as ``pyc`` commands; see ``pyc
notifications --help``). For email:

.. code-block:: text

    POST /api/v1/notifications/channels
    {"name": "ops-mail", "kind": "smtp_email", "scope_level": "SYSTEM",
     "config": {"host": "smtp.example.com", "port": 587, "use_tls": true,
                "from_address": "pychestrate@example.com", "username": "robot"},
     "secrets": {"password": "..."}}

A secret is sent in ``secrets`` and stored in the vault, or ``config`` names an
existing vault secret as ``"secret://<name>"``; a secret sent as plain text in
``config`` is refused, with every other problem found. The other kinds are
``slack_webhook``, ``ms_teams_webhook``, ``pagerduty_events_v2`` and
``generic_webhook``. ``PATCH`` on a channel switches it on or off, changes its
plain settings or replaces a secret, ``DELETE`` removes it, and
``POST .../test`` sends a test message. A rule:

.. code-block:: text

    POST /api/v1/notifications/routing-rules
    {"event_pattern": "entity.run.failed", "template_name": "run_failed",
     "channel_ids": ["<the channel's id>"],
     "recipients": ["oncall@example.com"],
     "project_id": "<a project's id, or leave out for every project>",
     "rate_limit_per_minute": 10}

``entity.run.failed`` (a run that failed) with the ``run_failed`` template, and
``entity.run.completed`` (a run that finished) with ``run_succeeded``, are the two
events that can be sent. A rule that could never send is refused with the reason:
a pattern that matches neither event, an unknown template or channel, a template
that does not describe the event, no recipient. ``GET /api/v1/notifications/routing-rules``
lists the rules, ``PATCH`` with ``{"disabled": true}`` turns one off, and ``DELETE``
removes it.


Change or remove an alert rule
==============================

Open **Insights**, **Alert Rules** and choose the project. Each rule has an **Edit**
and a **Delete** button if you may change alert rules; without that permission the
page only reads.

**Edit** opens the same form you used to create the rule, filled in with its name,
metric, comparison, threshold, window, severity, notification targets and whether it
is enabled. Change what you need and choose **Save changes**. The kind of rule cannot
change (to alert on something different, create a new rule), and a name another rule
in the project already has is refused with a message that says so; your form stays open
so nothing you typed is lost. Saving a rule exactly as it is changes nothing.

To stop a rule without losing it, edit it and untick **Enabled**. **Delete** removes the
rule and its current state for good, after a confirmation that names the rule; it
cannot be undone.


Remove a dashboard
==================

Open **Insights**, **Dashboards** and choose the project. If you may change dashboards,
each one has a **Delete** button beside **Edit**. The confirmation names the dashboard
and says how many tiles go with it; choosing **Delete** removes it for good, so if you
only want to change what it shows, use **Edit** or the layout editor instead. Without the
permission the buttons are not shown.


What the states mean
====================

.. list-table::
   :header-rows: 1
   :widths: 26 74

   * - State
     - Meaning
   * - ``pending``
     - Created, not yet sent to a pod.
   * - ``dispatching``
     - Being signed and sent to a pod.
   * - ``dispatched``
     - The pod confirmed it received the job.
   * - ``running``
     - The pod has reported progress.
   * - ``progress_stalled``
     - Running, but no progress has arrived for a while (five minutes by
       default). It returns to *running* when progress resumes.
   * - ``completing``
     - The pod has finished and the results are arriving. A pod may report
       completion directly, so you do not always see this state.
   * - ``completed``
     - Finished; the outcome is *success*.
   * - ``failed``
     - Finished; the outcome is *failure*. Read the reason.
   * - ``cancel_requested``
     - Someone asked to cancel; the pod has not confirmed yet.
   * - ``cancelling``
     - The pod confirmed and is stopping the job.
   * - ``cancelled``
     - Stopped on request, or ended by the service after its hard deadline.
   * - ``dispatch_unconfirmed``
     - The pod did not confirm receipt in time. It can still be confirmed,
       and the run moves on to *dispatched*, or the receipt is lost.
   * - ``dispatch_lost``
     - The service lost track of whether the pod has the job. The run has
       ended without an answer from the job itself.
   * - ``dispatch_failed``
     - The job could not be sent to a pod.
   * - ``needs_investigation``
     - Something did not add up and the service flagged the run for a person to
       look at. An operator reconciles it, after which it ends *failed*, unless
       the pod reports an outcome first.

The runs that have ended are *completed*, *failed*, *cancelled*,
*dispatch_lost* and *dispatch_failed*; nothing changes them afterwards. The
*dispatch* states and *needs_investigation* point at the transport, not at the
job. The colours are described in the `Consumer UI Glossary
<18-00-ui-glossary.rst>`_.
