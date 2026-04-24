"""
.. module:: pods.factories.integrity_validator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference IntegrityValidator for pod specs.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, List, Mapping

from automojo.pychestrate.webservice.pods.factories.validator import (
    PodSpecValidatorProtocol,
    ValidationReport,
)


class IntegrityValidator(PodSpecValidatorProtocol):
    """
        Minimum viable validator: every spec must carry a ``members``
        list whose entries have a ``kind`` string and a unique ``name``.
    """

    factory_protocol_name: ClassVar[str] = "pod_spec_validator"
    PRECEDENCE: ClassVar[int] = 10

    @classmethod
    def validate(cls, *, spec: Mapping[str, Any]) -> ValidationReport:
        errors: List[str] = []

        if spec is None or isinstance(spec, Mapping) is False:
            errors.append("spec must be a mapping")
            rtnval = ValidationReport(ok=False, errors=errors)
            return rtnval

        members = spec.get("members", None)
        if members is None or isinstance(members, list) is False:
            errors.append("spec.members must be a list")
            rtnval = ValidationReport(ok=False, errors=errors)
            return rtnval

        seen_names = set()
        for index, member in enumerate(members):
            if isinstance(member, Mapping) is False:
                errors.append("members[{}] must be a mapping".format(index))
                continue
            kind = member.get("kind", None)
            if kind is None or len(str(kind).strip()) == 0:
                errors.append("members[{}].kind is required".format(index))
            name = member.get("name", None)
            if name is None or len(str(name).strip()) == 0:
                errors.append("members[{}].name is required".format(index))
                continue
            if name in seen_names:
                errors.append("members[{}].name '{}' is not unique".format(index, name))
            seen_names.add(name)

        rtnval = ValidationReport(ok=(len(errors) == 0), errors=errors)
        return rtnval
