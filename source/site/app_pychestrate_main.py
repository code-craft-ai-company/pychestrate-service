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
from automojo.pychestrate.webservice.plugin_api.runtime import (
    build_and_validate_catalog as build_and_validate_plugin_api_catalog,
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
    return


def pychestrate_website_main():
    register_service_extensions()

    app.startup()
    wsgi_app = create_wsgi_application(config={"handler": app.dispatcher})

    print("Starting native WebWorks WSGI Server on 127.0.0.1:8888")
    run_server(app=wsgi_app, host="127.0.0.1", port=8888, workers=1, threads=1)

if __name__ == "__main__":
    pychestrate_website_main()
