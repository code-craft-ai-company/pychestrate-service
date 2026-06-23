"""
.. module:: variables.factories.variable_resolver
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``variable_resolver`` factory protocol base.

.. moduleauthor:: Code Craft AI LLC

Concrete implementations declare how a variable binding is resolved for
a given (scope, scope_id, name) triple. The M1 reference implementation
is :class:`~variables.factories.database_resolver.DatabaseVariableResolver`
which reads directly from the :class:`VariableBinding` table.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase
from ccai.pychestrate.webservice.variables.models import (
    VariableBinding,
    VariableScope,
)


class VariableResolverProtocol(FactoryProtocolBase):
    """
        Contract for variable resolver implementations.
    """

    factory_protocol_name: ClassVar[str] = "variable_resolver"
    protocol_schema_version: ClassVar[int] = 1

    @classmethod
    def resolve(
            cls,
            *,
            db_session: DbSession,
            scope: VariableScope,
            scope_id: str,
            name: str
        ) -> Optional[VariableBinding]:
        """
            Return the binding for the triple, or None when not present.

            :param db_session: Active SQLAlchemy session.
            :param scope: Target scope.
            :param scope_id: Scope-local identifier.
            :param name: Variable name.

            :returns: The :class:`VariableBinding` or None.
        """
        raise NotImplementedError("Subclasses must implement resolve()")
