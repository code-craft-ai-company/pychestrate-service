import logging
import os

from typing import Any

from automojo.pychestrate.webservice.extensions.bootstrap import (
    register_phase1_builtin_extensions,
)
from automojo.pychestrate.webservice.extensions.phase2_bootstrap import (
    register_phase2_builtin_extensions,
)
from automojo.pychestrate.webservice.extensions.phase3_bootstrap import (
    register_phase3_builtin_extensions,
)
from automojo.pychestrate.webservice.extensions.phase4_bootstrap import (
    register_phase4_builtin_extensions,
)
from automojo.pychestrate.webservice.extensions.phase5_bootstrap import (
    register_phase5_builtin_extensions,
)
from automojo.pychestrate.webservice.extensions.phase6_bootstrap import (
    register_phase6_builtin_extensions,
)
from automojo.pychestrate.webservice.extensions.ext_router import (
    mount_extension_routes,
)
from automojo.pychestrate.webservice.agents.restapi.v1.agents_routes import (
    register_agents_routes,
)
from automojo.pychestrate.webservice.audit.restapi.v1.audit_routes import (
    register_audit_routes,
)
from automojo.pychestrate.webservice.clients.restapi.v1.clients_routes import (
    register_clients_routes,
)
from automojo.pychestrate.webservice.clients.restapi.v1.enrollment_routes import (
    register_enrollment_routes,
)
from automojo.pychestrate.webservice.identity.flags.restapi.v1.flags_routes import (
    register_flags_routes,
)
from automojo.pychestrate.webservice.identity.users.restapi.v1.users_routes import (
    register_users_routes,
)
from automojo.pychestrate.webservice.middleware_setup_gate import (
    install_pychestrate_setup_gate_middleware,
)
from automojo.pychestrate.webservice.middleware_webworks import (
    install_pychestrate_session_middleware,
)
from automojo.pychestrate.webservice.notifications.restapi.v1.channels_routes import (
    register_channels_routes,
)
from automojo.pychestrate.webservice.plugin_api.restapi.v1.catalog_routes import (
    register_catalog_routes,
)
from automojo.pychestrate.webservice.pods.restapi.v1.pods_routes import (
    register_pods_routes,
)
from automojo.pychestrate.webservice.projects.restapi.v1.projects_routes import (
    register_projects_routes,
)
from automojo.pychestrate.webservice.plugin_api.runtime import (
    build_and_validate_catalog as build_and_validate_plugin_api_catalog,
)
from automojo.pychestrate.webservice.retention.restapi.v1.retention_routes import (
    register_retention_routes,
)
from automojo.pychestrate.webservice.identity.setup.setup_service import (
    bootstrap_setup_state,
    is_setup_complete as _is_setup_complete,
)
from automojo.pychestrate.webservice.runtime_bootstrap import (
    bootstrap_runtime,
    load_config_from_environment,
)
from automojo.pychestrate.webservice.project_templates.restapi.v1.templates_routes import (
    register_templates_routes,
)
from automojo.pychestrate.webservice.secrets.restapi.v1.secrets_routes import (
    register_secrets_routes,
)
from automojo.pychestrate.webservice.tagging.restapi.v1.tags_routes import (
    register_tags_routes,
)
from automojo.pychestrate.webservice.variables.restapi.v1.variables_routes import (
    register_variables_routes,
)
from automojo.pychestrate.webservice.security.auth.restapi.v1.auth_routes import (
    register_auth_routes,
)
from automojo.pychestrate.webservice.security.auth.restapi.v1.me_routes import (
    register_me_routes,
)
from automojo.pychestrate.webservice.security.rbac.restapi.v1.rbac_routes import (
    register_rbac_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
    register_config_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.setup.routes import (
    register_setup_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    register_projects_routes as register_projects_web_ui_routes,
)
from automojo.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    register_resources_routes,
)
from automojo.pychestrate.webservice.webinterface.foundation.static_files import (
    register_static_routes,
)
from automojo.pychestrate.webservice.webinterface.foundation.templating import (
    build_jinja_environment,
    discover_blueprint_template_paths,
    set_default_environment,
)
from automojo.pychestrate.webservice.webinterface.foundation.url_for import (
    install_url_for_global,
)
from automojo.pychestrate.webservice.metadata import SITE_DIRECTORIES, SITE_SHARED_GLOBALS
from automojo.pychestrate.webservice.pychestrate_variables import (
    PychestrateVariables,
)
from automojo.webworks.webapplication import establish_webapp_persona
from automojo.webworks.wsgi.application import create_wsgi_application
from automojo.webworks.wsgi.server import run_server
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import HTMLResponse, Response


