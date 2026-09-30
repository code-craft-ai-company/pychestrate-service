import logging
import os

from typing import Any

from ccai.pychestrate.webservice.extensions.bootstrap import (
    register_phase1_builtin_extensions,
)
from ccai.pychestrate.webservice.extensions.phase2_bootstrap import (
    register_phase2_builtin_extensions,
)
from ccai.pychestrate.webservice.extensions.phase3_bootstrap import (
    register_phase3_builtin_extensions,
)
from ccai.pychestrate.webservice.extensions.phase4_bootstrap import (
    register_phase4_builtin_extensions,
)
from ccai.pychestrate.webservice.extensions.phase5_bootstrap import (
    register_phase5_builtin_extensions,
)
from ccai.pychestrate.webservice.extensions.phase6_bootstrap import (
    register_phase6_builtin_extensions,
)
from ccai.pychestrate.webservice.extensions.phase7_bootstrap import (
    register_phase7_builtin_extensions,
)
from ccai.pychestrate.webservice.extensions.phase8_bootstrap import (
    register_phase8_builtin_extensions,
)
from ccai.pychestrate.webservice.extensions.view_registry_self_check import (
    log_view_registry_self_check,
)
from ccai.pychestrate.webservice.extensions.ext_router import (
    mount_extension_routes,
)
from ccai.pychestrate.webservice.agents.restapi.v1.agents_routes import (
    register_agents_routes,
)
from ccai.pychestrate.webservice.clients.restapi.v1.client_dispatch_routes import (
    register_client_dispatch_routes,
)
from ccai.pychestrate.webservice.audit.restapi.v1.audit_routes import (
    register_audit_routes,
)
from ccai.pychestrate.webservice.clients.restapi.v1.clients_routes import (
    register_clients_routes,
)
from ccai.pychestrate.webservice.clients.restapi.v1.enrollment_routes import (
    register_enrollment_routes,
)
from ccai.pychestrate.webservice.identity.flags.restapi.v1.flags_routes import (
    register_flags_routes,
)
from ccai.pychestrate.webservice.identity.users.restapi.v1.users_routes import (
    register_users_routes,
)
from ccai.pychestrate.webservice.middleware_setup_gate import (
    install_pychestrate_setup_gate_middleware,
)
from ccai.pychestrate.webservice.middleware_webworks import (
    install_pychestrate_session_middleware,
)
from ccai.pychestrate.webservice.notifications.restapi.v1.channels_routes import (
    register_channels_routes,
)
from ccai.pychestrate.webservice.notifications.restapi.v1.routing_rules_routes import (
    register_routing_rules_routes,
)
from ccai.pychestrate.webservice.plugin_api.restapi.v1.catalog_routes import (
    register_catalog_routes,
)
from ccai.pychestrate.webservice.extensions.discovery import (
    discover_and_register_extensions,
)
from ccai.pychestrate.webservice.embed.restapi.v1.embed_routes import (
    embed_views_enabled,
    register_embed_routes,
)
from ccai.pychestrate.webservice.system.restapi.v1.system_health_routes import (
    register_system_health_routes,
)
from ccai.pychestrate.webservice.system.restapi.v1.operations_routes import (
    register_operations_routes,
)
from ccai.pychestrate.webservice.mcp.service_endpoint import (
    MCP_MIDDLEWARE_PREFIX,
    register_mcp_service_routes,
)
from ccai.pychestrate.webservice.pods.restapi.v1.pods_routes import (
    register_pods_routes,
)
from ccai.pychestrate.webservice.projects.restapi.v1.projects_routes import (
    register_projects_routes,
)
from ccai.pychestrate.webservice.projects.restapi.v1.release_templates_routes import (
    register_release_templates_routes,
)
from ccai.pychestrate.webservice.plugin_api.runtime import (
    build_and_validate_catalog as build_and_validate_plugin_api_catalog,
)
from ccai.pychestrate.webservice.retention.restapi.v1.retention_routes import (
    register_retention_routes,
)
from ccai.pychestrate.webservice.identity.setup.setup_service import (
    bootstrap_setup_state,
    is_setup_complete as _is_setup_complete,
)
from ccai.pychestrate.webservice.runtime_bootstrap import (
    bootstrap_runtime,
    load_config_from_environment,
)
from ccai.pychestrate.webservice.project_templates.restapi.v1.templates_routes import (
    register_templates_routes,
)
from ccai.pychestrate.webservice.secrets.restapi.v1.secrets_routes import (
    register_secrets_routes,
)
from ccai.pychestrate.webservice.tagging.restapi.v1.tags_routes import (
    register_tags_routes,
)
from ccai.pychestrate.webservice.variables.restapi.v1.variables_routes import (
    register_variables_routes,
)
from ccai.pychestrate.webservice.security.auth.restapi.v1.auth_routes import (
    register_auth_routes,
)
from ccai.pychestrate.webservice.security.auth.restapi.v1.me_routes import (
    register_me_routes,
)
# Machine identity: API tokens, service accounts, /api/v1/me.
from ccai.pychestrate.webservice.security.auth.restapi.v1.api_tokens_routes import (
    register_api_tokens_routes,
)
# The REST contract as JSON for the pyc CLI (/api/v1/_meta/openapi.json).
from ccai.pychestrate.webservice.wsgi_dispatch import build_wsgi_compat_dispatch  # noqa: F401  (re-exported)
from ccai.pychestrate.webservice.api.openapi_document import (
    register_api_docs_routes,
    register_openapi_document_routes,
)
from ccai.pychestrate.webservice.api.error_catalogue import register_error_catalogue_routes
from ccai.pychestrate.webservice.metrics.restapi.v1.ui_metrics_routes import (
    register_ui_metrics_routes,
)
from ccai.pychestrate.webservice.metrics.restapi.v1.metrics_routes import (
    register_metrics_routes,
)
from ccai.pychestrate.webservice.metrics.restapi.v1.dashboards_routes import (
    register_dashboards_routes,
)
from ccai.pychestrate.webservice.metrics.restapi.v1.metric_alerts_routes import (
    register_metric_alerts_routes,
)
from ccai.pychestrate.webservice.runs.restapi.v1.runs_routes import (
    register_runs_routes,
)
from ccai.pychestrate.webservice.jobs.envelope.restapi.v1.signing_keys_routes import (
    register_signing_keys_routes,
)
from ccai.pychestrate.webservice.jobs.envelope.restapi.v1.jwks_routes import (
    register_envelope_jwks_routes,
)
from ccai.pychestrate.webservice.jobs.envelope.startup import (
    install_envelope_signer_from_environment,
)
from ccai.pychestrate.webservice.runs.restapi.v1.runs_events_routes import (
    register_runs_events_routes,
)
from ccai.pychestrate.webservice.runs.restapi.v1.artifacts_routes import (
    register_artifacts_routes,
)
from ccai.pychestrate.webservice.orchestration.test.restapi.v1.test_catalog_routes import (
    register_test_catalog_routes,
)
from ccai.pychestrate.webservice.orchestration.test.restapi.v1.test_runs_routes import (
    register_test_runs_routes,
)
from ccai.pychestrate.webservice.orchestration.build.restapi.v1.build_runs_routes import (
    register_build_runs_routes,
)
from ccai.pychestrate.webservice.orchestration.rpa.restapi.v1.rpa_routes import (
    register_rpa_routes,
)
from ccai.pychestrate.webservice.webinterface.site_shell.ui_profile_routes import (
    register_ui_profile_api_routes,
)
from ccai.pychestrate.webservice.orchestration.pipelines.restapi.v1.pipeline_definitions_routes import (
    register_pipeline_definitions_routes,
)
from ccai.pychestrate.webservice.orchestration.pipelines.restapi.v1.pipeline_runs_routes import (
    register_pipeline_runs_routes,
)
from ccai.pychestrate.webservice.orchestration.source.restapi.v1.source_integrations_routes import (
    register_source_integrations_routes,
)
from ccai.pychestrate.webservice.orchestration.infra.restapi.v1.environments_routes import (
    register_environments_routes,
)
from ccai.pychestrate.webservice.orchestration.infra.restapi.v1.provisioning_runs_routes import (
    register_provisioning_runs_routes,
)
from ccai.pychestrate.webservice.orchestration.infra.restapi.v1.drift_routes import (
    register_drift_routes,
)
from ccai.pychestrate.webservice.orchestration.infra.restapi.v1.guards_routes import (
    register_guards_routes,
)
from ccai.pychestrate.webservice.metrics.restapi.v1.slos_routes import (
    register_slos_routes,
)
from ccai.pychestrate.webservice.ops.release.restapi.v1.release_channels_routes import (
    register_release_channels_routes,
)
from ccai.pychestrate.webservice.security.rbac.restapi.v1.rbac_routes import (
    register_rbac_routes,
)
from ccai.pychestrate.webservice.webhooks_in.restapi.v1.webhooks_in_routes import (
    register_webhooks_in_routes,
)
from ccai.pychestrate.webservice.webhooks_out.restapi.v1.webhooks_out_routes import (
    register_webhooks_out_routes,
)
from ccai.pychestrate.webservice.backup.restapi.v1.backup_routes import (
    register_backup_routes,
)
from ccai.pychestrate.webservice.resources.restapi.v1.resource_pools_routes import (
    register_resource_pools_routes,
)
from ccai.pychestrate.webservice.resources.restapi.v1.resources_routes import (
    register_resources_routes as register_resources_api_routes,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    register_config_routes,
)
from ccai.pychestrate.webservice.webinterface.blueprints.setup.routes import (
    register_setup_routes,
)
from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    register_projects_routes as register_projects_web_ui_routes,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    register_resources_routes,
)
from ccai.pychestrate.webservice.webinterface.foundation.static_files import (
    configure_static_url_root,
    install_static_url_global,
    register_favicon_route,
    register_static_routes,
)
from ccai.pychestrate.webservice.webinterface.foundation.templating import (
    build_jinja_environment,
    install_template_globals,
    discover_blueprint_template_paths,
    set_default_environment,
)
from ccai.pychestrate.webservice.webinterface.site_shell.bundle_registry import (
    install_default_bundles as install_shell_default_bundles,
)
from ccai.pychestrate.webservice.webinterface.site_shell.catchall_route import (
    register_shell_catchall,
)
from ccai.pychestrate.webservice.webinterface.site_shell.user_guide_route import (
    register_user_guide_routes,
)
from ccai.pychestrate.webservice.webinterface.site_shell.shell_document import (
    get_shell_template_search_path,
)
from ccai.pychestrate.webservice.webinterface.foundation.url_for import (
    install_url_for_global,
)
from ccai.pychestrate.webservice.webinterface.foundation.cookie_session import (
    wrap_wsgi_app_with_secure_cookie_policy,
)
from ccai.pychestrate.webservice.clients.mtls_identity import (
    install_client_certificate_identity,
)
from ccai.pychestrate.webservice.webinterface.foundation.form_drafts import (
    wrap_wsgi_app_with_form_capture,
)
from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES, SITE_SHARED_GLOBALS
from ccai.pychestrate.webservice.pychestrate_variables import (
    PychestrateVariables,
)
from ccai.pychestrate.webservice.hardening.platform_wsgi import (
    wrap_platform_wsgi_application,
)
from ccai.webworks.webapplication import establish_webapp_persona
from ccai.webworks.wsgi.application import create_wsgi_application
from ccai.webworks.wsgi.server import run_server
from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import HTMLResponse, Response


