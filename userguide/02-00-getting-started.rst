.. _02-00-getting-started:

***************
Getting Started
***************

This page takes you from a fresh checkout to a running Pychestrate on
your own machine: a development server, the setup wizard, your first
sign-in, a project, and a device in the inventory. It takes about 15
minutes once the dependencies are available to you.

The development server is for trying Pychestrate and working on it. To
run it for a team, follow `Deploying Pychestrate
<13-00-alpha-deployment.rst>`_ instead.

.. contents:: On this page
   :local:
   :depth: 1


What you need
=============

* Linux or macOS.
* Python 3.12 and `Poetry <https://python-poetry.org/>`_ 2.x.
* ``git``, ``make``, and ``openssl`` (the development server generates
  a throwaway certificate authority with it).
* A web browser.
* Access to PyPI, where the Code Craft AI framework packages are
  published -- see the next section.


The dependencies
================

Pychestrate is built on Code Craft AI's framework libraries (the
``codecraftai-*`` packages: webworks, testbase, runtime, and others).
They are published on PyPI, so Poetry installs them with everything
else and there is nothing to set up: no package index, no token. The
``pyproject.toml`` accepts any release in the 1.x line of each (webworks
from 1.4, which the API explorer page needs).


Install
=======

Clone the repository and run the two setup scripts from its root:

.. code-block:: bash

    git clone https://github.com/code-craft-ai-company/pychestrate-service.git
    cd pychestrate-service
    repository-setup/rehome-repository
    development/setup-environment

* ``repository-setup/rehome-repository`` writes ``.env`` (the
  ``PYTHONPATH`` that covers ``source/packages``, ``source/site``, and
  ``source/testroots``) and generates VS Code workspace files under
  ``workspaces/``.
* ``development/setup-environment`` creates the virtual environment in
  ``.venv`` with Poetry, installs the dependencies, and makes
  ``.venv/bin/activate`` load ``.env``. Run it again whenever
  ``poetry.lock`` changes; ``development/setup-environment reset``
  rebuilds ``.venv`` from scratch.


Start a development server
==========================

.. code-block:: bash

    make dev-up

``make dev-up`` runs ``development/dev-up``, which:

* generates development secrets once -- a key-encryption key, a
  password pepper, a cookie-signing secret, and a self-signed
  enrollment CA -- under ``.cache/dev-secrets/``;
* keeps the SQLite database and the setup token in
  ``.cache/presence/``;
* creates the database schema on first start and serves on
  ``http://127.0.0.1:8888``. To use another port, run
  ``PYCHESTRATE_BIND_PORT=8890 make dev-up``.

The terminal shows where the setup token is, then the server banner:

.. code-block:: text

    Initial-admin token path: /home/you/pychestrate-service/.cache/presence/initial-admin-token
    Starting native WebWorks WSGI Server on 127.0.0.1:8888 (workers=1, threads=1)

Lines about ``PYCHESTRATE_RESULT_PRESIGN_SECRET`` and the envelope
signer are expected on a development server; they matter only once
pods run jobs. Leave the server running in this terminal.


Finish the setup wizard
=======================

A new Pychestrate has no accounts. Until someone who can read the
server's files creates the first administrator, every page redirects to
the setup wizard.

#. Open ``http://127.0.0.1:8888/``. You land on **Unlock
   Pychestrate**, which shows the path of the token file.
#. In a second terminal, print the token and copy it:

   .. code-block:: bash

       cat .cache/presence/initial-admin-token

#. Paste it into **Initial admin token** and choose **Continue**.
#. Fill in the administrator's **Username** (3 to 64 letters, digits,
   underscores, or hyphens, starting with a letter or digit),
   **Email**, **Display name**, and a **Password** of at least 12
   characters, twice. Choose **Create administrator**.

You are signed in as the administrator you just created, and arrive at
the home page. The wizard is gone for good: the token file is deleted and
``/setup/unlock`` now answers "not found". (If the service cannot sign you
in for any reason, it sends you to the sign-in page instead; sign in
there with the same login and password.)


Look around
===========

The home page lists every destination, grouped the way the sidebar groups
them:
**Projects**, **Orchestration** (runs, builds, pipelines, the test
catalog, environments, provisioning), **Insights** (metrics,
dashboards, SLOs, alert rules), **Fleet** (pods, clients, resources, IP
pools, reservations, resource health), **Operations** (webhooks,
release channels), **System** (secrets), and **Admin** (users, roles,
audit logs, enrollment tokens, and the rest of the administration
pages).

The header holds four controls:

