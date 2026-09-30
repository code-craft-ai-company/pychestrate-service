.. _11-00-extensions:

==========
Extensions
==========

Pychestrate exposes well-defined extension points so teams can add drivers,
strategies, event subscribers, and resource kinds without forking the service:
an extension is a Python package you install next to it, and the service loads
it at start. This document covers:

* The two kinds of extension points — **factory protocols** and **resource
  extensions** — and when to use each.
* How to implement an extension, register it, and confirm it is active.
* A complete worked example that replaces the in-tree ``password_hasher`` with
  a production Argon2id implementation.

Most of what follows applies to any extension point. The
`Worked example: adding an Argon2id password hasher`_ section is a concrete walk-through of the most
commonly-needed operator customization: hardening local credential hashing.


Concepts
========

Factory protocols vs resource extensions
----------------------------------------

Pychestrate has two extension patterns. They look similar but solve
different problems; mixing them up is the first mistake to avoid.

**Factory protocols** — *override or provide a named behavior.* A
``FactoryProtocolBase`` subclass declares a contract identified by a
``factory_protocol_name``. Concrete implementations inherit the protocol, set
a numeric ``PRECEDENCE`` (lower = higher priority), and compete for the
same slot. The registry returns the winning implementation to the consumer.
Examples: ``secrets_backend``, ``audit_sink``, ``auth_provider``, ``password_hasher``.

**Resource extensions** — *add a new kind of thing to a registry.* A
``ResourceExtension`` subclass is the collection base type. Concrete
subclasses contribute a kind; the registry returns the full set in
registration order. There is no PRECEDENCE — every subclass is enumerated.
Examples: ``PermissionExtension``, ``AuditEventTypeExtension``,
``RoleExtension``.

When in doubt: does your extension replace an existing behavior (factory
protocol) or add a new member to a set (resource extension)?

Precedence
----------

Factory protocol implementations are sorted ascending by ``PRECEDENCE``, so a
lower value wins. The in-tree reference implementations ship at ``PRECEDENCE =
1000`` or ``2000``; operators pin their own implementations at a lower number
to take over the slot. The ``StdlibScryptPasswordHasher`` that ships in-tree
deliberately uses ``PRECEDENCE = 2000`` so any real production hasher at
``1000`` or below resolves first for new hashes.

Old rows that stored a specific ``algorithm_name`` continue to verify through
the newly-installed hasher only if that hasher's ``algorithm_name()`` matches
the stored tag. When you upgrade a hasher, old rows are resolved to whichever
registered hasher declares their recorded algorithm name. This is why the
in-tree hasher is left registered even after an operator installs Argon2id —
it verifies legacy rows.


File layout of an extension pack
--------------------------------

An out-of-tree extension pack is an ordinary Python package with a name
matching the convention ``pychestrate-ext-<name>``. A minimal layout:

.. code-block::

    pychestrate-ext-auth-argon2id/
        pyproject.toml
        pychestrate_ext_auth_argon2id/
            __init__.py
            argon2id_hasher.py
            register.py

The package does not need to live under ``ccai/factories/...``. What makes the
service load it is an *entry point* in the group ``pychestrate.extensions``,
declared in the pack's ``pyproject.toml`` and pointing at its ``register``
function:

.. code-block:: toml

    [tool.poetry.plugins."pychestrate.extensions"]
    auth-argon2id = "pychestrate_ext_auth_argon2id:register"

When the pack is installed in the service's environment, the service imports that
function at start (after its own extensions are registered) and calls it once.
Nothing in the service is edited. A pack that fails to load is logged with its
name (``pychestrate.extensions.load_failed``) and the others still load; set
``PYCHESTRATE_EXTENSIONS_STRICT=1`` to stop the service instead, or
``PYCHESTRATE_LOAD_EXTENSIONS=0`` to load none (see the
:ref:`environment reference <21-00-environment-reference>`). A pack runs code
inside the service, exactly as any installed package does, so install only packs
you trust.

The fastest way to start is the generator, which writes a pack that is already
wired this way:

.. code-block:: bash

    python -m ccai.pychestrate.admin pack-template new \
        --name my-pack --author "Your Team" --license MIT \
        --protocol notification_channel

It creates ``pychestrate-ext-my-pack/`` with the manifest, a ``register.py`` whose
``register()`` registers nothing yet (the sample factory raises until you
implement it), the ``pyproject.toml`` entry point, and a unit test. Replace the
sample with a real implementation and register it in ``register()``.


Implementing an extension
=========================

Factory protocol implementation
-------------------------------