def _wrap_with_peer_address(wsgi_app: Any) -> Any:
    """
        Wrap the WSGI app so request handlers can see the socket peer
        (``REMOTE_ADDR``); see
        :func:`security.auth.client_address.wrap_wsgi_app_with_peer_address`.

        :param wsgi_app: The WSGI application.

        :returns: The wrapped WSGI application.
    """
    from ccai.pychestrate.webservice.security.auth.client_address import (  # noqa: E402
        wrap_wsgi_app_with_peer_address,
    )
    rtnval = wrap_wsgi_app_with_peer_address(wsgi_app)
    return rtnval


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


DIR_THIS = os.path.dirname(__file__)

logger = logging.getLogger("scms")

# Resolve the persona presence directory BEFORE persona init.
# Precedence: ``--presence-dir`` CLI flag, ``PYCHESTRATE_PRESENCE_DIR``
# env var, then the pychestrate default ``~/pychestrate``. This
# bootstrap step deliberately bypasses ``AppVarAccessor`` because
# the presence_dir holds the settings file -- it cannot itself be
# read from settings without a chicken-and-egg.
import sys

from ccai.pychestrate.webservice.pychestrate_presence import (
    resolve_presence_dir,
)

_presence_dir = resolve_presence_dir(argv=sys.argv[1:])

