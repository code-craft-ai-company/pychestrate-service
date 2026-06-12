"""
.. module:: orchestration.test.factories.testbase_runner
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: TestbaseRunnerKind — reference test runner.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Mapping

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import (
    TestCatalogEntrySnapshot,
)
from ccai.pychestrate.webservice.orchestration.test.factories.runner_protocol import (
    TestRunnerKindProtocol,
)


TESTBASE_RUNNER_KIND: str = "testbase"


class TestbaseRunnerKind(TestRunnerKindProtocol):
    """
        Reference runner. Validates that ``inputs.includes`` is a
        list of strings and produces the params dict the testbase
        client agent expects:
        ``{"runner": "testbase", "root": <str>, "includes": [...],
        "extras": {...}}``.
    """

    factory_protocol_name: str = "test_runner_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def runner_kind(cls) -> str:
        rtnval = TESTBASE_RUNNER_KIND
        return rtnval

    @classmethod
    def validate_inputs(
            cls,
            *,
            snapshot: TestCatalogEntrySnapshot,
            inputs: Mapping[str, Any]
        ) -> None:
        errors = []
        includes_raw = inputs.get("includes", None) if inputs is not None else None
        if includes_raw is None:
            errors.append("'includes' is required")
        elif isinstance(includes_raw, list) is False:
            errors.append("'includes' must be a list of strings")
        else:
            for item in includes_raw:
                if isinstance(item, str) is False:
                    errors.append(
                        "'includes' entry is not a string: {!r}".format(item)
                    )

        root_raw = inputs.get("root", None) if inputs is not None else None
        if root_raw is not None and isinstance(root_raw, str) is False:
            errors.append("'root' must be a string when supplied")

        if len(errors) == 0:
            return

        err_lines = ["Invalid testbase runner inputs."]
        err_lines.append("CATALOG_ENTRY: {}".format(snapshot.entry_id))
        err_lines.append("ERRORS: ({})".format(len(errors)))
        for err in errors:
            err_lines.append("    {}".format(err))
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None

    @classmethod
    def build_envelope_params(
            cls,
            *,
            snapshot: TestCatalogEntrySnapshot,
            inputs: Mapping[str, Any]
        ) -> Mapping[str, Any]:
        cls.validate_inputs(snapshot=snapshot, inputs=inputs)
        rtnval = {
            "runner": TESTBASE_RUNNER_KIND,
            "root": inputs.get("root", snapshot.raw_metadata.get("root", "")),
            "includes": list(inputs.get("includes", [])),
            "extras": dict(inputs.get("extras", {}) or {}),
        }
        return rtnval