To contribute an implementation of an existing factory protocol:

1. **Find the protocol class.** It lives next to the feature that owns it
   under ``source/site/ccai/pychestrate/webservice/.../factories/``. The
   protocol declares ``factory_protocol_name``, ``protocol_schema_version``,
   and the classmethods implementations must provide.
2. **Subclass it.** Set ``PRECEDENCE`` to a value lower than the in-tree
   reference. Implement every classmethod listed on the base.
3. **Register it.** Call
   ``ccai.pychestrate.webservice.extensions.registry.register_factory_implementation``
   once at service startup, before the first consumer reads from the registry.

Resource extension contribution
-------------------------------

To add a new kind of thing:

1. **Find the base class.** It lives next to the feature that owns it under
   ``source/site/ccai/pychestrate/webservice/.../extensions/``. Each base
   declares the class attributes implementations must set (``permission_keys``,
   ``kind``, ``source_topic``, …).
2. **Subclass it.** Set every class attribute the base declares. Do not set
   ``PRECEDENCE`` — resource extensions are not ordered.
3. **Register it.** Call
   ``ccai.pychestrate.webservice.extensions.registry.register_resource_extension``
   once at startup with both the base class and your subclass.

Registering multiple extensions at once
---------------------------------------

The convention is a single ``register()`` function that the service calls at
start through the pack's entry point (see the pack layout above).

.. code-block:: python

    from ccai.pychestrate.webservice.extensions.registry import (
        register_factory_implementation,
    )
    from .argon2id_hasher import Argon2idPasswordHasher

    def register() -> None:
        register_factory_implementation(implementation=Argon2idPasswordHasher)
        return

Confirm the extension is active
-------------------------------

Call
``ccai.pychestrate.webservice.extensions.registry.list_factory_implementations``
after bootstrap and assert your class is in the returned tuple. The tuple is
sorted ascending by ``PRECEDENCE`` so the winning implementation for new
resolutions is always ``result[0]``.


.. _11-01-argon2id-hasher:

Worked example: adding an Argon2id password hasher
==================================================

The in-tree ``StdlibScryptPasswordHasher`` is good enough for a development
boot, but production deployments should use Argon2id with ``memory_cost >= 65536``
KiB, ``time_cost >= 3``, and ``parallelism >= 1``. This section shows the
complete extension pack.

.. note::

   ``password_hasher`` is not one of the protocols in the
   :doc:`Plugin Catalog <extensions/index>` (the catalog lists the externally
   stable protocols; see the table below). It is an internal protocol whose
   contract may change between releases. This example shows the mechanics of a
   pack, and it works, but prefer a catalog protocol for anything you plan to
   maintain across upgrades.

The service never imports ``argon2``. The extension pack adds the dependency,
the hasher class, and the registration call. Installing the pack is all that's
needed: its entry point makes the service call ``register()`` at start.

Step 1 — Scaffold the package
-----------------------------

Create a new Python package ``pychestrate-ext-auth-argon2id`` with this layout:

.. code-block::

    pychestrate-ext-auth-argon2id/
        pyproject.toml
        pychestrate_ext_auth_argon2id/
            __init__.py
            argon2id_hasher.py

``pyproject.toml``:

.. code-block:: toml

    [tool.poetry]
    name = "pychestrate-ext-auth-argon2id"
    version = "0.1.0"
    description = "Argon2id password hasher extension for Pychestrate"
    authors = []

    [tool.poetry.plugins."pychestrate.extensions"]
    auth-argon2id = "pychestrate_ext_auth_argon2id:register"

    [tool.poetry.dependencies]
    python = ">=3.10,<4.0"
    argon2-cffi = "^23.1"

    [build-system]
    requires = ["poetry-core"]
    build-backend = "poetry.core.masonry.api"

Step 2 — Implement the hasher
-----------------------------

``pychestrate_ext_auth_argon2id/argon2id_hasher.py``:

