"""
.. module:: test_p15c_variables_resolver_chain_m2
    :synopsis: Tests for P15c — 2-global-variables M2
               resolver chain with fail-over.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, Optional

from automojo import testbase

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.variables.factories.variable_resolver import (
    VariableResolverProtocol,
)
from automojo.pychestrate.webservice.variables.models import (
    VariableBinding,
    VariableScope,
    VariableValueType,
)
from automojo.pychestrate.webservice.variables.resolver_chain import (
    ChainResult,
    ResolverFallover,
    resolve_through_chain,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    return


def _make_binding(*, name: str = "FAKE_VAR") -> VariableBinding:
    rtnval = VariableBinding(
        binding_id=new_uuid(),
        scope=VariableScope.SYSTEM,
        scope_id="",
        name=name,
        value_type=VariableValueType.STRING,
        value_text="resolved",
        set_by_user_id=None,
    )
    return rtnval


# -------------------------------------
# Test fixtures
# -------------------------------------

class _LowPrecedenceResolver(VariableResolverProtocol):
    """
        Test fixture — runs first (lower PRECEDENCE wins).
    """
    factory_protocol_name: ClassVar[str] = "variable_resolver"
    PRECEDENCE: ClassVar[int] = 100
    SHOULD_RETURN_BINDING: ClassVar[bool] = False
    RAISE: ClassVar[Optional[type]] = None

    @classmethod
    def resolve(cls, *, db_session, scope, scope_id, name):
        if cls.RAISE is not None:
            raise cls.RAISE("simulated_low_precedence_failure")
        if cls.SHOULD_RETURN_BINDING is True:
            return _make_binding(name=name)
        return None


class _HighPrecedenceResolver(VariableResolverProtocol):
    """
        Test fixture — runs second (higher PRECEDENCE).
    """
    factory_protocol_name: ClassVar[str] = "variable_resolver"
    PRECEDENCE: ClassVar[int] = 1000
    SHOULD_RETURN_BINDING: ClassVar[bool] = True

    @classmethod
    def resolve(cls, *, db_session, scope, scope_id, name):
        if cls.SHOULD_RETURN_BINDING is True:
            return _make_binding(name=name)
        return None


def _setup_fixtures(*, low_returns=False, low_raise=None, high_returns=True):
    _LowPrecedenceResolver.SHOULD_RETURN_BINDING = low_returns
    _LowPrecedenceResolver.RAISE = low_raise
    _HighPrecedenceResolver.SHOULD_RETURN_BINDING = high_returns
    register_factory_implementation(implementation=_LowPrecedenceResolver)
    register_factory_implementation(implementation=_HighPrecedenceResolver)
    return


# -------------------------------------
# Order + first-non-None semantics
# -------------------------------------

def test_chain_returns_first_non_none_binding():
    """
    **Feature: 2-global-variables (M2)**
    **Property: the chain returns the binding from the
    lowest-PRECEDENCE resolver that produces one.**
    """
    _prepare_runtime()
    _setup_fixtures(low_returns=True, high_returns=True)
    _engine, session = build_in_memory_session()
    result = resolve_through_chain(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="FAKE_VAR",
    )
    testbase.assert_equal(result.binding is not None, True)
    testbase.assert_equal(
        "_LowPrecedenceResolver" in result.resolved_by, True,
    )
    testbase.assert_equal(result.fallovers, ())
    return


def test_chain_falls_through_to_higher_precedence_when_lower_returns_none():
    """
    **Feature: 2-global-variables (M2)**
    **Property: when the lowest-PRECEDENCE resolver returns
    None, the chain advances to the next resolver and uses
    its binding.**
    """
    _prepare_runtime()
    _setup_fixtures(low_returns=False, high_returns=True)
    _engine, session = build_in_memory_session()
    result = resolve_through_chain(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="FAKE_VAR",
    )
    testbase.assert_equal(result.binding is not None, True)
    testbase.assert_equal(
        "_HighPrecedenceResolver" in result.resolved_by, True,
    )
    testbase.assert_equal(result.fallovers, ())
    return


def test_chain_returns_none_when_no_resolver_finds_binding():
    """
    **Feature: 2-global-variables (M2)**
    **Property: the chain returns ChainResult(binding=None)
    when every resolver returns None.**
    """
    _prepare_runtime()
    _setup_fixtures(low_returns=False, high_returns=False)
    _engine, session = build_in_memory_session()
    result = resolve_through_chain(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="FAKE_VAR",
    )
    testbase.assert_equal(result.binding, None)
    testbase.assert_equal(result.resolved_by, "")
    testbase.assert_equal(result.fallovers, ())
    return


def test_chain_returns_none_with_no_resolvers_registered():
    """
    **Feature: 2-global-variables (M2)**
    **Property: the chain returns ChainResult(binding=None)
    when the registry is empty.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    result = resolve_through_chain(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="FAKE_VAR",
    )
    testbase.assert_equal(result.binding, None)
    testbase.assert_equal(result.resolved_by, "")
    return


