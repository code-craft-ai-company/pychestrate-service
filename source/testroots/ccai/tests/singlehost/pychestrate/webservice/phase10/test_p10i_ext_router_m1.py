"""
.. module:: test_p10i_ext_router_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the framework-free ext_router (8-rest-api-v1 T2.5).

.. moduleauthor:: Code Craft AI LLC

The router walks every loaded :class:`RestEndpointExtension` subclass,
validates per-extension descriptors, refuses cross-extension
``ext_name`` collisions, and produces a :class:`MountManifest`. The
M2 HTTP layer consumes the manifest; M1 ships only the discovery +
validation half so it can be exercised without a Flask runtime.

Tests inject synthetic extension class lists via the
``extensions=`` parameter on :func:`mount_extension_routes` so the
collision paths never pollute ``RestEndpointExtension.__subclasses__``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import functools
import gc

from typing import Tuple

from ccai import testbase

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.extensions.ext_router import (
    EXTENSION_ROUTE_NAMESPACE_PREFIX,
    MountedRoute,
    MountManifest,
    discover_extensions,
    manifest_to_jsonable,
    mount_extension_routes,
)
from ccai.pychestrate.webservice.extensions.rest_endpoint_example import (  # noqa: F401
    ExampleEchoEndpoints,
)
from ccai.pychestrate.webservice.extensions.rest_endpoint_protocol import (
    HTTP_METHOD_GET,
    HTTP_METHOD_POST,
    RestEndpointDescriptor,
    RestEndpointExtension,
)


def _releases_synthetic_extensions(test_function):
    """
        Collect garbage as soon as a test that mounts deliberately invalid synthetic extensions returns.

        The router finds extensions through ``RestEndpointExtension.__subclasses__()``, and a class made inside a test sits in a reference cycle,
        so it stays registered until the collector next runs. A leftover class with a duplicate name, a duplicate descriptor, an unsupported
        method or no endpoints makes every later test that mounts all extensions fail with a ConfigurationError, depending only on when the
        collector happened to run (the full suite errored on that in four unrelated tests).
    """
    @functools.wraps(test_function)
    def wrapper():
        try:
            test_function()
        finally:
            gc.collect()
        return
    return wrapper


def _build_extension_class(
        *,
        ext_name: str,
        descriptors: Tuple[RestEndpointDescriptor, ...]
    ):
    """
        Build a fresh :class:`RestEndpointExtension` subclass for
        injection into ``mount_extension_routes(extensions=...)``.

        :param ext_name: ``ext_name`` ClassVar value.
        :param descriptors: Tuple returned by ``declare_endpoints``.

        :returns: New subclass type.
    """

    captured_descriptors = descriptors

    class _Synthetic(RestEndpointExtension):
        @classmethod
        def declare_endpoints(cls) -> Tuple[RestEndpointDescriptor, ...]:
            rtnval = captured_descriptors
            return rtnval

    _Synthetic.ext_name = ext_name
    _Synthetic.__qualname__ = "Synthetic_{}".format(ext_name.replace("-", "_"))
    rtnval = _Synthetic
    return rtnval


def _make_descriptor(
        *,
        method: str = HTTP_METHOD_GET,
        path_suffix: str = "/x"
    ) -> RestEndpointDescriptor:
    rtnval = RestEndpointDescriptor(
        method=method,
        path_suffix=path_suffix,
        required_permissions=tuple(),
        required_capabilities=tuple(),
        description="",
    )
    return rtnval


# ---------------------------------------------------------------------------
# Discovery (live subclass tree)
# ---------------------------------------------------------------------------

def test_discover_extensions_includes_example_reference():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: discover_extensions includes the in-tree
    ExampleEchoEndpoints reference once its module is imported.**
    """
    discovered = discover_extensions()
    seen_names = {cls.ext_name for cls in discovered}
    testbase.assert_equal("example" in seen_names, True)
    return