app = establish_webapp_persona(
    name="pychestrate",
    logger_name="scms",
    log_basename="pychestrate",
    presence_dir=_presence_dir,
)

# The legacy hard-coded ``/`` handler was replaced by the site-
# shell catch-all (see ``register_shell_catchall``). The shell
# bundle is now responsible for the landing page once a user is
# authenticated. The catch-all is wired during
# ``register_service_extensions`` AFTER every other blueprint has
# registered, so any explicit blueprint route (``/admin/...``,
# ``/projects/...``, ``/login``, ``/api/...``) takes precedence.

ENV_TEMPLATE_STRICT_UNDEFINED = "PYCHESTRATE_TEMPLATE_STRICT_UNDEFINED"


def _resolve_template_strict_undefined() -> bool:
    """
        Read the ``PYCHESTRATE_TEMPLATE_STRICT_UNDEFINED`` environment
        variable and decide whether the consumer-UI jinja environment
        should raise on undefined template variables.

        Strict is the default: every template passes the phase-13
        render-smoke suite under ``StrictUndefined``, so a template
        that reads an attribute the handler never supplied is a
        defect and should fail loudly rather than render a blank.
        An operator can roll back to the lenient historical
        behaviour for one release by setting the variable to ``0``.

        :returns: True unless the variable explicitly disables it.
    """
    raw = os.environ.get(ENV_TEMPLATE_STRICT_UNDEFINED, "")
    normalized = raw.strip().lower()
    rtnval = normalized not in ("0", "false", "no", "off")
    return rtnval


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
        a global so blueprint templates can build links using the
        familiar ``{{ url_for('config.dashboard') }}`` syntax.

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

    # Site-shell template directory -- carries the shell document
    # host page (``site_shell/shell_document.html``). Appended so
    # blueprint templates retain priority on any name collision.
    shell_template_path = get_shell_template_search_path()
    template_paths = list(template_paths) + [shell_template_path]
    strict_undefined = _resolve_template_strict_undefined()
    environment = build_jinja_environment(
        template_search_paths=template_paths,
        strict_undefined=strict_undefined,
    )
    install_template_globals(environment=environment)
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
    # Layer 7 (metrics / SLOs / alerts / dashboards) and Layer 8
    # (webhooks, release channels) registries -- previously never
    # registered (audit ORC-04).
    register_phase7_builtin_extensions()
    register_phase8_builtin_extensions()
    # Packs installed next to the service that declare the
    # ``pychestrate.extensions`` entry point (DOC-11): after the in-tree
    # registrations, before the plugin catalog is built from the registries.
    discover_and_register_extensions()
    build_and_validate_plugin_api_catalog()
    mount_extension_routes()
    register_flags_routes(app=app, version_prefix="/api/v1")
    register_audit_routes(app=app, version_prefix="/api/v1")
    register_catalog_routes(app=app, version_prefix="/api/v1")
    register_system_health_routes(app=app, version_prefix="/api/v1")
    # Liveness / readiness probes and Prometheus /metrics (top level,
    # no session; see system.operations).
    register_operations_routes(app=app)
    # MCP server endpoint for agents (fixed path /mcp/1/service, not
    # under the versioned REST prefix).
    register_mcp_service_routes(app=app)
    # Embeddable views are unfinished (ORC-07): not served unless asked for.
    if embed_views_enabled() is True:
        register_embed_routes(app=app, version_prefix="/api/v1")
    register_channels_routes(app=app, version_prefix="/api/v1")
    register_routing_rules_routes(app=app, version_prefix="/api/v1")
    register_auth_routes(app=app, version_prefix="/api/v1")
    register_me_routes(app=app, version_prefix="/api/v1")
    register_ui_metrics_routes(app=app, version_prefix="/api/v1")
    register_metrics_routes(app=app, version_prefix="/api/v1")
    register_dashboards_routes(app=app, version_prefix="/api/v1")
    register_metric_alerts_routes(app=app, version_prefix="/api/v1")
    register_templates_routes(app=app, version_prefix="/api/v1")
    register_secrets_routes(app=app, version_prefix="/api/v1")
    register_agents_routes(app=app, version_prefix="/api/v1")
    register_client_dispatch_routes(app=app, version_prefix="/api/v1")
    register_users_routes(app=app, version_prefix="/api/v1")
    register_tags_routes(app=app, version_prefix="/api/v1")
    register_retention_routes(app=app, version_prefix="/api/v1")
    register_variables_routes(app=app, version_prefix="/api/v1")
    register_clients_routes(app=app, version_prefix="/api/v1")
    register_rbac_routes(app=app, version_prefix="/api/v1")
    register_enrollment_routes(app=app, version_prefix="/api/v1")
    register_pods_routes(app=app, version_prefix="/api/v1")
    register_projects_routes(app=app, version_prefix="/api/v1")
    register_release_templates_routes(app=app, version_prefix="/api/v1")
    register_runs_routes(app=app, version_prefix="/api/v1")
    register_artifacts_routes(app=app, version_prefix="/api/v1")
    register_signing_keys_routes(app=app, version_prefix="/api/v1")
    register_envelope_jwks_routes(app=app, version_prefix="/api/v1")
    register_runs_events_routes(app=app, version_prefix="/api/v1")
    register_test_catalog_routes(app=app, version_prefix="/api/v1")
    register_test_runs_routes(app=app, version_prefix="/api/v1")
    register_build_runs_routes(app=app, version_prefix="/api/v1")
    register_rpa_routes(app=app, version_prefix="/api/v1")
    register_ui_profile_api_routes(app=app, version_prefix="/api/v1")
    register_pipeline_definitions_routes(app=app, version_prefix="/api/v1")
    register_pipeline_runs_routes(app=app, version_prefix="/api/v1")
    register_source_integrations_routes(app=app, version_prefix="/api/v1")
    register_environments_routes(app=app, version_prefix="/api/v1")
    register_provisioning_runs_routes(app=app, version_prefix="/api/v1")
    register_drift_routes(app=app, version_prefix="/api/v1")
    register_guards_routes(app=app, version_prefix="/api/v1")
    register_slos_routes(app=app, version_prefix="/api/v1")
    register_release_channels_routes(app=app, version_prefix="/api/v1")
    register_resource_pools_routes(app=app, version_prefix="/api/v1")
    register_resources_api_routes(app=app, version_prefix="/api/v1")
    register_webhooks_in_routes(app=app, version_prefix="/api/v1")
    register_webhooks_out_routes(app=app, version_prefix="/api/v1")
    register_backup_routes(app=app, version_prefix="/api/v1")
    # Machine identity: API tokens, service accounts, /api/v1/me.
    register_api_tokens_routes(app=app, version_prefix="/api/v1")
    # The REST contract as JSON for the pyc CLI.
    register_openapi_document_routes(app=app, version_prefix="/api/v1")
    # The same document for people, rendered by ReDoc (/api/docs redirects).
    register_api_docs_routes(app=app, version_prefix="/api/v1")
    # The pages the type member of an error response points to (public).
    register_error_catalogue_routes(app=app)
    register_static_routes(
        app=app,
        url_prefix="/static",
        static_root=SITE_DIRECTORIES.DIR_STATIC,
    )
    configure_static_url_root(static_root=SITE_DIRECTORIES.DIR_STATIC)
    # The user guide this release shipped with, served from the service
    # itself at /docs (DOC-20); absent when the built site is not installed.
    register_user_guide_routes(app=app)
    register_favicon_route(
        app=app,
        favicon_path=os.path.join(SITE_DIRECTORIES.DIR_STATIC, "favicon.svg"),
    )
    # codecraftai-webworks ships the mj-* component library + chart
    # renderers + design tokens as static assets under its site-
    # packages ``static/`` directory. Mount that directory at
    # ``/mj`` so the shell document can pull in
    # ``/mj/styles/tokens.css`` and ``/mj/javascript/index.js``
    # to register every <mj-*> custom element.
    import ccai.webworks as _ww_pkg
    webworks_static_dir = os.path.join(
        os.path.dirname(_ww_pkg.__file__), "static"
    )
    register_static_routes(
        app=app,
        url_prefix="/mj",
        static_root=webworks_static_dir,
    )
    install_web_ui_templating()
    # Setup wizard routes register BEFORE the rest of the consumer
    # UI so the gate-redirect target ``/setup/unlock`` is bound on
    # the dispatcher early.
    register_setup_routes(app=app)
    register_config_routes(app=app)
    register_resources_routes(app=app)
    register_projects_web_ui_routes(app=app)

    # Site-shell catch-all is registered LAST so every explicit
    # blueprint route wins the dispatcher match. The shell only
    # claims paths no other blueprint owns -- ``/`` and any future
    # routes that have not yet been ported to shell-resident
    # bundles. Per spec ``9-site-shell`` Requirement 1.1 / 3.2,
    # chromeless prefixes (``/login``, ``/logout``, ``/setup``,
    # ``/__health``, ``/errors``) and the API surface are also
    # explicitly skipped by the catch-all.
    install_shell_default_bundles()
    register_shell_catchall(app=app)
    # Startup self-check: warn about any view whose extension registry
    # is empty (audit ORC-04).
    log_view_registry_self_check()
    return