* **Ctrl+K** (**Cmd+K** on macOS) opens the command palette. Type part
  of a page name -- for example ``users`` -- and press Enter to go
  there. It also finds a project by name, offers actions such as *Create
  a project*, *Register a device*, *Switch theme* and *Sign out*, and
  opens a run or build when you paste its full id.
* **Theme** switches between the light and dark themes.
* **Preferences** is where you choose which parts of the interface you
  see (below).
* **Sign out** ends your session.

The account menu also opens this guide (**User guide**), which the service
serves itself, so it matches the running release and opens without internet
access. A form that needs explaining, such as the ones that create a role, a
project, a device, a pool, a reservation or a health check, register an RPA job
type, or add a notification channel or rule, has a **Learn more** link beside its
title that opens the section explaining it in a new tab, so what you have typed
is not lost. If the guide is not installed on a deployment, the links are not
drawn.


Create a project
================

#. In the sidebar, open **Projects** and choose **All Projects**.
#. Choose **New Project**.
#. Enter a **Project Name** such as ``firmware-ci`` and, if you like, a
   **Description**. Choose **Create Project**.

The project opens on its overview. Its own navigation lists what a
project holds: **Members**, **Repositories**, **Builds**,
**Infrastructure**, **Tests**, **Releases**, **Pipelines**,
**Channels**, **Schedules**, **Release Templates**, **Calendar**,
**RPA**, and **Watches**. You are the project's owner.

Six of these are labelled "(preview)": **Infrastructure**, **Tests**,
**Pipelines**, **Channels**, **Schedules** and **Calendar**. Nothing in this
version can create what they list (test and infrastructure specifications,
release pipelines, channels, schedules, release events), so their pages stay
empty and say so. To run tests for a project, use the **Test catalog** and
**Runs** pages in the sidebar (the project's overview links to both,
filtered to it). A release is created from a **Release Template**.


Add a device to the inventory
=============================

#. Open ``http://127.0.0.1:8888/resources/list`` -- the resource list.
   (From the sidebar: **Fleet**, then **IP Pools**, then **Resources**
   in the page's section menu.)
#. Choose **Create Resource**.
#. Enter a **Resource Name** such as ``bench-phone-01``, choose the
   **Resource Type** ``Device``, and add a **Description**. Choose
   **Create Resource**.

The resource page shows its pool, health, and capacity, the check-out
form, and any active allocations and upcoming reservations. See
`Overview <01-00-overview.rst#concepts>`_ for what those mean.


Choose what the interface shows
===============================

Open **Preferences** in the header. The four checkboxes are the
interface's *surfaces*: Build Automation, Testing Automation, Robotic
Process Automation, and Infrastructure. Clear the ones you do not use
and choose **Save preferences**; their pages leave your sidebar and
project navigation. Nothing about your permissions changes. `Choosing
What the UI Shows <20-00-ui-profiles.rst>`_ explains the deployment-wide
setting an administrator controls.


If a form expires while you fill it in
======================================

A session ends after a period without activity, and a form's anti-forgery token
can go stale if the page stays open a long time. If you submit a form then, the
service does not throw away what you typed. It keeps the text fields for ten
minutes and, once you are signed in again, opens the same form with them put back
and a notice saying so; check them and submit again. This covers the project,
resource, user and role forms, the RPA job type form and the forms that add a notification
channel or rule.

Some things are deliberately not kept: anything in a field whose name suggests a
secret (a password, a token, a key), forms that hold secrets (Secrets, Variables,
API tokens, enrollment tokens and the sign-in pages), and, when the form is put
back, tick boxes, passwords and lists that take several choices, which you choose
again. The text is stored on the service, not in your browser, and is deleted as
soon as the form has been filled in again or after ten minutes, whichever comes
first.


Stop or start over
==================

* Press **Ctrl+C** in the terminal running ``make dev-up`` to stop the
  server. The next ``make dev-up`` reuses the same database, so your
  administrator and project are still there.
* To start from an empty database and see the setup wizard again, stop
  the server and delete the presence directory; the development
  secrets in ``.cache/dev-secrets/`` are kept:

  .. code-block:: bash

      rm -rf .cache/presence


Next steps
==========

* `Deploying Pychestrate <13-00-alpha-deployment.rst>`_ -- run it for a
  team on Postgres, behind TLS.
* `RPA Jobs <19-00-rpa-jobs.rst>`_ -- register an automation and run it
  from a project.
* Pods run jobs through the pod client (``pychestrate-client``), which
  lives in its own repository; an administrator creates its one-time
  enrollment token under **Admin**, **Enrollment Tokens**.
* `DEVELOPING.md <../DEVELOPING.md>`_ -- run the tests and change
  Pychestrate (for the maintainers).