def test_discover_extensions_skips_classes_without_ext_name():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: discover_extensions filters out subclasses whose
    ``ext_name`` is empty (the abstract case).**
    """
    discovered = discover_extensions()
    for cls in discovered:
        testbase.assert_equal(cls.ext_name != "", True)
    return


# ---------------------------------------------------------------------------
# Happy path against synthetic injection
# ---------------------------------------------------------------------------

def test_mount_routes_renders_full_path_under_namespace_prefix():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: A mounted route's full_path is
    ``/api/v1/ext/<ext-name><suffix>``.**
    """
    alpha_class = _build_extension_class(
        ext_name="alpha",
        descriptors=(_make_descriptor(method=HTTP_METHOD_GET, path_suffix="/items"),),
    )
    manifest = mount_extension_routes(extensions=[alpha_class])
    testbase.assert_equal(len(manifest.routes), 1)
    only_route = manifest.routes[0]
    testbase.assert_equal(
        only_route.full_path, "{}{}{}".format(
            EXTENSION_ROUTE_NAMESPACE_PREFIX, "alpha", "/items"
        )
    )
    testbase.assert_equal(only_route.handler_class is alpha_class, True)
    return


def test_mount_routes_orders_routes_deterministically():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: manifest.routes ordering is stable: ext_name asc,
    method asc, path_suffix asc.**
    """
    alpha_class = _build_extension_class(
        ext_name="zulu",
        descriptors=(
            _make_descriptor(method=HTTP_METHOD_POST, path_suffix="/z"),
            _make_descriptor(method=HTTP_METHOD_GET, path_suffix="/z"),
        ),
    )
    bravo_class = _build_extension_class(
        ext_name="alfa",
        descriptors=(_make_descriptor(method=HTTP_METHOD_GET, path_suffix="/a"),),
    )
    manifest = mount_extension_routes(extensions=[alpha_class, bravo_class])
    sortable = [(r.ext_name, r.method, r.path_suffix) for r in manifest.routes]
    testbase.assert_equal(sortable, sorted(sortable))
    return


def test_mount_routes_preserves_descriptor_metadata():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: required_permissions / required_capabilities flow
    through to the rendered manifest unchanged.**
    """
    descriptor = RestEndpointDescriptor(
        method=HTTP_METHOD_POST,
        path_suffix="/items",
        required_permissions=("system:writer",),
        required_capabilities=("net:outbound",),
        description="create",
    )
    ext_class = _build_extension_class(
        ext_name="meta-test", descriptors=(descriptor,)
    )
    manifest = mount_extension_routes(extensions=[ext_class])
    only_route = manifest.routes[0]
    testbase.assert_equal(only_route.descriptor.required_permissions, ("system:writer",))
    testbase.assert_equal(only_route.descriptor.required_capabilities, ("net:outbound",))
    testbase.assert_equal(only_route.descriptor.description, "create")
    return


def test_manifest_to_jsonable_renders_documented_keys():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: manifest_to_jsonable produces stable per-route dicts
    with the documented keys.**
    """
    ext_class = _build_extension_class(
        ext_name="render-test",
        descriptors=(_make_descriptor(method=HTTP_METHOD_GET, path_suffix="/x"),),
    )
    manifest = mount_extension_routes(extensions=[ext_class])
    rendered = manifest_to_jsonable(manifest=manifest)
    testbase.assert_equal(len(rendered), 1)
    sample = rendered[0]
    for key in (
        "ext_name",
        "method",
        "path_suffix",
        "full_path",
        "handler_class",
        "required_permissions",
        "required_capabilities",
        "description",
    ):
        testbase.assert_equal(key in sample, True)
    return


# ---------------------------------------------------------------------------
# Live discovery integration
# ---------------------------------------------------------------------------

def test_mount_extension_routes_discovers_example_when_extensions_omitted():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: With no extensions argument, mount_extension_routes
    discovers ExampleEchoEndpoints from the live subclass tree.**
    """
    manifest = mount_extension_routes(extensions=None)
    matched = None
    for route in manifest.routes:
        if route.ext_name == "example":
            matched = route
            break
    testbase.assert_equal(matched is not None, True)
    testbase.assert_equal(matched.full_path, "/api/v1/ext/example/echo")
    return


# ---------------------------------------------------------------------------
# Collision: duplicate ext_name across two subclasses
# ---------------------------------------------------------------------------