#: Threads per worker for the built-in webworks server when
#: ``PYCHESTRATE_THREADS`` is unset. The server only builds a thread
#: pool for ``worker_class="thread"``; with the default ``"sync"``
#: class it served one connection at a time, so every asset request
#: waited out the previous connection's 2 s keep-alive (10-13 s per
#: page) and one pod long-poll stalled everyone for 30 s.
NATIVE_SERVER_DEFAULT_THREADS = 8


def pychestrate_website_main():
    runtime_config = load_config_from_environment()
    bootstrap_runtime(config=runtime_config)

    # Install the Ed25519 job-envelope signing key from the deploy
    # environment. Best-effort: a misconfiguration degrades the
    # dispatch feature (the signing-key endpoint returns 503) without
    # taking down login or the rest of the API.
    install_envelope_signer_from_environment()

    # Provision the initial-admin token (idempotent; no-op past
    # completion). Logs the on-disk token path so operators see it
    # in journald / stdout immediately.
    session_factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    token_path = bootstrap_setup_state(session_factory=session_factory)
    # flush: stdout redirected to a file is block-buffered, and the
    # server never exits to flush it (LD-11).
    print("Initial-admin token path: {}".format(token_path), flush=True)

    register_service_extensions()

    app.startup()

    install_pychestrate_session_middleware(
        app=app,
        path_prefixes=("/api/v1/", MCP_MIDDLEWARE_PREFIX),
    )

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
    # ADM-16: expose the socket peer so handlers can resolve the real
    # client address behind a trusted proxy.
    wsgi_app = _wrap_with_peer_address(wsgi_app)
    # Cookies carry ``Secure`` for HTTPS requests (direct or through a
    # trusted proxy) and always in production; see cookie_session.
    wsgi_app = wrap_wsgi_app_with_secure_cookie_policy(wsgi_app=wsgi_app)
    # A form posted after the sign-in or its token expired comes back filled in (XC-11).
    wsgi_app = wrap_wsgi_app_with_form_capture(wsgi_app=wsgi_app)
    # Platform layers (security headers + CSP nonce, request metrics)
    # see every response.
    wsgi_app = wrap_platform_wsgi_application(
        wsgi_app=wsgi_app, runtime_environment=runtime_config.runtime_environment,
    )

    # Pod client-certificate identity (clients.mtls_identity): the
    # OUTERMOST wrapper, so it strips client-supplied certificate
    # headers before any other layer reads the environ, and the CN the
    # TLS terminator verified reaches the mTLS routes as
    # ``request.mtls_client_cn``.
    wsgi_app = install_client_certificate_identity(app=app, wsgi_app=wsgi_app)

    bind_host = PychestrateVariables.PYCHESTRATE_BIND_HOST
    bind_port = int(PychestrateVariables.PYCHESTRATE_BIND_PORT)
    workers = int(os.environ.get("PYCHESTRATE_WORKERS", "1"))
    threads = int(os.environ.get("PYCHESTRATE_THREADS", str(NATIVE_SERVER_DEFAULT_THREADS)))
    worker_class = "thread" if threads > 1 else "sync"

    print(
        "Starting native WebWorks WSGI Server on {}:{} (workers={}, threads={}, worker_class={})".format(
            bind_host, bind_port, workers, threads, worker_class
        ),
        flush=True,
    )
    run_server(app=wsgi_app, host=bind_host, port=bind_port,
               workers=workers, threads=threads, worker_class=worker_class)


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

    # Install the Ed25519 job-envelope signing key from the deploy
    # environment. See pychestrate_website_main for the rationale; the
    # production-WSGI factory mirrors the dev entry point exactly.
    install_envelope_signer_from_environment()

    # Provision the initial-admin token. See pychestrate_website_main
    # for the rationale; the production-WSGI factory mirrors the dev
    # entry point exactly.
    session_factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    token_path = bootstrap_setup_state(session_factory=session_factory)
    print("Initial-admin token path: {}".format(token_path), flush=True)

    register_service_extensions()
    app.startup()
    install_pychestrate_session_middleware(
        app=app,
        path_prefixes=("/api/v1/", MCP_MIDDLEWARE_PREFIX),
    )
    install_pychestrate_setup_gate_middleware(
        app=app,
        is_complete=lambda: _is_setup_complete(
            session_factory=SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
        ),
    )

    rtnval_inner = create_wsgi_application(config={"handler": build_wsgi_compat_dispatch(app=app)})
    # ADM-16: expose the socket peer (see pychestrate_website_main).
    rtnval = _wrap_with_peer_address(_eager_start_response_wsgi(rtnval_inner))
    # Cookies carry ``Secure`` for HTTPS requests (direct or through a
    # trusted proxy) and always in production; see cookie_session.
    rtnval = wrap_wsgi_app_with_secure_cookie_policy(wsgi_app=rtnval)
    # A form posted after the sign-in or its token expired comes back filled in (XC-11).
    rtnval = wrap_wsgi_app_with_form_capture(wsgi_app=rtnval)
    # Platform layers (security headers + CSP nonce, request metrics)
    # see every response.
    rtnval = wrap_platform_wsgi_application(
        wsgi_app=rtnval, runtime_environment=runtime_config.runtime_environment,
    )

    # Pod client-certificate identity (clients.mtls_identity), the
    # OUTERMOST wrapper so it strips client-supplied certificate
    # headers before anything else reads the environ; see
    # pychestrate_website_main.
    rtnval = install_client_certificate_identity(app=app, wsgi_app=rtnval)
    return rtnval

if __name__ == "__main__":
    pychestrate_website_main()
