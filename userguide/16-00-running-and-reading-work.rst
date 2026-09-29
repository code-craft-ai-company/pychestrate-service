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
the entry requires.


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
builds and tests, are under **Orchestration**, **Pipelines**.


Follow a run
============

**Orchestration**, **Runs** lists runs newest first. Filter by **State** or by
**Project**, and choose **Refresh** to reload; the page notes when it last did.
The columns are **Job** (what ran: the job's name, which links to the run's
page, and the short id after it for quoting), **Type** (for example *Test ·
testbase* or *Build · makefile*), **Project**, **State**, **Created** and
**Duration** (how long it ran, or how long so far while it is running; a dash
for a run that has not started). The **Builds** and **Provisioning runs** pages
lead the same way: a build with its runner and target (*makefile · docs*) and
the source it came from (*main @ github.com/acme/widgets*), a provisioning run
with its action and driver (*apply · terraform*). On a narrow screen the table
scrolls sideways as one piece.

**Download CSV**, beside Refresh, saves the whole list as the filters now
show it (not just the page on screen) as a spreadsheet: run id, project, job
name and type, state, outcome, when it was created, started and completed, how
long it ran, and the pod. It holds at most 5,000 runs; a longer list is cut and
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
* Its facts: **Project**, **Pod**, **Job type**, **Job name**, **Dispatch
  attempt**, and the times it was **Created**, **Dispatched**, **Started** and
  **Completed**.
* **Terminal outcome** and **Reason**, once the run has ended. The reason says
  why. For a test run it is the pod's account, for example "testbase run exited
  with code 255", or "testbase result manifest: outcome=success". A run that
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
