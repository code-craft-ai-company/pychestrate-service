"""
.. module:: orchestration.infra.environment.factories.k8s_cluster_kind
    :synopsis: K8sClusterEnvironmentKind — reference k8s-cluster env kind.

Required attrs:

* ``cluster_id`` — non-empty string identifying the cluster
  in the operator's CMDB.
* ``region`` — non-empty string region/zone identifier.
* ``api_endpoint`` — URL of the cluster API server.

Optional attrs:

* ``node_pool_count`` — non-negative integer.
* ``capability_tags`` — list of tag strings.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Mapping, Tuple

from ccai.pychestrate.webservice.orchestration.infra.environment.factories.kind_protocol import (
    EnvironmentKindProtocol,
)


K8S_CLUSTER_KIND_NAME: str = "k8s-cluster"


class K8sClusterEnvironmentKind(EnvironmentKindProtocol):
    """
        Reference Kubernetes-cluster environment kind.
    """

    factory_protocol_name: str = "environment_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def kind_name(cls) -> str:
        rtnval = K8S_CLUSTER_KIND_NAME
        return rtnval

    @classmethod
    def attribute_fields(cls) -> List[Dict[str, Any]]:
        rtnval: List[Dict[str, Any]] = [
            {"name": "cluster_id", "label": "Cluster id", "type": "text", "required": True,
             "hint": "how your inventory names this cluster, e.g. prod-east-1"},
            {"name": "region", "label": "Region", "type": "text", "required": True, "hint": "us-east-1"},
            {"name": "api_endpoint", "label": "API endpoint", "type": "url", "required": True,
             "hint": "https://k8s.example.com:6443"},
            {"name": "node_pool_count", "label": "Node pools", "type": "number", "required": False, "hint": "0"},
            {"name": "capability_tags", "label": "Capability tags", "type": "tags", "required": False,
             "hint": "comma-separated, e.g. gpu, arm64"},
        ]
        return rtnval

    @classmethod
    def validate_attrs(
            cls,
            *,
            attrs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []

        for field_name in ("cluster_id", "region", "api_endpoint"):
            value = attrs.get(field_name, None)
            if value is None:
                issues.append("'{}' is required".format(field_name))
                continue
            if not isinstance(value, str) or len(value) == 0:
                issues.append(
                    "'{}' must be a non-empty string".format(field_name),
                )

        api_endpoint = attrs.get("api_endpoint", "")
        if isinstance(api_endpoint, str) and len(api_endpoint) > 0:
            if not (
                api_endpoint.startswith("http://")
                or api_endpoint.startswith("https://")
            ):
                issues.append(
                    "'api_endpoint' must start with http:// or https://",
                )

        node_pool_count = attrs.get("node_pool_count", 0)
        if not isinstance(node_pool_count, int) or node_pool_count < 0:
            issues.append("'node_pool_count' must be a non-negative integer")

        capability_tags = attrs.get("capability_tags", [])
        if not isinstance(capability_tags, list):
            issues.append("'capability_tags' must be a list of strings")
        else:
            for index, tag in enumerate(capability_tags):
                if not isinstance(tag, str) or len(tag) == 0:
                    issues.append(
                        "'capability_tags[{}]' must be a non-empty string".format(
                            index,
                        )
                    )

        if len(issues) > 0:
            rtnval: Tuple[bool, Tuple[str, ...]] = (False, tuple(issues))
            return rtnval
        rtnval = (True, ())
        return rtnval
