"""
.. module:: variables.resolver_chain
    :synopsis: Walk registered variable_resolver impls with fail-over.

The chain calls each registered
:class:`VariableResolverProtocol` implementation in
``PRECEDENCE`` order. The first impl that returns a binding
wins. When an impl raises a *recoverable* error
(:class:`TimeoutError`, :class:`ConnectionError`,
:class:`OSError`) the chain logs the failover and tries the
next impl. Programmer errors
(:class:`NotImplementedError`, :class:`SemanticError`) bubble
unchanged so a misconfigured resolver doesn't get silently
masked by the rest of the chain.

The M3 hardening layer wraps this chain with a 503 surface
when every resolver fails; M2 returns ``None`` so callers
that have a default value can keep moving.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.variables.factories.variable_resolver import (
    VariableResolverProtocol,
)
from automojo.pychestrate.webservice.variables.models import (
    VariableBinding,
    VariableScope,
)


logger = logging.getLogger(__name__)


_RECOVERABLE_EXCEPTIONS: Tuple[type, ...] = (
    TimeoutError,
    ConnectionError,
    OSError,
)


@dataclass(frozen=True)
class ResolverFallover:
    """
        One per-resolver failure recorded during a chain walk.

        :param resolver: Qualname of the resolver that failed.
        :param reason: Stable token (the exception class).
        :param detail: Exception message.
    """
    resolver: str
    reason: str
    detail: str


@dataclass(frozen=True)
class ChainResult:
    """
        Outcome of :func:`resolve_through_chain`.

        :param binding: The first non-None binding the chain
                        produced; ``None`` when no resolver
                        returned a binding.
        :param resolved_by: Qualname of the resolver that
                            produced ``binding``; empty when
                            the chain returned ``None``.
        :param fallovers: Per-resolver failure records for
                          the resolvers that raised a
                          recoverable exception.
    """
    binding: Optional[VariableBinding]
    resolved_by: str = ""
    fallovers: Tuple[ResolverFallover, ...] = ()


def resolve_through_chain(
        *,
        db_session: DbSession,
        scope: VariableScope,
        scope_id: str,
        name: str
    ) -> ChainResult:
    """
        Walk every registered :class:`VariableResolverProtocol`
        in PRECEDENCE order. Return the first non-None
        binding plus a fallover record for every resolver
        that raised a recoverable exception along the way.

        :raises: SemanticError unchanged (programmer error);
                 NotImplementedError unchanged (subclass
                 contract violation).
    """
    resolvers = _list_resolvers()
    fallovers: List[ResolverFallover] = []
    for resolver_cls in resolvers:
        try:
            binding = resolver_cls.resolve(
                db_session=db_session,
                scope=scope,
                scope_id=scope_id,
                name=name,
            )
        except SemanticError:
            raise
        except NotImplementedError:
            raise
        except _RECOVERABLE_EXCEPTIONS as resolver_err:
            qualname = getattr(
                resolver_cls, "__qualname__", str(resolver_cls),
            )
            logger.warning(
                "variable_resolver.failover resolver=%s reason=%s",
                qualname,
                type(resolver_err).__name__,
            )
            fallovers.append(ResolverFallover(
                resolver=qualname,
                reason=type(resolver_err).__name__,
                detail=str(resolver_err),
            ))
            continue
        if binding is not None:
            qualname = getattr(
                resolver_cls, "__qualname__", str(resolver_cls),
            )
            rtnval = ChainResult(
                binding=binding,
                resolved_by=qualname,
                fallovers=tuple(fallovers),
            )
            return rtnval
    rtnval = ChainResult(
        binding=None,
        resolved_by="",
        fallovers=tuple(fallovers),
    )
    return rtnval


def _list_resolvers() -> List[Type[VariableResolverProtocol]]:
    candidates = list_factory_implementations(
        factory_protocol_name=VariableResolverProtocol.factory_protocol_name,
    )
    rtnval = list(candidates)
    return rtnval
