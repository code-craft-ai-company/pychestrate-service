"""
.. module:: extension.pack_template
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Cookiecutter-style starter generator for ``pychestrate-ext-<name>`` packs.

.. moduleauthor:: Automation Mojo LLC

This subsystem produces a working ``pychestrate-ext-<name>`` source tree
from a vendored versioned corpus. The corpus lives next to the generator
so that regressions are caught by the service's own CI rather than at
extension-author time. The CLI entry point lives in
:mod:`extension.pack_template.cli` and is wired to the
``pychestrate-admin`` console script declared by the service's
``pyproject.toml``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extension.pack_template.generator import (
    PackGenerator,
    normalize_pack_name,
)
from automojo.pychestrate.webservice.extension.pack_template.models import (
    PackGenerationRequest,
    PackTemplateFile,
    PackTemplateManifest,
)


__all__ = [
    "PackGenerator",
    "PackGenerationRequest",
    "PackTemplateFile",
    "PackTemplateManifest",
    "normalize_pack_name",
]