@_releases_synthetic_extensions
def test_mount_routes_rejects_duplicate_ext_name():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: Two extensions sharing an ext_name fail with
    ConfigurationError naming both classes.**
    """
    first = _build_extension_class(
        ext_name="duplicated",
        descriptors=(_make_descriptor(path_suffix="/a"),),
    )
    second = _build_extension_class(
        ext_name="duplicated",
        descriptors=(_make_descriptor(path_suffix="/b"),),
    )

    raised = False
    error_text = ""
    try:
        mount_extension_routes(extensions=[first, second])
    except ConfigurationError as xcpt:
        raised = True
        error_text = str(xcpt)
    testbase.assert_equal(raised, True)
    testbase.assert_equal("duplicated" in error_text, True)
    testbase.assert_equal("Synthetic_duplicated" in error_text, True)
    return


# ---------------------------------------------------------------------------
# Collision: duplicate (method, path_suffix) within a single extension
# ---------------------------------------------------------------------------

@_releases_synthetic_extensions
def test_mount_routes_rejects_internal_duplicate_descriptor():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: A single subclass declaring two descriptors with the
    same (method, path_suffix) fails with ConfigurationError.**
    """
    duplicate_descriptor = _make_descriptor(
        method=HTTP_METHOD_GET, path_suffix="/same"
    )
    ext_class = _build_extension_class(
        ext_name="dup-desc-test",
        descriptors=(duplicate_descriptor, duplicate_descriptor),
    )

    raised = False
    error_text = ""
    try:
        mount_extension_routes(extensions=[ext_class])
    except ConfigurationError as xcpt:
        raised = True
        error_text = str(xcpt)
    testbase.assert_equal(raised, True)
    testbase.assert_equal("dup-desc-test" in error_text, True)
    testbase.assert_equal("/same" in error_text, True)
    return


def test_a_deliberately_invalid_extension_does_not_stay_registered_after_its_test():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: with the garbage collector switched off, a test that mounts an extension with a duplicate descriptor leaves no synthetic
    extension class registered, so a later test that mounts every extension is not broken by it.**
    """
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        test_mount_routes_rejects_internal_duplicate_descriptor()
        lingering = sorted(
            str(getattr(subclass, "ext_name", None)) for subclass in RestEndpointExtension.__subclasses__()
            if "Synthetic" in subclass.__qualname__
        )
    finally:
        if was_enabled:
            gc.enable()
    testbase.assert_equal(lingering, [])
    return


# ---------------------------------------------------------------------------
# Per-descriptor invariants
# ---------------------------------------------------------------------------

@_releases_synthetic_extensions
def test_mount_routes_rejects_unsupported_method():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: A descriptor with a non-canonical HTTP method fails
    with ConfigurationError.**
    """
    bad = RestEndpointDescriptor(
        method="OPTIONS",
        path_suffix="/anything",
        required_permissions=tuple(),
        required_capabilities=tuple(),
        description="",
    )
    ext_class = _build_extension_class(
        ext_name="bad-method-test", descriptors=(bad,)
    )
    raised = False
    try:
        mount_extension_routes(extensions=[ext_class])
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


@_releases_synthetic_extensions
def test_mount_routes_rejects_path_suffix_without_leading_slash():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: A descriptor whose path_suffix lacks a leading '/' is
    rejected.**
    """
    bad = RestEndpointDescriptor(
        method=HTTP_METHOD_GET,
        path_suffix="echo",
        required_permissions=tuple(),
        required_capabilities=tuple(),
        description="",
    )
    ext_class = _build_extension_class(
        ext_name="bad-suffix-test", descriptors=(bad,)
    )
    raised = False
    try:
        mount_extension_routes(extensions=[ext_class])
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


@_releases_synthetic_extensions
def test_mount_routes_rejects_extension_with_no_endpoints():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: An extension whose declare_endpoints returns an empty
    tuple is rejected — silent zero-route extensions hide bugs.**
    """
    ext_class = _build_extension_class(ext_name="empty-test", descriptors=tuple())
    raised = False
    try:
        mount_extension_routes(extensions=[ext_class])
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# ---------------------------------------------------------------------------
# MountedRoute / MountManifest dataclass invariants
# ---------------------------------------------------------------------------

def test_mounted_route_is_frozen():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: MountedRoute is a frozen dataclass.**
    """
    descriptor = _make_descriptor()
    route = MountedRoute(
        ext_name="x",
        method=HTTP_METHOD_GET,
        path_suffix="/x",
        full_path="/api/v1/ext/x/x",
        handler_class=ExampleEchoEndpoints,
        descriptor=descriptor,
    )
    raised = False
    try:
        route.ext_name = "y"
    except Exception:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_mount_manifest_routes_default_to_empty_tuple():
    """
    **Feature: 8-rest-api-v1 (T2.5 partial)**
    **Property: MountManifest constructed without arguments yields an
    empty routes tuple.**
    """
    manifest = MountManifest()
    testbase.assert_equal(manifest.routes, tuple())
    return