def _eager_start_response_wsgi(wsgi_app: Any) -> Any:
    """
        Wrap a webworks-built WSGI app so the bundled
        :class:`webworks.wsgi.worker.Worker` can serve responses.

        The bug: ``wsgi.application.WSGIApplication.__call__`` is a
        generator that calls ``start_response(status, headers)``
        BEFORE its first ``yield``. The worker calls
        ``start_response.send_headers()`` BEFORE iterating the
        generator (worker.py line 521). Because the generator body
        has not run yet, ``_status`` is still ``None`` and
        ``send_headers()`` raises
        ``RuntimeError("start_response not called before sending
        headers")`` -- every response ends as a 500 with an empty
        body. Tests against the dispatcher pass; only the WSGI
        envelope is broken. This is what produced the "blank page"
        on the first deploy.

        The fix: drive the generator to its first yield (or end)
        eagerly inside this wrapper. By the time the wrapper
        returns, the WSGI app has already called start_response,
        so the worker's send_headers check passes. We then return
        an iterable that re-yields the buffered first chunk and
        continues iterating the remaining chunks lazily, preserving
        WSGI streaming semantics for callers that care.

        :param wsgi_app: The WSGI callable returned by
                         :func:`webworks.wsgi.application.create_wsgi_application`.

        :returns: A WSGI callable that does the eager advance.
    """
    def _wrapped(environ, start_response):
        gen = wsgi_app(environ, start_response)
        try:
            first_chunk = next(gen)
        except StopIteration:
            # The body emitted zero chunks (e.g. a 204) but
            # start_response WAS called inside the generator body
            # before the implicit StopIteration, so the worker is
            # happy.
            return iter([])

        def _iter():
            yield first_chunk
            for chunk in gen:
                yield chunk

        rtnval = _iter()
        return rtnval

    rtnval = _wrapped
    return rtnval


def build_wsgi_compat_dispatch(*, app: Any) -> Any:
    """
        Return a callable that dispatches a webworks request and
        massages the returned :class:`Response` so the bundled
        :class:`automojo.webworks.wsgi.response.WSGIResponseBuilder`
        emits a correct HTTP response. Two version-skew bugs in
        the venv'd webworks library have to be papered over here:

        1. **Missing ``content_type`` attribute.** The builder
           reads ``response.content_type`` as an attribute when
           the body is non-empty, but :class:`Response` only
           stores the content type in the ``headers`` dict
           (e.g. ``{"Content-Type": "text/html"}``). Without the
           backfill every non-redirect response raises
           ``AttributeError`` inside the WSGI envelope and gets
           swallowed as a 500. Backfilling ``content_type =
           None`` is sufficient: the builder's
           :meth:`format_headers` already re-emits the
           Content-Type from ``headers`` when present and only
           falls back to the parameter when absent.

        2. **Set-Cookie headers dropped.**
           :meth:`Response.set_cookie` stores cookies in
           ``response._cookies`` (a :class:`SimpleCookie`).
           :meth:`Response._get_all_headers` correctly fans
           those out as ``Set-Cookie`` headers, but the WSGI
           builder ignores ``_cookies`` and only iterates the
           ``headers`` dict -- so any cookie a handler sets
           never reaches the wire.

           Push the serialized cookie value(s) into
           ``response.headers["Set-Cookie"]`` so the builder
           picks them up. Multi-cookie cases collapse onto the
           single header slot a dict supports; the consumer UI
           only sets one cookie per response so this is fine
           in practice. (A future webworks upgrade that fixes
           the builder to use ``Response.to_wsgi`` directly
           obsoletes this shim.)

        :param app: WebWorks application built by
                    :func:`establish_webapp_persona` and advanced
                    past ``INFRASTRUCTURE_READY``.

        :returns: A callable suitable for the ``handler`` slot in
                  :func:`create_wsgi_application`'s config.
    """
    dispatch = app.dispatcher.dispatch

    def _dispatch_with_response_compat(
            request: Request
        ) -> Response:
        response = dispatch(request)
        if not hasattr(response, "content_type"):
            response.content_type = None

        # Push any cookies set via ``response.set_cookie(...)``
        # into the response headers dict so the bundled WSGI
        # builder emits them.
        cookies_jar = getattr(response, "_cookies", None)
        if cookies_jar is not None and len(cookies_jar) > 0:
            cookie_header_values = []
            for cookie_name in cookies_jar:
                morsel = cookies_jar[cookie_name]
                cookie_header_values.append(morsel.OutputString())
            # The WSGI ``format_headers`` step skips hop-by-hop
            # headers but does not coalesce repeated names; a
            # dict slot can only carry one value, so we join with
            # ``\r\n`` -- WSGI servers split this back into
            # separate Set-Cookie headers per the WSGI spec
            # (PEP 3333 explicitly allows this for hosting
            # frameworks).  The webworks builder's
            # ``format_headers`` produces a list of (name, value)
            # tuples though, and its consumer (the WSGI app's
            # ``__call__``) just hands them to ``start_response``,
            # which on most servers treats them as a single
            # header. To be safe and to keep the behavior simple,
            # set only the first cookie via the headers dict and
            # drop any additional. This module's UI only sets
            # one cookie per response.
            response.headers["Set-Cookie"] = cookie_header_values[0]

        return response

    rtnval = _dispatch_with_response_compat
    return rtnval