.. code-block:: python

    """
        Argon2id password hasher — Pychestrate extension pack.
    """

    from argon2 import PasswordHasher
    from argon2.exceptions import VerificationError, VerifyMismatchError

    from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
    from ccai.pychestrate.webservice.security.auth.factories.password_hasher import (
        EncodedHash,
        PasswordHasherProtocol,
    )


    ARGON2ID_ALGORITHM_NAME: str = "argon2id-64mib-3t"
    ARGON2ID_TIME_COST: int = 3
    ARGON2ID_MEMORY_COST_KIB: int = 65536
    ARGON2ID_PARALLELISM: int = 1
    ARGON2ID_HASH_LEN: int = 32
    ARGON2ID_SALT_LEN: int = 16


    def _build_hasher() -> PasswordHasher:
        """
            Construct the configured argon2-cffi PasswordHasher.

            :returns: PasswordHasher instance with the parameters above.
        """
        rtnval = PasswordHasher(
            time_cost=ARGON2ID_TIME_COST,
            memory_cost=ARGON2ID_MEMORY_COST_KIB,
            parallelism=ARGON2ID_PARALLELISM,
            hash_len=ARGON2ID_HASH_LEN,
            salt_len=ARGON2ID_SALT_LEN,
        )
        return rtnval


    class Argon2idPasswordHasher(PasswordHasherProtocol):
        """
            Argon2id reference implementation.

            Registered at PRECEDENCE=1000 so it resolves ahead of the in-tree
            stdlib scrypt hasher (PRECEDENCE=2000) for new hashes. Old rows
            stamped with the stdlib algorithm_name continue to verify via the
            stdlib hasher.
        """

        factory_protocol_name: str = "password_hasher"
        protocol_schema_version: int = 1
        PRECEDENCE: int = 1000

        @classmethod
        def algorithm_name(cls) -> str:
            rtnval = ARGON2ID_ALGORITHM_NAME
            return rtnval

        @classmethod
        def hash_password(cls, *, password: str, pepper: SecretBytes) -> EncodedHash:
            hasher = _build_hasher()
            peppered = password.encode("utf-8") + pepper.reveal()
            encoded_str = hasher.hash(peppered)
            rtnval = EncodedHash(
                encoded_bytes=encoded_str.encode("utf-8"),
                algorithm_name=ARGON2ID_ALGORITHM_NAME,
                algo_params={
                    "algorithm": ARGON2ID_ALGORITHM_NAME,
                    "time_cost": ARGON2ID_TIME_COST,
                    "memory_cost": ARGON2ID_MEMORY_COST_KIB,
                    "parallelism": ARGON2ID_PARALLELISM,
                    "hash_len": ARGON2ID_HASH_LEN,
                    "salt_len": ARGON2ID_SALT_LEN,
                },
            )
            return rtnval

        @classmethod
        def verify_password(
                cls,
                *,
                encoded_hash: bytes,
                password: str,
                pepper: SecretBytes
            ) -> bool:
            hasher = _build_hasher()
            encoded_str = encoded_hash.decode("utf-8")
            peppered = password.encode("utf-8") + pepper.reveal()
            try:
                hasher.verify(encoded_str, peppered)
            except VerifyMismatchError:
                return False
            except VerificationError:
                return False
            rtnval = True
            return rtnval

Notes on the implementation:

* The class declares ``factory_protocol_name`` and ``protocol_schema_version``
  to match the base. Pychestrate checks the version on lookup to catch
  contract drift.
* ``PRECEDENCE = 1000`` wins against the in-tree ``2000``. If a site wants
  an even stronger hasher later, it can ship another extension at
  ``PRECEDENCE = 500`` without removing this one.
* The password is concatenated with the pepper the service keeps in its secrets
  store under ``system:auth.local.password_pepper``. The
  extension never generates or reads the pepper itself — it receives it
  through the protocol argument.
* Verification returns ``False`` on mismatch rather than raising. The
  ``local_flow`` wrapper translates ``False`` into an
  ``AuthenticationError`` after recording a backoff failure.
* The stored bytes are the argon2-cffi canonical encoding,
  e.g. ``$argon2id$v=19$m=65536,t=3,p=1$<b64 salt>$<b64 digest>``. No custom
  serialization — argon2-cffi owns the format.

Step 3 — Expose a register() entry point
----------------------------------------

``pychestrate_ext_auth_argon2id/__init__.py``:

.. code-block:: python

    """
        Argon2id password hasher extension for Pychestrate.
    """

    from ccai.pychestrate.webservice.extensions.registry import (
        register_factory_implementation,
    )

    from pychestrate_ext_auth_argon2id.argon2id_hasher import Argon2idPasswordHasher


    def register() -> None:
        """
            Register the Argon2id hasher as a password_hasher implementation.

            :returns: None.
        """
        register_factory_implementation(implementation=Argon2idPasswordHasher)
        return

Step 4 — Install the pack
-------------------------

In the consuming service (pychestrate-service):

.. code-block:: bash

    poetry add pychestrate-ext-auth-argon2id
    # or, during local development:
    poetry add ../pychestrate-ext-auth-argon2id --editable

Step 5 — Restart the service
----------------------------

