"""
.. module:: orchestration.infra.drift.factories.terraform_checker
    :synopsis: TerraformDriftChecker — reference Terraform drift checker.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Tuple

from ccai.pychestrate.webservice.orchestration.infra.drift.factories.checker_protocol import (
    DriftCheckerProtocol,
)


TERRAFORM_DRIFT_CHECKER_NAME: str = "terraform"
TERRAFORM_SUPPORTED_ENV_KINDS: Tuple[str, ...] = ("k8s-cluster",)


class TerraformDriftChecker(DriftCheckerProtocol):
    """
        Reference Terraform drift checker. Supports the
        Layer-7 in-tree :class:`K8sClusterEnvironmentKind` at
        M1; M2 widens the env-kind list as new kinds register.
    """

    factory_protocol_name: str = "drift_checker"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def checker_name(cls) -> str:
        rtnval = TERRAFORM_DRIFT_CHECKER_NAME
        return rtnval

    @classmethod
    def supported_environment_kinds(cls) -> Tuple[str, ...]:
        rtnval = TERRAFORM_SUPPORTED_ENV_KINDS
        return rtnval
