import logging
import os

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
from automojo.pychestrate.webservice.identity.flags.restapi.v1.flags_routes import (
    register_flags_routes,
)
from automojo.pychestrate.webservice.identity.users.restapi.v1.users_routes import (
    register_users_routes,
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
from automojo.pychestrate.webservice.plugin_api.runtime import (
    build_and_validate_catalog as build_and_validate_plugin_api_catalog,
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
from automojo.pychestrate.webservice.security.auth.restapi.v1.auth_routes import (
    register_auth_routes,
)
from automojo.webworks.webapplication import establish_webapp_persona
from automojo.webworks.wsgi.application import create_wsgi_application
from automojo.webworks.wsgi.server import run_server
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import HTMLResponse

DIR_THIS = os.path.dirname(__file__)

logger = logging.getLogger("scms")

app = establish_webapp_persona(
    name="pychestrate",
    logger_name="scms",
    log_basename="pychestrate"
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
    register_templates_routes(app=app, version_prefix="/api/v1")
    register_secrets_routes(app=app, version_prefix="/api/v1")
    register_agents_routes(app=app, version_prefix="/api/v1")
    register_users_routes(app=app, version_prefix="/api/v1")
    return


def pychestrate_website_main():
    runtime_config = load_config_from_environment()
    bootstrap_runtime(config=runtime_config)

    register_service_extensions()

    app.startup()

    install_pychestrate_session_middleware(app=app)

    wsgi_app = create_wsgi_application(config={"handler": app.dispatcher})

    bind_host = os.environ.get("PYCHESTRATE_BIND_HOST", "127.0.0.1")
    bind_port = int(os.environ.get("PYCHESTRATE_BIND_PORT", "8888"))
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

    register_service_extensions()
    app.startup()
    install_pychestrate_session_middleware(app=app)

    rtnval = create_wsgi_application(config={"handler": app.dispatcher})
    return rtnval

if __name__ == "__main__":
    pychestrate_website_main()
