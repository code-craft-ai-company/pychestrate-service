"""
.. module:: variables.factories.database_resolver
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference :class:`VariableResolverProtocol` implementation.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.webservice.variables.factories.variable_resolver import (
    VariableResolverProtocol,
)
from ccai.pychestrate.webservice.variables.models import (
    VariableBinding,
    VariableScope,
)
from ccai.pychestrate.webservice.variables import repository as variable_repository


class DatabaseVariableResolver(VariableResolverProtocol):
    """
        Reads a single binding from the :class:`VariableBinding` table.
    """

    factory_protocol_name: ClassVar[str] = "variable_resolver"
    PRECEDENCE: ClassVar[int] = 1000

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
            Return the binding for the given triple, if present.

            :param db_session: Active SQLAlchemy session.
            :param scope: Target scope.
            :param scope_id: Scope-local identifier.
            :param name: Variable name.

            :returns: The :class:`VariableBinding` or None.
        """
        rtnval = variable_repository.get_binding(
            db_session=db_session,
            scope=scope,
            scope_id=scope_id,
            name=name,
        )
        return rtnval
