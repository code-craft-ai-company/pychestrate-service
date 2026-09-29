"""
.. module:: test_p31q_docs_site_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The documentation site holds the manual, the REST API
               reference and the plugin catalog (DOC-05).

.. moduleauthor:: Code Craft AI LLC

The only Sphinx site built to an index and two empty category pages: the
catalog walker read the catalog before anything had registered the
built-in extensions, so it found none of the 22 entries the running
service publishes, and the test that should have caught it looped over
the empty catalog and passed. The user manual was in a separate site and
the REST API reference was in none.

The manual's site now takes the reference and the catalog when built with
``-t reference`` (``make docs``). These tests hold that: a fresh process
finds the catalog the service publishes, an empty catalog stops the
build, and a real build contains all three parts.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import shutil
import subprocess
import sys
import tempfile

from typing import Any, Dict, List, Tuple

from ccai import testbase

from ccai.pychestrate.webservice.extension.docs_ext import check_catalog_not_empty
from ccai.pychestrate.webservice.plugin_api.catalog_builder import (
    Catalog,
    CatalogEntry,
)
from ccai.pychestrate.webservice.plugin_api import (
    PUBLISHED_STATUS_SUPPORTED,
    PublishedSurfaceMetadata,
)


#: Published entries that only the full import of the service reaches:
#: registering the three bootstrap phases alone misses them.
ONLY_IN_THE_FULL_LOAD = {
    "protocols": {"backup_storage_backend", "rpa_job_type", "rpa_execution_mode"},
    "resources": {"MetricDefinitionExtension"},
}

CATALOG_OF_A_FRESH_PROCESS = r"""
import json
from ccai.pychestrate.webservice.extension.docs_ext import load_builtin_declarations
from ccai.pychestrate.webservice.plugin_api.runtime import get_active_catalog
load_builtin_declarations()
catalog = get_active_catalog()
print("CATALOG_JSON=" + json.dumps({
    "protocols": sorted(entry.name for entry in catalog.factory_entries),
    "resources": sorted(entry.name for entry in catalog.resource_entries),
}))
"""


def _repo_root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "userguide")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    return current


def _environment() -> Dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([entry for entry in sys.path if entry])
    return env


def _entry(name: str, kind: str) -> CatalogEntry:
    rtnval = CatalogEntry(
        name=name,
        kind=kind,
        protocol_schema_version=1,
        metadata=PublishedSurfaceMetadata(
            status=PUBLISHED_STATUS_SUPPORTED,
            min_schema_version=1,
            deprecation_date=None,
            sunset_date=None,
            docs_url="https://docs.example.com/x",
            reference="example.module.Impl",
        ),
        declaring_class_qualname="example.module.Declaring",
    )
    return rtnval


def test_a_fresh_process_finds_the_catalog_the_service_publishes():
    """
    **Feature: documentation site (DOC-05)**
    **Property: in a new process, loading the built-in declarations
    fills the catalog, including the entries that only the full import
    of the service reaches.**
    """
    done = subprocess.run(
        [sys.executable, "-c", CATALOG_OF_A_FRESH_PROCESS],
        cwd=_repo_root(), env=_environment(), capture_output=True, text=True, timeout=300,
    )
    lines = [line for line in done.stdout.splitlines() if line.startswith("CATALOG_JSON=")]
    testbase.assert_equal((done.returncode, len(lines)), (0, 1), done.stderr[-1500:])
    found: Dict[str, List[str]] = json.loads(lines[0][len("CATALOG_JSON="):])

    missing = {
        category: sorted(expected - set(found[category]))
        for category, expected in ONLY_IN_THE_FULL_LOAD.items()
    }
    testbase.assert_equal(
        (len(found["protocols"]) >= 10, len(found["resources"]) >= 5, missing),
        (True, True, {"protocols": [], "resources": []}),
        str(found),
    )
    return


def test_an_empty_catalog_stops_the_build():
    """
    **Feature: documentation site (DOC-05)**
    **Property: a catalog with no factory protocols, or no resource
    extensions, is refused with an error naming what is missing; one
    with both is accepted.**
    """
    from sphinx.errors import ExtensionError

    refused: List[str] = []
    for label, catalog in (
        ("nothing", Catalog()),
        ("no resources", Catalog(factory_entries=(_entry("alpha", "factory_protocol"),))),
        ("no protocols", Catalog(resource_entries=(_entry("Beta", "resource_extension"),))),
    ):
        try:
            check_catalog_not_empty(catalog=catalog)
        except ExtensionError as error:
            refused.append("{}: {}".format(label, str(error)))

    check_catalog_not_empty(catalog=Catalog(
        factory_entries=(_entry("alpha", "factory_protocol"),),
        resource_entries=(_entry("Beta", "resource_extension"),),
    ))

    testbase.assert_equal(
        (len(refused), "factory protocols" in refused[0] and "resource extensions" in refused[0],
         "resource extensions" in refused[1], "factory protocols" in refused[2]),
        (3, True, True, True),
        str(refused),
    )
    return


def _build_site(*, output: str) -> Tuple[int, str]:
    root = _repo_root()
    done = subprocess.run(
        [sys.executable, "-m", "sphinx", "-W", "--keep-going", "-t", "reference", "-q",
         "-b", "html", "-d", os.path.join(output, "doctrees"), "userguide", os.path.join(output, "html")],
        cwd=root, env=_environment(), capture_output=True, text=True, timeout=600,
    )
    return (done.returncode, (done.stdout + done.stderr)[-2500:])


def test_the_built_site_holds_the_manual_the_reference_and_the_catalog():
    """
    **Feature: documentation site (DOC-05)**
    **Property: a build with warnings as errors succeeds and contains
    the manual (searchable), the REST API reference with the same
    contract as the repository's document, and a catalog page for every
    published entry; the manual links to the reference.**
    """
    root = _repo_root()
    generated = [os.path.join(root, "userguide", "extensions"), os.path.join(root, "userguide", "_reference")]
    already_there = [path for path in generated if os.path.exists(path)]
    output = tempfile.mkdtemp(prefix="pychestrate-docs-site-")
    try:
        status, log = _build_site(output=output)
        testbase.assert_equal(status, 0, log)
        site = os.path.join(output, "html")

        with open(os.path.join(site, "api-reference", "openapi.json"), "r", encoding="utf-8") as handle:
            reference = json.load(handle)
        import yaml
        with open(os.path.join(root, "specs", "openapi", "pychestrate.yaml"), "r", encoding="utf-8") as handle:
            contract = yaml.safe_load(handle)
        with open(os.path.join(site, "searchindex.js"), "r", encoding="utf-8") as handle:
            search_index = handle.read()
        with open(os.path.join(site, "01-00-overview.html"), "r", encoding="utf-8") as handle:
            overview = handle.read()
        protocol_pages = sorted(os.listdir(os.path.join(site, "extensions", "protocols")))
        resource_pages = sorted(os.listdir(os.path.join(site, "extensions", "resources")))

        testbase.assert_equal(
            (
                reference["info"]["version"] == contract["info"]["version"],
                len(reference["paths"]) == len(contract["paths"]),
                os.path.getsize(os.path.join(site, "api-reference", "redoc.standalone.js")) > 100000,
                os.path.isfile(os.path.join(site, "api-reference", "index.html")),
                'href="api-reference/index.html"' in overview,
                "deploy" in search_index and "environment" in search_index,
                len(protocol_pages) >= 11 and "rpa_job_type.html" in protocol_pages,
                len(resource_pages) >= 6,
                os.path.isfile(os.path.join(site, "21-00-environment-reference.html")),
            ),
            (True,) * 9,
        )
    finally:
        for path in generated:
            if path not in already_there:
                shutil.rmtree(path, ignore_errors=True)
        shutil.rmtree(output, ignore_errors=True)
    return
