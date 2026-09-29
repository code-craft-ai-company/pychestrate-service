.. _userguide:

***********
User Manual
***********

Pychestrate is a self-hosted service that keeps an inventory of lab
devices and resources, organizes work into projects, and runs build,
test, infrastructure, and RPA jobs on pods. This manual is grouped by
what you want to do. New here? Read the `Overview <01-00-overview.rst>`_,
then `Getting Started <02-00-getting-started.rst>`_.


Using Pychestrate
=================

* `Overview <01-00-overview.rst>`_ -- what Pychestrate is, how its
  pieces fit together, and the concepts the rest of the manual uses.
* `Getting Started <02-00-getting-started.rst>`_ -- run a development
  server, finish the setup wizard, and create your first project.
* `RPA Jobs <19-00-rpa-jobs.rst>`_ -- register versioned automations and
  run them from a project.
* `Running and Reading Work <16-00-running-and-reading-work.rst>`_ --
  start a test run or a build, follow it, read the result, cancel it, and
  what each run state means.
* `Managing the Lab <15-00-lab-administration.rst>`_ -- devices,
  resource pools, IP pools, check-out and check-in, reservations, and
  health checks.
* `Choosing What the UI Shows <20-00-ui-profiles.rst>`_ -- hide the
  automation domains a deployment or a person does not use.
* `The pyc Command Line <14-00-pyc-command-line.rst>`_ -- every REST
  operation as a command, for terminals, scripts and CI jobs.


Operating Pychestrate
=====================

* `Deploying Pychestrate <13-00-alpha-deployment.rst>`_ -- the operator
  runbook: Postgres, secrets, gunicorn, TLS, the first administrator,
  and smoke tests.
* `Environment Variable Reference <21-00-environment-reference.rst>`_ --
  every variable the service reads, its default, and what it changes.


Extending Pychestrate
=====================

* `Extensions <11-00-extensions.rst>`_ -- factory protocols, resource
  extensions, packaging, and a worked example.


Contributing to Pychestrate
===========================

Start with `CONTRIBUTING.md <../CONTRIBUTING.md>`_ at the repository
root. The standards and internals it refers to:

* `Code Organization and Conventions
  <09-00-code-organization-and-conventions.rst>`_ -- the webworks
  service, retired flask controllers, RFC 7807 problem documents.
* `Coding Standards <10-00-coding-standards.rst>`_, with
  `Code Organization <10-01-code-organization.rst>`_,
  `Naming Conventions <10-02-naming-conventions.rst>`_,
  `Testing Patterns and Practices <10-03-testing-patterns-and-practices.rst>`_,
  and `Testing Frameworks <10-04-testing-frameworks.rst>`_.
* `Consumer UI Auth Stack <12-00-consumer-ui-auth-stack.rst>`_ -- how
  sign-in, sessions, and RBAC are wired, and their history.
* `Site Shell <17-00-site-shell.rst>`_ -- the ``<pyc-site-shell>``
  chrome, its sidebar and palette registries, and its invariants.
* `Consumer UI Glossary <18-00-ui-glossary.rst>`_ -- the words, status
  colors, and formats the interface uses.


.. toctree::
   :hidden:
   :caption: Using Pychestrate

   01-00-overview
   02-00-getting-started
   16-00-running-and-reading-work
   15-00-lab-administration
   19-00-rpa-jobs
   20-00-ui-profiles
   14-00-pyc-command-line

.. toctree::
   :hidden:
   :caption: Operating Pychestrate

   13-00-alpha-deployment
   21-00-environment-reference

.. toctree::
   :hidden:
   :caption: Extending Pychestrate

   11-00-extensions

.. toctree::
   :hidden:
   :caption: Contributing to Pychestrate

   09-00-code-organization-and-conventions
   10-00-coding-standards
   12-00-consumer-ui-auth-stack
   17-00-site-shell
   18-00-ui-glossary
