"""
.. module:: pods.factories.libvirt_provisioner
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference LibvirtProvisioner stub for 3-dynamic-pods M1.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, Mapping

from ccai.pychestrate.webservice.pods.factories.provisioner import (
    PodProvisionerProtocol,
    ProvisionOutcome,
)


class LibvirtProvisioner(PodProvisionerProtocol):
    """
        Reference M1 stub. Real libvirt integration lands alongside the
        infrastructure-orchestration work. The M1 implementation records
        that provisioning would run and returns success so materialization
        pipelines can be exercised end-to-end in tests.
    """

    factory_protocol_name: ClassVar[str] = "pod_provisioner"
    provisioner_name: ClassVar[str] = "libvirt"
    required_capabilities: ClassVar[frozenset] = frozenset({"hypervisor.libvirt"})
    PRECEDENCE: ClassVar[int] = 100

    @classmethod
    def provision(
            cls,
            *,
            rendered_spec: Mapping[str, Any]
        ) -> ProvisionOutcome:
        member_count = 0
        if rendered_spec is not None:
            members = rendered_spec.get("members", None)
            if isinstance(members, list) is True:
                member_count = len(members)

        rtnval = ProvisionOutcome(
            provisioned=True,
            detail="M1 stub — would provision {} members via libvirt".format(member_count),
        )
        return rtnval
