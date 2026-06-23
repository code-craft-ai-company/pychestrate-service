"""
.. module:: extension.pack_template.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Dataclasses describing pack-template inputs and corpus shape.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


COPY_RENDER_MODE: str = "copy"
JINJA_RENDER_MODE: str = "jinja"


@dataclass(frozen=True)
class PackTemplateFile:
    """
        Single file in a corpus version.

        :param relative_path: Destination path relative to the generated
                              pack root, with ``__NAME__`` placeholders
                              still embedded.
        :param source_path: Absolute path to the corpus source file.
        :param render_mode: ``"jinja"`` to evaluate as a Jinja2 template,
                            ``"copy"`` to emit byte-for-byte.
    """
    relative_path: str
    source_path: Path
    render_mode: str


@dataclass(frozen=True)
class PackTemplateManifest:
    """
        Collected description of a single corpus version.

        :param template_version: Integer version (``v1`` -> ``1``).
        :param files: Tuple of :class:`PackTemplateFile`.
    """
    template_version: int
    files: Tuple[PackTemplateFile, ...]


@dataclass(frozen=True)
class PackGenerationRequest:
    """
        Caller-supplied parameters for a single ``new`` invocation.

        :param name: Raw user-supplied name (may be mixed-case / contain
                     underscores). The generator normalizes via
                     :func:`normalize_pack_name`.
        :param normalized_name: The normalized name written into
                                ``pychestrate_ext.yaml`` and used for
                                package directory naming.
        :param author: Optional author / org string.
        :param license: Optional SPDX-style license identifier.
        :param protocol_names: Tuple of factory-protocol names the pack
                               will implement (e.g.,
                               ``("object_store_driver",)``). Used to
                               seed sample factory stubs.
        :param resource_base_names: Tuple of resource extension base
                                    names the pack will register kinds
                                    under (e.g., ``("ResourceKindExtension",)``).
        :param target_dir: Filesystem directory under which the
                           ``pychestrate-ext-<name>/`` tree is materialized.
    """
    name: str
    normalized_name: str
    author: Optional[str]
    license: Optional[str]
    protocol_names: Tuple[str, ...]
    resource_base_names: Tuple[str, ...]
    target_dir: Path