There is nothing to wire. The pack's entry point (Step 1) makes the service call
``register()`` at start. Restart it and look for the line
``pychestrate.extensions.loaded: name=auth-argon2id`` in the log; a pack that could
not load is reported as ``pychestrate.extensions.load_failed`` with the error.

If you run the service from your own start-up code instead (or in a test), call
``pychestrate_ext_auth_argon2id.register()`` yourself after the service's own
extensions are registered and before the first request.

Step 6 — Confirm the resolution order
-------------------------------------

At a REPL or in a startup diagnostic:

.. code-block:: python

    from ccai.pychestrate.webservice.extensions.registry import (
        list_factory_implementations,
    )

    impls = list_factory_implementations(factory_protocol_name="password_hasher")
    for impl in impls:
        print(impl.__name__, impl.algorithm_name(), "PRECEDENCE=", impl.PRECEDENCE)

Expected output after the extension registers:

.. code-block::

    Argon2idPasswordHasher argon2id-64mib-3t PRECEDENCE= 1000
    StdlibScryptPasswordHasher phase1-scrypt PRECEDENCE= 2000

The first entry wins for new hashes. Old rows stamped ``phase1-scrypt`` route
to the second entry for verification via ``resolve_hasher_for_verifying``.

Step 7 — Verify end-to-end
--------------------------

In the service process:

.. code-block:: python

    from ccai.pychestrate.webservice.security.auth.local_flow import hash_password

    encoded_bytes, algo_params = hash_password(password="correct horse battery staple")
    print(algo_params["algorithm"])
    # argon2id-64mib-3t

Now every new password hashed by ``local_flow.hash_password`` uses Argon2id;
every stored row carries ``algo_params["algorithm"] = "argon2id-64mib-3t"``;
and any legacy scrypt rows continue to verify correctly.


Rehashing legacy rows on successful login (optional)
====================================================

The verifier does not automatically rehash legacy rows to the newly-installed
hasher. Operators wanting to cycle every user to Argon2id have two options:

* **Passive migration.** Next time a user changes their password, the new
  hash goes through the top-priority hasher automatically. No operator
  action needed.
* **Forced rotation.** Set ``must_rotate_after`` on every
  ``AuthLocalCredentials`` row to ``now()`` so the service forces each user
  through a password change on next login.


Extending other factory protocols
=================================

The same pattern applies to every factory protocol in the
:doc:`Plugin Catalog <extensions/index>`, which is the externally stable surface:
its pages give each protocol's schema version, support status and reference
implementation.

=============================  ====================================================================
Protocol                       What it is for (the reference implementation shipped in the service)
=============================  ====================================================================
``secrets_backend``            Where secrets are stored (local encrypted store).
``auth_provider``              How people sign in (local credentials); add OIDC or SAML here.
``notification_channel``       Where notifications go (SMTP email); add Slack, Teams or PagerDuty.
``backup_storage_backend``     Where backup archives are kept (local filesystem).
``scm_provider``               A source-hosting service (GitHub).
``inbound_webhook_parser``     How an incoming webhook is verified and read (generic HMAC).
``build_runner_kind``          How a build is run (a Makefile).
``test_runner_kind``           How a test run is started (testbase).
``infra_tool_driver``          How infrastructure is provisioned (Terraform).
``progress_parser``            How a pod's progress reports are read (testbase).
``result_tree_parser``         How a pod's uploaded results are read (testbase).
``resource_kind``              A kind of lab resource (a device).
``rpa_job_type``               A type of RPA job (a process).
``rpa_execution_mode``         How an RPA job's process is executed (a subprocess).
``timeseries_driver``          Where metric samples are stored (native PostgreSQL).
=============================  ====================================================================

