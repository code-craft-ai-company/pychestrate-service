"""
.. module:: pychestrate.webservice.pychestrateapplication
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Webworks Application bootstrap for the pychestrate service.

.. moduleauthor:: Automation Mojo LLC

This module assembles the runnable webworks application:

* imports every controller blueprint module (which triggers
  ``@RestBlueprint.attach_at`` descriptor registration at module-load
  time);
* collects the global :class:`EndpointRegistry` snapshot and feeds it
  into a single :class:`Router`;
* installs the standard middleware pipeline
  (:class:`DbSessionMiddleware` + :class:`PychestrateSessionMiddleware`);
* builds a :class:`Dispatcher`;
* wraps everything as a :class:`WSGIApplication` so a WSGI server
  (gunicorn, uWSGI, the built-in webworks server) can serve the app.

Callers supply a ``session_factory`` (a zero-arg callable returning a
fresh ``sqlalchemy.orm.Session``). The ``role_resolver`` and
``user_profile_lookup`` arguments default to the production-grade
helpers that ship with :mod:`pychestratesessionmiddleware`; tests typically pass
deterministic stubs.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Callable, Dict, Iterable, Optional

from automojo.errors.exceptions import ConfigurationError

from automojo.webworks.endpoints.registry import EndpointRegistry
from automojo.webworks.routing.dispatcher import Dispatcher
from automojo.webworks.routing.middleware import MiddlewarePipeline
from automojo.webworks.routing.router import Router
from automojo.webworks.wsgi.application import WSGIApplication

# Importing the blueprint modules below has a side effect: every
# RestBlueprint.attach_at decorator runs at module-load time and
# registers its EndpointDescriptor in the global EndpointRegistry. The
# bootstrap then reads that registry to populate the router.
from automojo.pychestrate.webservice.agents.restapi.v1 import (  # noqa: F401
    agentsblueprint as _agentsblueprint,
)
from automojo.pychestrate.webservice.audit.restapi.v1 import (  # noqa: F401
    auditblueprint as _auditblueprint,
)
from automojo.pychestrate.webservice.clients.restapi.v1 import (  # noqa: F401
    clientsblueprint as _clientsblueprint,
    enrollmentblueprint as _enrollmentblueprint,
)
from automojo.pychestrate.webservice.identity.flags.restapi.v1 import (  # noqa: F401
    flagsblueprint as _flagsblueprint,
)
from automojo.pychestrate.webservice.identity.users.restapi.v1 import (  # noqa: F401
    identityusersblueprint as _identityusersblueprint,
)
from automojo.pychestrate.webservice.dbsessionmiddleware import (
    DbSessionMiddleware,
    SessionFactory,
)
from automojo.pychestrate.webservice.notifications.restapi.v1 import (  # noqa: F401
    notificationchannelsblueprint as _notificationchannelsblueprint,
)
from automojo.pychestrate.webservice import (  # noqa: F401
    openapiblueprint as _openapiblueprint,
)
from automojo.pychestrate.webservice.orchestration import (  # noqa: F401
    flowsblueprint as _flowsblueprint,
)
from automojo.pychestrate.webservice.accesspolicymiddleware import (
    AccessPolicyMiddleware,
)
from automojo.pychestrate.webservice.bearertokenmiddleware import (
    BearerTokenMiddleware,
)
from automojo.pychestrate.webservice.orchestration.flowruntime import (
    FlowRuntime,
)
from automojo.pychestrate.webservice.pods.restapi.v1 import (  # noqa: F401
    podsblueprint as _podsblueprint,
)
from automojo.pychestrate.webservice.project_templates.restapi.v1 import (  # noqa: F401
    projecttemplatesblueprint as _projecttemplatesblueprint,
)
from automojo.pychestrate.webservice.projects.restapi.v1 import (  # noqa: F401
    projectsblueprint as _projectsblueprint,
)
from automojo.pychestrate.webservice.retention.restapi.v1 import (  # noqa: F401
    retentionblueprint as _retentionblueprint,
)
from automojo.pychestrate.webservice.secrets.restapi.v1 import (  # noqa: F401
    secretsblueprint as _secretsblueprint,
)
from automojo.pychestrate.webservice.security.auth.restapi.v1 import (  # noqa: F401
    authblueprint as _authblueprint,
)
from automojo.pychestrate.webservice.security.auth.pychestratesessionmiddleware import (
    PychestrateSessionMiddleware,
    RoleResolver,
    UserProfileLookup,
    default_role_resolver_via_rbac,
    default_user_profile_lookup_via_user_service,
)
from automojo.pychestrate.webservice.security.rbac.restapi.v1 import (  # noqa: F401
    rbacblueprint as _rbacblueprint,
)
from automojo.pychestrate.webservice.tagging.restapi.v1 import (  # noqa: F401
    tagsblueprint as _tagsblueprint,
)
from automojo.pychestrate.webservice.variables.restapi.v1 import (  # noqa: F401
    variablesblueprint as _variablesblueprint,
)
from automojo.pychestrate.webservice.workers.localworkerpool import (
    LocalWorkerPool,
    resolve_pool_config_from_env,
)
from automojo.pychestrate.webservice.workers.staleworkersweeper import (
    StaleWorkerSweeper,
    resolve_sweeper_config_from_env,
)
from automojo.pychestrate.webservice.workers.restapi.v1 import (  # noqa: F401
    queueblueprint as _queueblueprint,
    workersblueprint as _workersblueprint,
)


class PychestrateApplication:
    """
        Runnable webworks application for the pychestrate service.

        Construction wires the full request-handling stack:

        * imports every blueprint module (descriptor side-effects),
        * builds a :class:`Router` from the resulting
          :class:`EndpointRegistry` snapshot,
        * installs :class:`DbSessionMiddleware` and
          :class:`PychestrateSessionMiddleware` in the pipeline,
        * constructs a :class:`Dispatcher`,
        * wraps everything as a :class:`WSGIApplication`.

        :param session_factory: Zero-arg callable returning a fresh
                                SQLAlchemy session per request.
        :param role_resolver: Optional callable that returns role names
                              for a user id. Defaults to the RBAC-bound
                              resolver that reads
                              ``binding_service.list_bindings``.
        :param user_profile_lookup: Optional callable that returns a
                                    :class:`UserProfile` for a user id.
                                    Defaults to the production lookup
                                    that reads ``user_service``.
        :param register_extensions: Whether to call
                                    :func:`register_phase1_builtin_extensions`
                                    during construction. Defaults to
                                    True for production; tests with a
                                    pre-registered extension state may
                                    pass False.
        :param debug: Whether the WSGI app and dispatcher emit
                      tracebacks in error responses.
    """

    def __init__(
            self,
            *,
            session_factory: SessionFactory,
            role_resolver: Optional[RoleResolver] = None,
            user_profile_lookup: Optional[UserProfileLookup] = None,
            register_extensions: bool = True,
            debug: bool = False,
            local_worker_pool_size: Optional[int] = None,
            local_worker_pool_autostart: bool = False,
            stale_worker_sweeper_autostart: bool = False,
        ):
        """
            Construct a :class:`PychestrateApplication`.
        """
        if session_factory is None:
            err_lines = [
                "PychestrateApplication requires a session_factory.",
            ]
            err_msg = os.linesep.join(err_lines)
            raise ConfigurationError(err_msg)

        if role_resolver is None:
            self._role_resolver: RoleResolver = default_role_resolver_via_rbac
        else:
            self._role_resolver = role_resolver

        if user_profile_lookup is None:
            self._user_profile_lookup: UserProfileLookup = (
                default_user_profile_lookup_via_user_service
            )
        else:
            self._user_profile_lookup = user_profile_lookup

        self._session_factory: SessionFactory = session_factory
        self._debug: bool = debug

        if register_extensions is True:
            self._register_builtin_extensions()

        # FlowRuntime is constructed with the same session_factory so
        # taskplus submissions persist to FlowSubmissionRecord rows
        # and survive a service restart.
        self._flow_runtime: FlowRuntime = FlowRuntime(
            session_factory=session_factory,
        )

        # In-process local worker pool. Pool size resolves from the
        # caller's explicit override first, otherwise from
        # PYCHESTRATE_LOCAL_WORKER_POOL_SIZE in the environment, with
        # a default of 1. The pool is constructed but only auto-
        # started when the bootstrap path requests it (the WSGI
        # entrypoint does; tests typically don't, since they want
        # deterministic control over which worker handles which
        # job).
        env_config = resolve_pool_config_from_env()
        if local_worker_pool_size is not None:
            env_config["size"] = int(local_worker_pool_size)
        self._local_worker_pool: LocalWorkerPool = LocalWorkerPool(
            session_factory=session_factory,
            size=env_config["size"],
            base_name=env_config["base_name"],
            poll_interval_seconds=env_config["poll_interval_seconds"],
            heartbeat_interval_seconds=(
                env_config["heartbeat_interval_seconds"]
            ),
            default_command_timeout_seconds=(
                env_config["default_command_timeout_seconds"]
            ),
        )
        if local_worker_pool_autostart is True:
            self._local_worker_pool.start()

        # Stale-worker sweeper. Reads its threshold + interval
        # from the environment so operators can dial in tighter
        # liveness windows without redeploying. Construction is
        # always cheap; only the autostart flag (or env override)
        # spins the background thread.
        sweeper_config = resolve_sweeper_config_from_env()
        self._stale_worker_sweeper: StaleWorkerSweeper = (
            StaleWorkerSweeper(
                session_factory=session_factory,
                stale_threshold_seconds=(
                    sweeper_config["stale_threshold_seconds"]
                ),
                sweep_interval_seconds=(
                    sweeper_config["sweep_interval_seconds"]
                ),
            )
        )
        if stale_worker_sweeper_autostart is True:
            if sweeper_config["enabled"] is True:
                self._stale_worker_sweeper.start()

        self._router: Router = self._build_router()
        self._pipeline: MiddlewarePipeline = self._build_pipeline()
        self._dispatcher: Dispatcher = self._build_dispatcher(debug=debug)
        self._wsgi_app: WSGIApplication = WSGIApplication(
            handler=self._dispatcher.dispatch,
            debug=debug,
        )
        return

    @property
    def router(self) -> Router:
        """
            The assembled :class:`Router` with every registered route.

            :returns: The router instance.
        """
        rtnval = self._router
        return rtnval

    @property
    def pipeline(self) -> MiddlewarePipeline:
        """
            The middleware pipeline.

            :returns: The pipeline instance.
        """
        rtnval = self._pipeline
        return rtnval

    @property
    def dispatcher(self) -> Dispatcher:
        """
            The :class:`Dispatcher` that bridges the router to the
            pipeline.

            :returns: The dispatcher instance.
        """
        rtnval = self._dispatcher
        return rtnval

    @property
    def wsgi_application(self) -> WSGIApplication:
        """
            The runnable :class:`WSGIApplication` callable.

            :returns: The WSGI app instance.
        """
        rtnval = self._wsgi_app
        return rtnval

    @property
    def flow_runtime(self) -> FlowRuntime:
        """
            The :class:`FlowRuntime` shared by every request through
            the dispatcher attach-shim. Wired with the same
            session_factory as the rest of the app so submissions
            persist to FlowSubmissionRecord rows.

            :returns: The runtime instance.
        """
        rtnval = self._flow_runtime
        return rtnval

    @property
    def local_worker_pool(self) -> LocalWorkerPool:
        """
            The in-process :class:`LocalWorkerPool`. The pool is
            constructed during ``__init__`` but only auto-started
            when ``local_worker_pool_autostart=True`` was passed
            to the constructor. The WSGI entrypoint
            (``wsgientry.py``) starts it; unit tests typically
            don't.

            :returns: The pool instance.
        """
        rtnval = self._local_worker_pool
        return rtnval

    @property
    def stale_worker_sweeper(self) -> StaleWorkerSweeper:
        """
            The :class:`StaleWorkerSweeper` background thread.
            Constructed during ``__init__`` but only auto-started
            when ``stale_worker_sweeper_autostart=True``. The
            WSGI entrypoint starts it; unit tests typically run
            ``run_one_pass`` directly for determinism.

            :returns: The sweeper instance.
        """
        rtnval = self._stale_worker_sweeper
        return rtnval

    @property
    def debug(self) -> bool:
        """
            Whether debug mode is enabled.

            :returns: True when debug responses include tracebacks.
        """
        rtnval = self._debug
        return rtnval

    def shutdown(self, *, wait: bool = True) -> None:
        """
            Graceful shutdown: drain the local worker pool, then
            stop the stale-worker sweeper, then the flow runtime.
            The pool is drained first so any in-flight
            ``RemoteCommand`` step against a local worker has a
            chance to complete and report a result before the
            flow runtime stops accepting new work; the sweeper
            stops next so a final pass can fail any orphaned
            jobs.
        """
        self._local_worker_pool.shutdown(wait=wait)
        self._stale_worker_sweeper.shutdown(wait=wait)
        self._flow_runtime.shutdown(wait=wait)
        return

    def __call__(
            self,
            environ: Dict[str, Any],
            start_response: Callable,
        ) -> Iterable[bytes]:
        """
            WSGI entry point — delegates to the wrapped
            :class:`WSGIApplication`.

            :param environ: WSGI environ dict.
            :param start_response: WSGI start_response callable.

            :returns: The WSGI response body iterator.
        """
        rtnval = self._wsgi_app(environ, start_response)
        return rtnval

    def _register_builtin_extensions(self) -> None:
        """
            Register the Phase-1 built-in extensions (RBAC catalog,
            credential providers, taxonomy registrations, ...).

            Imported lazily so unit tests that exercise the bootstrap
            without a full extension stack can opt out via
            ``register_extensions=False``.
        """
        from automojo.pychestrate.webservice.extensions.bootstrap import (
            register_phase1_builtin_extensions,
        )
        register_phase1_builtin_extensions()
        return

    def _build_router(self) -> Router:
        """
            Construct the :class:`Router` and load it with every
            descriptor registered in the global
            :class:`EndpointRegistry`.

            :returns: A populated router.
        """
        router = Router()
        descriptors = EndpointRegistry.collect()
        for descriptor in descriptors:
            router.add_endpoint(descriptor=descriptor)
        rtnval = router
        return rtnval

    def _build_dispatcher(self, *, debug: bool) -> Dispatcher:
        """
            Construct a :class:`Dispatcher` and wrap its ``dispatch``
            so every incoming :class:`Request` carries the per-app
            :class:`FlowRuntime` on ``request.flow_runtime`` (the
            attribute the FlowsBlueprint reads).
        """
        dispatcher = Dispatcher(
            router=self._router,
            pipeline=self._pipeline,
            debug=debug,
        )
        original_dispatch = dispatcher.dispatch
        flow_runtime_ref = self._flow_runtime
        router_ref = self._router

        def _dispatch_with_runtime(*, request) -> Any:
            # Only attach the app's runtime when callers (typically
            # tests) haven't already injected an override. This keeps
            # the per-request override pattern from
            # test_p24h_end_to_end_application_smoke_m3 working.
            existing = getattr(request, "flow_runtime", None)
            if existing is None:
                request.flow_runtime = flow_runtime_ref

            # Resolve the matching descriptor up-front so the
            # AccessPolicyMiddleware can read ``request.endpoint_descriptor``
            # off the request without taking a router reference of
            # its own. The dispatcher will re-match downstream — that
            # second match is cheap (in-process radix walk).
            match = router_ref.match(request)
            if match is not None:
                request.endpoint_descriptor = match.descriptor
            else:
                request.endpoint_descriptor = None

            rtnval = original_dispatch(request=request)
            return rtnval

        dispatcher.dispatch = _dispatch_with_runtime
        return dispatcher

    def _build_pipeline(self) -> MiddlewarePipeline:
        """
            Construct the standard middleware pipeline:

            * :class:`DbSessionMiddleware` first (so authentication
              can read DB state).
            * :class:`PychestrateSessionMiddleware` (translates the
              ``pychestrate_session`` cookie into ``request.auth``).
            * :class:`BearerTokenMiddleware` (translates an
              ``Authorization: Bearer <token>`` header into
              ``request.auth`` when no cookie identity already
              landed — so cookie callers keep their human seat and
              bearer-only callers get the agent identity).
            * :class:`AccessPolicyMiddleware` (enforces per-endpoint
              role / scope requirements declared via
              ``access_policy=`` on ``RestBlueprint.attach_at``).

            :returns: The configured pipeline.
        """
        db_session_middleware = DbSessionMiddleware(
            session_factory=self._session_factory,
        )
        session_bridge = PychestrateSessionMiddleware(
            session_factory=self._session_factory,
            role_resolver=self._role_resolver,
            user_profile_lookup=self._user_profile_lookup,
        )
        bearer_token = BearerTokenMiddleware()
        access_policy = AccessPolicyMiddleware()

        pipeline = MiddlewarePipeline()
        pipeline.add(
            middleware=db_session_middleware,
            name=db_session_middleware.name,
        )
        pipeline.add(
            middleware=session_bridge,
            name=session_bridge.name,
        )
        pipeline.add(
            middleware=bearer_token,
            name=bearer_token.name,
        )
        pipeline.add(
            middleware=access_policy,
            name=access_policy.name,
        )
        rtnval = pipeline
        return rtnval


def build_application(
        *,
        session_factory: SessionFactory,
        role_resolver: Optional[RoleResolver] = None,
        user_profile_lookup: Optional[UserProfileLookup] = None,
        register_extensions: bool = True,
        debug: bool = False,
    ) -> PychestrateApplication:
    """
        Convenience factory for callers that prefer a function over
        instantiating :class:`PychestrateApplication` directly.

        :param session_factory: Zero-arg callable returning a fresh
                                SQLAlchemy session.
        :param role_resolver: Optional override for the role resolver.
        :param user_profile_lookup: Optional override for the user
                                    profile lookup.
        :param register_extensions: Whether to call
                                    ``register_phase1_builtin_extensions``.
        :param debug: Whether the dispatcher and WSGI app emit
                      debug-mode error responses.

        :returns: A constructed :class:`PychestrateApplication`.
    """
    rtnval = PychestrateApplication(
        session_factory=session_factory,
        role_resolver=role_resolver,
        user_profile_lookup=user_profile_lookup,
        register_extensions=register_extensions,
        debug=debug,
    )
    return rtnval