DIR_THIS = os.path.dirname(__file__)

logger = logging.getLogger("scms")

# Resolve the persona presence directory BEFORE persona init.
# Precedence: ``--presence-dir`` CLI flag, ``PYCHESTRATE_PRESENCE_DIR``
# env var, then the pychestrate default ``~/pychestrate``. This
# bootstrap step deliberately bypasses ``AppVarAccessor`` because
# the presence_dir holds the settings file -- it cannot itself be
# read from settings without a chicken-and-egg.
import sys

from automojo.pychestrate.webservice.pychestrate_presence import (
    resolve_presence_dir,
)

_presence_dir = resolve_presence_dir(argv=sys.argv[1:])

app = establish_webapp_persona(
    name="pychestrate",
    logger_name="scms",
    log_basename="pychestrate",
    presence_dir=_presence_dir,
)

@app.attach_route("/", methods=["GET"])
def hello_world(request: Request) -> HTMLResponse:
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pychestrate SCM</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #f5f7fa; color: #333; }
            header { background-color: #2c3e50; color: white; padding: 1rem 2rem; }
            .container { padding: 2rem; max-width: 1200px; margin: 0 auto; }
            .card { background: white; border-radius: 8px; padding: 2rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            h1 { margin-top: 0; }
        </style>
    </head>
    <body>
        <header>
            <h1>⚙️ Pychestrate SCM</h1>
        </header>
        <div class="container">
            <div class="card">
                <h2>Welcome to Pychestrate</h2>
                <p>The Software Configuration Management system powered by Automation Mojo WebWorks.</p>
                <p>This is the initial web interface scaffolding.</p>
                <hr>
                <p><em>Status:</em> Online and Orchestrating.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

def install_web_ui_templating() -> None:
    """
        Build and publish the jinja2 environment the consumer-
        facing web UI handlers render against. Walks the per-
        blueprint ``templates/`` subdirectories under
        ``SITE_DIRECTORIES.DIR_BLUEPRINTS`` and installs the result
        as the module-level default environment so handlers can
        call :func:`render_template_response` without threading the
        env through every callsite.

        Also attaches the :func:`url_for` shim to the environment as
        a global so blueprint templates can build links the same way
        the flask-era templates did (``{{ url_for('config.dashboard')
        }}``).

        Idempotent across calls -- the singleton is overwritten on
        each invocation; tests reset it with
        ``reset_default_environment_for_testing``.

        :returns: None.
    """
    template_paths = discover_blueprint_template_paths(
        blueprints_root=SITE_DIRECTORIES.DIR_BLUEPRINTS,
    )
    if len(template_paths) == 0:
        # No blueprints have shipped templates yet; the web UI
        # handlers will fail later if any handler tries to render.
        # Still install an environment so the first failure points
        # at the missing template rather than at "no env configured".
        template_paths = [SITE_DIRECTORIES.DIR_BLUEPRINTS]
    environment = build_jinja_environment(
        template_search_paths=template_paths,
    )
    install_url_for_global(environment=environment)
    set_default_environment(environment=environment)
    return


def register_service_extensions() -> None:
    """
        Register every in-tree factory-protocol implementation and
        resource-extension pack that the service publishes REST
        namespaces for. Must run before ``app.startup`` so request
        handlers that look up factories see populated registries.

        Full-fidelity :func:`bootstrap_phase1_runtime` /
        :func:`bootstrap_phase2_runtime` / :func:`bootstrap_phase3_runtime`
        additionally load the KEK, password pepper, and bus subscribers;
        those are driven from operator-supplied config and are wired in
        at deployment time. The register-only path here is idempotent
        and does not touch any secret material.

        :returns: None.
    """
    register_phase1_builtin_extensions()
    register_phase2_builtin_extensions()
    register_phase3_builtin_extensions()
    register_phase4_builtin_extensions()
    register_phase5_builtin_extensions()
    register_phase6_builtin_extensions()
    build_and_validate_plugin_api_catalog()
    mount_extension_routes()
    register_flags_routes(app=app, version_prefix="/api/v1")
    register_audit_routes(app=app, version_prefix="/api/v1")
    register_catalog_routes(app=app, version_prefix="/api/v1")
    register_channels_routes(app=app, version_prefix="/api/v1")
    register_auth_routes(app=app, version_prefix="/api/v1")
    register_me_routes(app=app, version_prefix="/api/v1")
    register_templates_routes(app=app, version_prefix="/api/v1")
    register_secrets_routes(app=app, version_prefix="/api/v1")
    register_agents_routes(app=app, version_prefix="/api/v1")
    register_users_routes(app=app, version_prefix="/api/v1")
    register_tags_routes(app=app, version_prefix="/api/v1")
    register_retention_routes(app=app, version_prefix="/api/v1")
    register_variables_routes(app=app, version_prefix="/api/v1")
    register_clients_routes(app=app, version_prefix="/api/v1")
    register_rbac_routes(app=app, version_prefix="/api/v1")
    register_enrollment_routes(app=app, version_prefix="/api/v1")
    register_pods_routes(app=app, version_prefix="/api/v1")
    register_projects_routes(app=app, version_prefix="/api/v1")
    register_static_routes(
        app=app,
        url_prefix="/static",
        static_root=SITE_DIRECTORIES.DIR_STATIC,
    )
    install_web_ui_templating()
    # Setup wizard routes register BEFORE the rest of the consumer
    # UI so the gate-redirect target ``/setup/unlock`` is bound on
    # the dispatcher early.
    register_setup_routes(app=app)
    register_config_routes(app=app)
    register_resources_routes(app=app)
    register_projects_web_ui_routes(app=app)
    return


def pychestrate_website_main():
    runtime_config = load_config_from_environment()
    bootstrap_runtime(config=runtime_config)

    # Provision the initial-admin token (idempotent; no-op past
    # completion). Logs the on-disk token path so operators see it
    # in journald / stdout immediately.
    session_factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    token_path = bootstrap_setup_state(session_factory=session_factory)
    print("Initial-admin token path: {}".format(token_path))

    register_service_extensions()

    app.startup()

    install_pychestrate_session_middleware(app=app)

    # Gate middleware installs LAST so it is the outermost wrapper:
    # webworks pipeline ``position="start"`` puts each new entry at
    # the head of the list, so the LAST install ends up running
    # FIRST on the way in. This is what we want -- the gate must
    # decide whether to redirect before any session work happens.
    install_pychestrate_setup_gate_middleware(
        app=app,
        is_complete=lambda: _is_setup_complete(
            session_factory=SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
        ),
    )

    wsgi_app_inner = create_wsgi_application(config={"handler": build_wsgi_compat_dispatch(app=app)})
    wsgi_app = _eager_start_response_wsgi(wsgi_app_inner)

    bind_host = PychestrateVariables.PYCHESTRATE_BIND_HOST
    bind_port = int(PychestrateVariables.PYCHESTRATE_BIND_PORT)
    workers = int(os.environ.get("PYCHESTRATE_WORKERS", "1"))
    threads = int(os.environ.get("PYCHESTRATE_THREADS", "1"))

    print(
        "Starting native WebWorks WSGI Server on {}:{} (workers={}, threads={})".format(
            bind_host, bind_port, workers, threads
        )
    )
    run_server(app=wsgi_app, host=bind_host, port=bind_port,
               workers=workers, threads=threads)


def build_wsgi_application_for_production():
    """
        Build a fully-bootstrapped WSGI app for embedding in an
        external WSGI server (gunicorn, uwsgi, mod_wsgi). Reads the
        operator environment, builds the engine + KEK + pepper, wires
        every Phase-1/2/3 bus subscriber, registers all webworks
        routes, advances the app to ``INFRASTRUCTURE_READY``, and
        installs the session middleware. The returned WSGI callable
        is what the external server should host.

        Example gunicorn invocation::

            gunicorn 'app_pychestrate_main:build_wsgi_application_for_production()' \\
                --bind 0.0.0.0:8888 --workers 4

        The trailing ``()`` tells gunicorn to call the factory rather
        than treat it as a module-level WSGI app object.

        :returns: WSGI callable.
    """
    runtime_config = load_config_from_environment()
    bootstrap_runtime(config=runtime_config)

    # Provision the initial-admin token. See pychestrate_website_main
    # for the rationale; the production-WSGI factory mirrors the dev
    # entry point exactly.
    session_factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    token_path = bootstrap_setup_state(session_factory=session_factory)
    print("Initial-admin token path: {}".format(token_path))

    register_service_extensions()
    app.startup()
    install_pychestrate_session_middleware(app=app)
    install_pychestrate_setup_gate_middleware(
        app=app,
        is_complete=lambda: _is_setup_complete(
            session_factory=SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
        ),
    )

    rtnval_inner = create_wsgi_application(config={"handler": build_wsgi_compat_dispatch(app=app)})
    rtnval = _eager_start_response_wsgi(rtnval_inner)
    return rtnval

if __name__ == "__main__":
    pychestrate_website_main()