# -------------------------------------
# Recoverable exception fail-over
# -------------------------------------

def test_chain_failovers_past_timeout_error():
    """
    **Feature: 2-global-variables (M2)**
    **Property: a TimeoutError from the lowest-PRECEDENCE
    resolver is recorded as a ResolverFallover and the chain
    advances to the next resolver.**
    """
    _prepare_runtime()
    _setup_fixtures(low_raise=TimeoutError, high_returns=True)
    _engine, session = build_in_memory_session()
    result = resolve_through_chain(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="FAKE_VAR",
    )
    testbase.assert_equal(result.binding is not None, True)
    testbase.assert_equal(
        "_HighPrecedenceResolver" in result.resolved_by, True,
    )
    testbase.assert_equal(len(result.fallovers), 1)
    testbase.assert_equal(result.fallovers[0].reason, "TimeoutError")
    return


def test_chain_failovers_past_connection_error():
    """
    **Feature: 2-global-variables (M2)**
    **Property: ConnectionError is treated as recoverable.**
    """
    _prepare_runtime()
    _setup_fixtures(low_raise=ConnectionError, high_returns=True)
    _engine, session = build_in_memory_session()
    result = resolve_through_chain(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="FAKE_VAR",
    )
    testbase.assert_equal(result.binding is not None, True)
    testbase.assert_equal(len(result.fallovers), 1)
    testbase.assert_equal(result.fallovers[0].reason, "ConnectionError")
    return


def test_chain_failovers_past_os_error():
    """
    **Feature: 2-global-variables (M2)**
    **Property: OSError is treated as recoverable.**
    """
    _prepare_runtime()
    _setup_fixtures(low_raise=OSError, high_returns=True)
    _engine, session = build_in_memory_session()
    result = resolve_through_chain(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="FAKE_VAR",
    )
    testbase.assert_equal(result.binding is not None, True)
    testbase.assert_equal(len(result.fallovers), 1)
    testbase.assert_equal(result.fallovers[0].reason, "OSError")
    return


def test_chain_returns_none_when_every_resolver_failovers():
    """
    **Feature: 2-global-variables (M2)**
    **Property: when every resolver in the chain raises a
    recoverable exception the chain returns
    ChainResult(binding=None) plus the per-resolver fallover
    records.**
    """
    _prepare_runtime()
    _LowPrecedenceResolver.RAISE = TimeoutError

    class _AlwaysFails(VariableResolverProtocol):
        factory_protocol_name: ClassVar[str] = "variable_resolver"
        PRECEDENCE: ClassVar[int] = 2000

        @classmethod
        def resolve(cls, *, db_session, scope, scope_id, name):
            raise ConnectionError("downstream_unavailable")

    register_factory_implementation(implementation=_LowPrecedenceResolver)
    register_factory_implementation(implementation=_AlwaysFails)
    _engine, session = build_in_memory_session()
    result = resolve_through_chain(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="FAKE_VAR",
    )
    testbase.assert_equal(result.binding, None)
    testbase.assert_equal(len(result.fallovers), 2)
    return


# -------------------------------------
# Programmer errors bubble unchanged
# -------------------------------------

def test_chain_bubbles_semantic_error():
    """
    **Feature: 2-global-variables (M2)**
    **Property: SemanticError is a programmer error and must
    bubble unchanged — the chain does NOT failover.**
    """
    _prepare_runtime()

    class _BadResolver(VariableResolverProtocol):
        factory_protocol_name: ClassVar[str] = "variable_resolver"
        PRECEDENCE: ClassVar[int] = 100

        @classmethod
        def resolve(cls, *, db_session, scope, scope_id, name):
            raise SemanticError("contract_violation")

    register_factory_implementation(implementation=_BadResolver)
    _engine, session = build_in_memory_session()
    raised = False
    try:
        resolve_through_chain(
            db_session=session,
            scope=VariableScope.SYSTEM,
            scope_id="",
            name="FAKE_VAR",
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_chain_bubbles_not_implemented_error():
    """
    **Feature: 2-global-variables (M2)**
    **Property: NotImplementedError marks a subclass that
    failed to override resolve — the chain bubbles
    unchanged.**
    """
    _prepare_runtime()

    class _UnimplementedResolver(VariableResolverProtocol):
        factory_protocol_name: ClassVar[str] = "variable_resolver"
        PRECEDENCE: ClassVar[int] = 100

    register_factory_implementation(implementation=_UnimplementedResolver)
    _engine, session = build_in_memory_session()
    raised = False
    try:
        resolve_through_chain(
            db_session=session,
            scope=VariableScope.SYSTEM,
            scope_id="",
            name="FAKE_VAR",
        )
    except NotImplementedError:
        raised = True
    testbase.assert_equal(raised, True)
    return