The service also has internal protocols that are not in the catalog, among them
``password_hasher`` (this guide's example), ``audit_sink``,
``feature_flag_backend``, ``user_directory_source`` and ``resource_health_probe``.
They work the same way but carry no stability promise: their contracts can
change between releases.

The mechanism is identical to the Argon2id walk-through above -- the in-tree
``notifications/extensions/run_failed_template.py`` registers through the same
registry that an out-of-tree ``pychestrate-ext-notif-slack`` would use; the
registry does not distinguish between the two.

For every protocol the same six steps apply:

1. Scaffold a ``pychestrate-ext-<name>`` package.
2. Subclass the protocol base; implement every classmethod.
3. Set ``PRECEDENCE`` below the in-tree reference.
4. Export a ``register()`` function and declare it as an entry point in the group
   ``pychestrate.extensions``.
5. Install the package and restart the service.
6. Confirm registration with ``list_factory_implementations``.


Testing an extension
====================

Extensions should ship their own tests. A testbase-style unit test for an
Argon2id hasher extension looks like:

.. code-block:: python

    from ccai import testbase

    from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes

    from pychestrate_ext_auth_argon2id.argon2id_hasher import Argon2idPasswordHasher


    def test_argon2id_hash_round_trip():
        """
            **Feature: pychestrate-ext-auth-argon2id**
            **Property: hash_password produces an encoded_bytes value that
            verify_password accepts for the same (password, pepper) pair.**
        """
        pepper = SecretBytes(b"unit-test-pepper-material")
        encoded = Argon2idPasswordHasher.hash_password(
            password="correct-horse-battery",
            pepper=pepper,
        )
        testbase.assert_equal(encoded.algorithm_name, "argon2id-64mib-3t")

        ok = Argon2idPasswordHasher.verify_password(
            encoded_hash=encoded.encoded_bytes,
            password="correct-horse-battery",
            pepper=pepper,
        )
        testbase.assert_equal(ok, True)

        wrong = Argon2idPasswordHasher.verify_password(
            encoded_hash=encoded.encoded_bytes,
            password="wrong",
            pepper=pepper,
        )
        testbase.assert_equal(wrong, False)
        return

To verify the registry integration, write a test that registers the extension
at a non-default ``PRECEDENCE`` and asserts the resolver picks it up:

.. code-block:: python

    from ccai.pychestrate.webservice.extensions.registry import (
        register_factory_implementation,
        reset_registry_for_testing,
        unregister_factory_implementation,
    )
    from ccai.pychestrate.webservice.security.auth.factories.password_hasher import (
        resolve_hasher_for_hashing,
    )

    from pychestrate_ext_auth_argon2id.argon2id_hasher import Argon2idPasswordHasher


    def test_argon2id_wins_against_default():
        """
            **Feature: pychestrate-ext-auth-argon2id**
            **Property: PRECEDENCE=1000 wins against the in-tree stdlib hasher
            at PRECEDENCE=2000 for new-hash resolution.**
        """
        reset_registry_for_testing()

        # Imitate the in-tree registration.
        from ccai.pychestrate.webservice.security.auth import (
            register_builtin_extensions,
        )
        register_builtin_extensions()

        # Now layer on the extension.
        register_factory_implementation(implementation=Argon2idPasswordHasher)
        try:
            hasher = resolve_hasher_for_hashing()
            testbase.assert_equal(hasher.__name__, "Argon2idPasswordHasher")
        finally:
            unregister_factory_implementation(implementation=Argon2idPasswordHasher)
        return


Troubleshooting
===============

**My extension's ``register()`` was called but the protocol still resolves
to the in-tree reference.**

Check ``PRECEDENCE``. The in-tree reference ships at ``2000`` for the
``password_hasher`` protocol (other protocols use ``1000``). Your extension
must use a *lower* number — the registry sorts ascending.

**ConfigurationError: No implementation found for factory protocol: X**

Your extension's ``register()`` was not called, or the factory_protocol_name
on your subclass does not match the base's value. Double-check the class
attribute is spelled exactly as the base declares it.

**ConfigurationError: No registered password_hasher matches the stored
algorithm.**

You upgraded to a new hasher and removed the previous hasher before old rows
were re-hashed. The verifier looks up the stored ``algorithm_name`` and the
extension that declared it is no longer registered. Solutions:

* Keep the old hasher registered alongside the new one until all rows are
  rehashed. The in-tree stdlib-scrypt hasher is registered automatically for
  this reason — do not remove it after you install Argon2id.
* If the previous hasher came from an external extension, leave that
  extension installed (it can be registered at a higher ``PRECEDENCE`` so the
  new hasher still wins for new hashes while old rows verify).

**My pack is installed but the service does not seem to load it.**

Check, in this order: that the pack is installed in the *same environment* the
service runs in; that its ``pyproject.toml`` declares the entry point in the group
``pychestrate.extensions`` (``[tool.poetry.plugins."pychestrate.extensions"]``) and
that it points at a callable (``module:register``); that ``PYCHESTRATE_LOAD_EXTENSIONS``
is not ``0``; and the service log, which names every pack it loaded
(``pychestrate.extensions.loaded``) or could not load
(``pychestrate.extensions.load_failed``, with the error). After changing an entry
point, reinstall the pack: entry points are read from the installed metadata.

**Tests interact with each other through global registry state.**

Use ``ccai.pychestrate.webservice.extensions.registry.reset_registry_for_testing``
at the top of each test, then call the specific extension's ``register()``
within the test.
