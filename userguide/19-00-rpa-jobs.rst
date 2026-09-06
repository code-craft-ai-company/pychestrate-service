=========
RPA Jobs
=========

Pychestrate runs Robotic Process Automation (RPA) jobs beside builds,
tests, and infrastructure runs. An RPA job is a **versioned job type**
that receives a **work packet** and performs the work on a pod. This
chapter covers the concepts, both execution modes, the pages and API
you use, and how to write a job type.

Concepts
========

Job type
    A deployment-wide, named automation such as ``invoice-import``.
    Administrators register job types once. A job type declares how it
    runs (its *execution mode*), the JSON Schema its work packet must
    satisfy, which packet fields are secrets, and which pod
    capabilities it needs.

Version
    A published release of a job type: where the code comes from, the
    entrypoint the pod runs, environment variables, and a timeout.
    Versions are ``active``, ``deprecated`` (still runnable when
    pinned, skipped by ``latest-active``), or ``retired``.

Specification
    A project-scoped binding of a job type to a version selector plus
    default packet fields. ``latest-active`` follows the newest active
    version; an exact label pins one. Editing a specification bumps
    its revision; each job records the revision it ran from.

Work packet
    The JSON document a job processes. The packet you submit is merged
    over the specification's defaults (your keys win), validated
    against the job type's schema, and delivered to the job. Fields
    the job type marks as secret are redacted everywhere except the
    signed envelope the pod receives.

Job
    One triggered execution. It moves through ``pending``,
    ``dispatching``, ``running`` and ends ``succeeded``, ``failed``,
    ``timeout``, or ``cancelled``. The job detail page shows the
    redacted packet, exit code, live log, and the result tree location.

Execution modes
===============

Simple process job
------------------

The pod runs a command. The version's entrypoint looks like::

    {"command": ["python", "-m", "jobs.invoice_import"],
     "packet_delivery": "file"}

The client writes ``work_packet.json`` into the run directory and
exports these variables before starting the command:

``PYC_WORK_PACKET``
    Path of the packet file (``packet_delivery: file``, the default).
    With ``stdin`` the packet is also written to standard input; with
    ``env`` it is also placed in ``PYC_WORK_PACKET_JSON``.
``PYC_RUN_ID``, ``PYC_JOB_TYPE``, ``PYC_JOB_VERSION``
    Identity of the run.
``PYC_RESULTS_DIR``
    Directory whose contents are uploaded as the result tree together
    with ``stdout.log`` and ``stderr.log``.

Exit code ``0`` means success. Anything the job prints is streamed to
the log viewer while it runs. A line of the form
``PYC-PROGRESS {"percent": 40, "message": "..."}`` is lifted into the
job's progress indicator.

Tasker-based job
----------------

The pod runs a ``codecraftai-taskplus`` workflow. The entrypoint names
either a workflow file inside the version's source or a single task::

    {"workflow": "workflows/invoice.yaml"}
    {"tasking": "jobs.invoice@InvoiceImport"}

The client renders ``workflow.rendered.yaml`` with the work packet as
the workflow's ``parameters`` (packet keys win over the file's own)
and the version's environment as its ``environment``, then runs
``taskplus workflow run`` as a subprocess. The engine is never imported
into the client, so a misbehaving workflow cannot take the agent down.
The pod needs the ``taskplus`` console script on ``PATH``.

Sources
-------

A version's code comes from one of three places:

``git``
    ``https://host/repo.git#ref`` is cloned and checked out per run.
``package``
    The job code is installed on the pod; the run directory is the
    working directory.
``local``
    A directory already present on the pod.

Pages
=====

``/admin/rpa-job-types``
    The registry. Register a type, publish versions, deprecate,
    reactivate, or retire them. Requires ``system:rpa.job_types.manage``
    to change anything.

``/projects/<id>/rpa/specs``
    A project's specifications. Developers create one by choosing an
    active job type, a version selector, default packet fields, and
    optional pod requirements.

``/projects/<id>/rpa/specs/<spec>``
    Specification detail with the **Run** form. The packet editor is
    pre-filled from the defaults; edit and run. The dispatch is
    confirmed before it happens.

``/projects/<id>/rpa``
    The jobs list with specification and status filters; each row
    links to the job detail and its logs.

API
===

Everything the pages do is available under ``/api/v1``:

* ``GET|POST /rpa/job-types``, ``GET|PATCH /rpa/job-types/{type_id}``,
  ``POST .../retire``, ``POST .../versions``,
  ``POST .../versions/{version}/deprecate|retire``.
* ``GET|POST /projects/{project_id}/rpa/specs``,
  ``GET|PATCH|DELETE .../specs/{spec_id}``,
  ``POST .../specs/{spec_id}/trigger``.
* ``GET /projects/{project_id}/rpa/jobs``, ``GET .../jobs/{job_id}``,
  ``GET .../jobs/{job_id}/logs``, ``POST .../jobs/{job_id}/cancel``.

A trigger that fails packet validation answers ``422`` with an
``errors`` list of ``{path, message}`` pairs. ``409`` means no eligible
pod, a capability mismatch, or an inactive version. See
``specs/openapi/pychestrate.yaml`` for the full contract.

Pipelines and watches
=====================

A pipeline stage of ``kind: rpa`` triggers a specification with a
packet::

    - kind: rpa
      inputs:
        spec_id: 3f2a...
        work_packet: {customer_id: 42}

A watch action ``trigger_rpa_job`` does the same when its source event
fires; put ``spec_id`` and ``work_packet`` in the action parameters.

Writing a job type in code
==========================

Extensions can ship job types as code instead of registering them by
hand. Subclass ``ProcessJobType`` or ``TaskplusJobType`` from
``ccai.pychestrate.webservice.orchestration.rpa`` and register the
class with the extension registry::

    class InvoiceImport(ProcessJobType):
        @classmethod
        def type_id(cls):
            return "invoice-import"

        @classmethod
        def display_name(cls):
            return "Invoice Import"

        @classmethod
        def packet_schema(cls):
            return {"type": "object", "required": ["customer_id"]}

        @classmethod
        def versions(cls):
            return (
                CodeDefinedVersion(
                    version="1.0.0",
                    source_kind="package",
                    source_ref="rpa-jobs==1.0.0",
                    entrypoint={"command": ["python", "-m", "jobs.invoice"]},
                ),
            )

The service mirrors code-defined types into the registry when the
registry is read. A type an administrator already registered keeps its
settings; only missing versions are added.

Operations
==========

* Pods advertise an ``rpa`` capability when the client's dispatch loop
  starts: whether ``taskplus`` is on ``PATH`` (and its version), plus the
  ``rpa_job_types`` and ``capability_tags`` lists an operator adds to the
  client's ``config.json``. The service turns these into matcher tags
  (``rpa``, ``rpa:<job type>``, and each free-form tag); job types and
  specifications can require them, and dispatch picks only pods that
  advertise them. The advertisement goes through
  ``PUT /api/v1/clients/{client_id}/capabilities``.
* Cancelling a job marks it cancelled on the service and queues a cancel
  request; the pod receives it on its next heartbeat, terminates the
  process group (SIGTERM, then SIGKILL after the grace period), and
  reports the ``cancelled`` outcome with its result manifest.
* Every trigger, completion, failure, and registry change produces an
  audit record and a counter
  (``pychestrate_rpa_jobs_triggered_total`` and friends).
