"""
.. module:: test_p31zzzf_environment_kinds_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The environment kinds are listed with the attributes each takes (ORC-17).

.. moduleauthor:: Code Craft AI LLC

The register-environment form asked for a kind name (its placeholder,
"terraform", is not a kind that exists; only ``k8s-cluster`` is) and for a JSON
object whose example, ``{"region": "us-east-1"}``, is missing two of the three
attributes the kind requires. ``GET /api/v1/environment-kinds`` now lists the
loaded kinds with the attributes each takes, so the form can offer the real
choices.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Dict, Optional

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.orchestration.infra.environment import register_builtin_extensions
from ccai.pychestrate.webservice.orchestration.infra.environment import service as environment_service
from ccai.pychestrate.webservice.orchestration.infra.environment.factories.k8s_cluster_kind import K8sClusterEnvironmentKind
from ccai.pychestrate.webservice.orchestration.infra.restapi.v1 import environments_routes


class _Request:
    def __init__(self) -> None:
        self.path = "/api/v1/environment-kinds"
        self.path_params: Dict[str, Any] = {}
        self.query_params = type("Q", (), {"get": staticmethod(lambda key, default=None: default)})()
        self.db_session = object()
        self.auth_principal = type("Principal", (), {"user_id": "user-1"})()


class _Allowed:
    allowed = True
    reason = ""


def test_the_loaded_kind_is_listed_with_every_attribute_it_requires():
    """
    **Feature: registry-fed forms (ORC-17)**
    **Property: ``list_kinds`` names ``k8s-cluster`` with fields for
    ``cluster_id``, ``region`` and ``api_endpoint`` (required) and
    ``node_pool_count`` and ``capability_tags`` (optional), and a kind that
    describes nothing has no fields.**
    """
    reset_registry_for_testing()
    register_builtin_extensions()
    kinds = environment_service.list_kinds()
    fields = {field["name"]: field for field in kinds[0]["fields"]}

    testbase.assert_equal(
        (
            [entry["kind"] for entry in kinds],
            sorted(name for name, field in fields.items() if field["required"]),
            sorted(name for name, field in fields.items() if not field["required"]),
            fields["api_endpoint"]["type"], fields["node_pool_count"]["type"], fields["capability_tags"]["type"],
        ),
        (["k8s-cluster"], ["api_endpoint", "cluster_id", "region"], ["capability_tags", "node_pool_count"], "url", "number", "tags"),
    )
    return


def test_every_required_field_of_the_kind_is_described_so_a_form_cannot_omit_one():
    """
    **Feature: registry-fed forms (ORC-17)**
    **Property: a payload built from the described required fields alone is
    accepted by the kind's own validator, and one missing a described required
    field is refused.**
    """
    described = [field for field in K8sClusterEnvironmentKind.attribute_fields() if field["required"]]
    complete = {field["name"]: ("https://k8s.example.test" if field["type"] == "url" else "x") for field in described}
    incomplete = dict(complete)
    incomplete.pop(described[0]["name"])

    testbase.assert_equal(
        (K8sClusterEnvironmentKind.validate_attrs(attrs=complete)[0], K8sClusterEnvironmentKind.validate_attrs(attrs=incomplete)[0]),
        (True, False),
    )
    return


def test_the_route_returns_the_kinds_to_a_caller_who_may_read_environments():
    """
    **Feature: registry-fed forms (ORC-17)**
    **Property: ``GET /api/v1/environment-kinds`` answers 200 ``{items}`` for a
    permitted caller and 403 for one who may not read environments.**
    """
    reset_registry_for_testing()
    register_builtin_extensions()
    outcomes = []
    for allowed in (True, False):
        patch = create_module_patch(environments_routes.rbac_evaluator, "check_permission")
        mock = patch.activate()
        decision = type("D", (), {"allowed": allowed, "reason": ""})()
        mock.configure(side_effect=lambda **kwargs: decision)
        try:
            response = environments_routes.handle_list_environment_kinds(_Request())
        finally:
            patch.deactivate()
        outcomes.append((response.status_code, [item["kind"] for item in json.loads(response.body.decode("utf-8")).get("items", [])] if response.status_code == 200 else None))

    testbase.assert_equal(outcomes, [(200, ["k8s-cluster"]), (403, None)])
    return
