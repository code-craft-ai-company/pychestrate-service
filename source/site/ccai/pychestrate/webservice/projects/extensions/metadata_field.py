"""
.. module:: projects.extensions.metadata_field
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ProjectMetadataFieldExtension — extend Project.extension_fields.

.. moduleauthor:: Code Craft AI LLC

Each concrete subclass contributes one extension field to the Project
aggregate. The field is validated against its declared spec when the
service writes ``extension_fields`` during PATCH.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, ClassVar, FrozenSet, Optional

from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension
from ccai.pychestrate.webservice.projects.exceptions import MetadataFieldValidationError


class ProjectMetadataFieldExtension(ResourceExtension):
    """
        Base class for a project metadata field.
    """

    resource_extension_name: ClassVar[str] = "project_metadata_field"
    field_name: ClassVar[str] = ""
    field_type: ClassVar[str] = "string"
    required: ClassVar[bool] = False
    default_value: ClassVar[Any] = None
    enum_values: ClassVar[Optional[FrozenSet[str]]] = None
    description: ClassVar[str] = ""
    source_extension: ClassVar[str] = ""

    @classmethod
    def validate_value(cls, *, value: Any) -> None:
        """
            Validate ``value`` against the declared spec. Subclasses may
            extend with stricter semantic checks.

            :param value: Candidate value.

            :returns: None.
            :raises: MetadataFieldValidationError
        """
        if value is None:
            if cls.required is True:
                err_msg = "Metadata field '{}' is required.".format(cls.field_name)
                raise MetadataFieldValidationError(err_msg)
            return

        if cls.field_type == "string":
            if isinstance(value, str) is False:
                err_msg = "Field '{}' expects a string.".format(cls.field_name)
                raise MetadataFieldValidationError(err_msg)

        elif cls.field_type == "integer":
            if isinstance(value, bool) is True or isinstance(value, int) is False:
                err_msg = "Field '{}' expects an integer.".format(cls.field_name)
                raise MetadataFieldValidationError(err_msg)

        elif cls.field_type == "boolean":
            if isinstance(value, bool) is False:
                err_msg = "Field '{}' expects a boolean.".format(cls.field_name)
                raise MetadataFieldValidationError(err_msg)

        elif cls.field_type == "url":
            if isinstance(value, str) is False or len(value.strip()) == 0:
                err_msg = "Field '{}' expects a non-empty URL string.".format(cls.field_name)
                raise MetadataFieldValidationError(err_msg)
            if value.startswith("http://") is False and value.startswith("https://") is False:
                err_msg = "Field '{}' must start with http:// or https://.".format(cls.field_name)
                raise MetadataFieldValidationError(err_msg)

        elif cls.field_type == "enum":
            if cls.enum_values is None:
                err_msg = "Field '{}' declared enum without enum_values.".format(cls.field_name)
                raise MetadataFieldValidationError(err_msg)
            if value not in cls.enum_values:
                err_msg = "Field '{}' value '{}' not in allowed set.".format(cls.field_name, value)
                raise MetadataFieldValidationError(err_msg)

        else:
            err_msg = "Field '{}' declares unknown field_type '{}'.".format(cls.field_name, cls.field_type)
            raise MetadataFieldValidationError(err_msg)

        return
