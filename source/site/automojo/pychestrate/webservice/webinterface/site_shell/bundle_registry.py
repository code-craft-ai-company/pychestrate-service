"""
.. module:: webinterface.site_shell.bundle_registry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Server-side mirror of which feature bundles the
               shell document should import for which route prefix.

.. moduleauthor:: Automation Mojo LLC

The bundles themselves live under
``webinterface/static/javascript/dist/<name>.js`` (committed; the
Python deploy ships them as static files). This module records the
``route_prefix -> bundle_name`` mapping so
``shell_document.render_shell_document`` can emit only the
``<script type="module" src=...>`` tags relevant to the current
request, not every bundle in the tree.

M1 registers a single entry: ``"" -> "pyc-site-shell"`` -- the
shell itself loads for every shell-served path. PR4 will register
the admin / project / run-detail bundles per route prefix.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Dict, List, Optional


_module_logger = logging.getLogger(__name__)


# Module-level state. Kept simple intentionally -- one mapping,
# one accessor, one mutator. A more elaborate registry can grow
# later if PR4-6 surfaces need richer routing.
_REGISTERED_BUNDLES: Dict[str, List[str]] = {}


def reset_for_testing() -> None:
    """
        Clear the module-level state so unit tests do not leak.

        :returns: None.
    """
    _REGISTERED_BUNDLES.clear()
    return


def register_bundle(
        *,
        route_prefix: str,
        bundle_name: str
    ) -> None:
    """
        Register a feature bundle for a route prefix. The shell
        document includes the bundle's ``<script>`` tag when the
        request path starts with ``route_prefix``. Pass
        ``route_prefix=""`` to register a bundle for every shell-
        served path (used for the shell itself).

        Idempotent on duplicate ``(route_prefix, bundle_name)``
        pairs.

        :param route_prefix: Path prefix the bundle activates on
                             (e.g. ``"/admin"``).
        :param bundle_name: Bundle base name (e.g.
                            ``"pyc-site-shell"``;
                            ``"pyc-admin-ui"``). Maps to
                            ``/static/javascript/dist/<name>.js``.

        :returns: None.
    """
    if route_prefix is None:
        route_prefix = ""
    if bundle_name is None or len(bundle_name) == 0:
        raise ValueError(
            "register_bundle requires a non-empty bundle_name"
        )
    bucket = _REGISTERED_BUNDLES.get(route_prefix)
    if bucket is None:
        bucket = []
        _REGISTERED_BUNDLES[route_prefix] = bucket
    if bundle_name in bucket:
        return
    bucket.append(bundle_name)
    return


def bundles_for(*, path: str) -> List[str]:
    """
        Return the ordered list of bundle names whose registered
        ``route_prefix`` matches the supplied request path. The
        ``""`` prefix always matches (used for shell-wide
        bundles).

        :param path: Incoming request path.

        :returns: List of bundle base names. The shell bundle
                  (registered under prefix ``""``) appears first
                  by convention; per-route bundles follow.
    """
    rtnval: List[str] = []
    if path is None:
        path = ""

    # The shell-wide bucket goes first.
    shell_wide = _REGISTERED_BUNDLES.get("")
    if shell_wide is not None:
        for bundle_name in shell_wide:
            if bundle_name not in rtnval:
                rtnval.append(bundle_name)

    # Then any per-prefix buckets, longest-prefix-first so the
    # rendered tag order is "most specific last" (mirrors the
    # CSS cascade convention).
    candidates = []
    for prefix, bundle_names in _REGISTERED_BUNDLES.items():
        if prefix == "":
            continue
        if path.startswith(prefix) is True:
            candidates.append((prefix, bundle_names))
    candidates.sort(key=lambda pair: len(pair[0]))
    for _, bundle_names in candidates:
        for bundle_name in bundle_names:
            if bundle_name not in rtnval:
                rtnval.append(bundle_name)

    return rtnval


def install_default_bundles() -> None:
    """
        Register the M1 default bundles plus the PR4 admin bundle.
        Called once during ``register_service_extensions`` so the
        shell document has something to emit.

        Bundles registered here:

        * ``pyc-site-shell`` -- prefix ``""`` -- shell itself,
          loaded on every shell-served path.
        * ``pyc-admin-bundle`` -- prefix ``/admin`` -- admin
          sidebar registration, loaded only on ``/admin/*`` paths.
        * ``pyc-runs-bundle`` -- prefix ``/runs`` -- runs list
          sidebar registration plus the ``<pyc-runs-list>`` view,
          loaded only on ``/runs`` and ``/runs/*`` paths.
        * ``pyc-catalog-bundle`` -- prefix ``/test-catalog`` --
          test-catalog sidebar registration plus the
          ``<pyc-test-catalog>`` view (catalog table, import action,
          per-entry trigger-run action), loaded only on
          ``/test-catalog`` and ``/test-catalog/*`` paths.
        * ``pyc-builds-bundle`` -- prefix ``/builds`` -- builds
          sidebar registration plus the ``<pyc-builds-list>`` and
          ``<pyc-build-detail>`` views (builds table, trigger-build
          action, build detail with artifacts), loaded only on
          ``/builds`` and ``/builds/*`` paths.
        * ``pyc-infra-bundle`` -- prefixes ``/environments`` and
          ``/provisioning-runs`` -- infrastructure / provisioning
          sidebar registration plus the ``<pyc-environments>``,
          ``<pyc-provisioning-list>`` and
          ``<pyc-provisioning-detail>`` views (environments table
          with drift status, provisioning-runs table, trigger
          actions, provisioning detail with plan summary), loaded
          only on ``/environments``, ``/provisioning-runs`` and
          their sub-paths.
        * ``pyc-metrics-bundle`` -- prefixes ``/test-metrics``,
          ``/timeseries`` and ``/dashboards`` -- metrics &
          dashboards sidebar registration plus the
          ``<pyc-test-metrics>``, ``<pyc-timeseries-explorer>``,
          ``<pyc-dashboards-list>`` and ``<pyc-dashboard-detail>``
          views (test-result rollup, timeseries explorer with an
          inline-SVG chart, dashboards list / detail with metric
          tiles), loaded only on those prefixes and their
          sub-paths.
        * ``pyc-secrets-bundle`` -- prefix ``/secrets`` -- secrets
          sidebar registration plus the ``<pyc-secrets>`` view
          (scope-aware Org / Project / User secret-metadata table,
          create form, per-secret reveal / rotate / delete
          actions), loaded only on ``/secrets`` and ``/secrets/*``
          paths.
        * ``pyc-pods-bundle`` -- prefixes ``/pods`` and
          ``/clients`` -- fleet (pods & clients) sidebar
          registration plus the ``<pyc-pods-list>``,
          ``<pyc-pod-detail>``, ``<pyc-clients-list>`` and
          ``<pyc-client-detail>`` views (pod-definitions table with
          member counts, pod detail with runtime state /
          registration / lifecycle history, enrolled-clients table
          with liveness, client detail with capabilities), loaded
          only on ``/pods``, ``/clients`` and their sub-paths.

        :returns: None.
    """
    register_bundle(route_prefix="", bundle_name="pyc-site-shell")
    register_bundle(route_prefix="/admin", bundle_name="pyc-admin-bundle")
    register_bundle(route_prefix="/runs", bundle_name="pyc-runs-bundle")
    register_bundle(
        route_prefix="/test-catalog", bundle_name="pyc-catalog-bundle"
    )
    register_bundle(route_prefix="/builds", bundle_name="pyc-builds-bundle")
    register_bundle(
        route_prefix="/environments", bundle_name="pyc-infra-bundle"
    )
    register_bundle(
        route_prefix="/provisioning-runs", bundle_name="pyc-infra-bundle"
    )
    register_bundle(
        route_prefix="/test-metrics", bundle_name="pyc-metrics-bundle"
    )
    register_bundle(
        route_prefix="/timeseries", bundle_name="pyc-metrics-bundle"
    )
    register_bundle(
        route_prefix="/dashboards", bundle_name="pyc-metrics-bundle"
    )
    register_bundle(
        route_prefix="/secrets", bundle_name="pyc-secrets-bundle"
    )
    register_bundle(route_prefix="/pods", bundle_name="pyc-pods-bundle")
    register_bundle(
        route_prefix="/clients", bundle_name="pyc-pods-bundle"
    )
    return


def get_registered_bundles_snapshot() -> Dict[str, List[str]]:
    """
        Return a defensive snapshot of the registered bundles
        mapping. Intended for diagnostics and tests.

        :returns: Dict mapping route prefix to list of bundle
                  names.
    """
    rtnval: Dict[str, List[str]] = {}
    for prefix, bundle_names in _REGISTERED_BUNDLES.items():
        rtnval[prefix] = list(bundle_names)
    return rtnval


__all__ = [
    "register_bundle",
    "bundles_for",
    "install_default_bundles",
    "reset_for_testing",
    "get_registered_bundles_snapshot",
]
