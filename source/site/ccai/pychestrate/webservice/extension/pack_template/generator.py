"""
.. module:: extension.pack_template.generator
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Render a versioned pack-template corpus into a target directory.

.. moduleauthor:: Code Craft AI LLC

The generator is the core M1 surface: ``PackGenerator.generate`` walks
the corpus manifest, renders each file as Jinja2 or copies bytes
through, substitutes the ``__NAME__`` placeholder in destination paths,
and writes the result under ``<target_dir>/pychestrate-ext-<name>/``.

Atomicity (full temp-tree-then-rename) lands in M3 / T3.1; the M1
implementation writes incrementally but refuses to start when the
target directory already contains files (Requirement 1.2). That keeps
M1 honest: it cannot half-overwrite a real pack.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re
import unicodedata

from pathlib import Path
from typing import Dict, List, Optional

import jinja2

from ccai.errors.exceptions import ConfigurationError, SemanticError

from ccai.pychestrate.webservice.extension.pack_template.corpus_loader import (
    builtin_corpus_root,
    discover_corpus_versions,
    load_template_manifest,
)
from ccai.pychestrate.webservice.extension.pack_template.models import (
    COPY_RENDER_MODE,
    JINJA_RENDER_MODE,
    PackGenerationRequest,
    PackTemplateFile,
)


NAME_PLACEHOLDER: str = "__NAME__"
PACK_DIRECTORY_PREFIX: str = "pychestrate-ext-"

_VALID_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
_DASH_RUN_PATTERN = re.compile(r"-+")


def normalize_pack_name(*, raw: str) -> str:
    """
        Normalize a caller-supplied pack name to ``^[a-z][a-z0-9-]*$``.

        Steps:

        1. Strip surrounding whitespace and lower-case.
        2. NFKD-decompose, drop combining marks, encode/decode as ASCII
           with strict ignore so non-ASCII characters are dropped.
        3. Replace any sequence of non-``[a-z0-9]`` characters with a
           single ``-``.
        4. Strip leading / trailing ``-``.
        5. Collapse runs of ``-``.
        6. If empty after the prior steps, raise :class:`SemanticError`.
        7. If the first character is not ``[a-z]``, prefix ``ext-``.

        Idempotent: calling :func:`normalize_pack_name` on its own output
        returns the input unchanged.

        :param raw: Caller-supplied raw name.

        :returns: Normalized name string.
        :raises: SemanticError on inputs that produce an empty result.
    """
    stripped = raw.strip().lower()
    if len(stripped) == 0:
        err_msg_lines = ["Pack name cannot be empty."]
        err_msg_lines.append("RAW_INPUT: {!r}".format(raw))
        err_msg = os.linesep.join(err_msg_lines)
        raise SemanticError(err_msg) from None

    decomposed = unicodedata.normalize("NFKD", stripped)
    ascii_only_bytes = decomposed.encode("ascii", "ignore")
    ascii_only = ascii_only_bytes.decode("ascii")

    replaced_chars: List[str] = []
    for ch in ascii_only:
        if ch.isalnum():
            replaced_chars.append(ch)
        else:
            replaced_chars.append("-")
    replaced = "".join(replaced_chars)

    collapsed = _DASH_RUN_PATTERN.sub("-", replaced)
    trimmed = collapsed.strip("-")

    if len(trimmed) == 0:
        err_msg_lines = ["Pack name reduced to empty after normalization."]
        err_msg_lines.append("RAW_INPUT: {!r}".format(raw))
        err_msg = os.linesep.join(err_msg_lines)
        raise SemanticError(err_msg) from None

    first_char = trimmed[0]
    if not (first_char >= "a" and first_char <= "z"):
        prefixed = "ext-" + trimmed
    else:
        prefixed = trimmed

    if not _VALID_NAME_PATTERN.match(prefixed):
        err_msg_lines = ["Normalized pack name failed final validation."]
        err_msg_lines.append("RAW_INPUT: {!r}".format(raw))
        err_msg_lines.append("NORMALIZED: {!r}".format(prefixed))
        err_msg = os.linesep.join(err_msg_lines)
        raise SemanticError(err_msg) from None

    rtnval = prefixed
    return rtnval


def _render_destination_relative(*, relative_path: str, normalized_name: str) -> str:
    """
        Substitute ``__NAME__`` in a corpus relative path.

        :param relative_path: Corpus-side relative path.
        :param normalized_name: Normalized pack name.

        :returns: Destination relative path string.
    """
    # A directory in the package path must be importable, and a Python module
    # name has no hyphen: the distribution keeps the hyphenated name
    # (``pychestrate-ext-demo-notes``), the packages use ``demo_notes``.
    rtnval = relative_path.replace(NAME_PLACEHOLDER, normalized_name.replace("-", "_"))
    return rtnval


def _build_template_environment(*, corpus_root: Path, version: int) -> jinja2.Environment:
    """
        Build a Jinja2 environment rooted at the corpus version directory.

        :param corpus_root: Corpus root containing ``vN`` subdirectories.
        :param version: Integer version being rendered.

        :returns: Configured :class:`jinja2.Environment`.
    """
    version_root = corpus_root / "v{}".format(version)
    loader = jinja2.FileSystemLoader(str(version_root))
    rtnval = jinja2.Environment(
        loader=loader,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
        undefined=jinja2.StrictUndefined,
    )
    return rtnval


def _build_render_context(*, request: PackGenerationRequest, template_version: int) -> Dict:
    """
        Build the Jinja2 render context exposed to every template.

        :param request: Caller-supplied :class:`PackGenerationRequest`.
        :param template_version: The corpus version being rendered.

        :returns: Dict of named variables.
    """
    author_value = request.author if request.author is not None else ""
    license_value = request.license if request.license is not None else ""
    rtnval = {
        "name": request.normalized_name,
        "raw_name": request.name,
        "author": author_value,
        "license": license_value,
        "protocol_names": list(request.protocol_names),
        "resource_base_names": list(request.resource_base_names),
        "template_version": template_version,
        "first_protocol_name": (
            request.protocol_names[0] if len(request.protocol_names) > 0 else "example_protocol"
        ),
        "first_resource_base_name": (
            request.resource_base_names[0]
            if len(request.resource_base_names) > 0
            else "ResourceKindExtension"
        ),
    }
    return rtnval


class PackGenerator:
    """
        Render the in-tree corpus into a target directory.
    """

    def __init__(self, *, corpus_root: Optional[Path]) -> None:
        """
            :param corpus_root: Override path for the corpus root. Pass
                                ``None`` to use the in-tree corpus shipped
                                alongside this module.
        """
        self._corpus_root: Path = corpus_root if corpus_root is not None else builtin_corpus_root()
        self._available_versions: tuple = discover_corpus_versions(corpus_root=self._corpus_root)
        if len(self._available_versions) == 0:
            err_msg_lines = ["Corpus root has no version directories."]
            err_msg_lines.append("PATH: {}".format(self._corpus_root))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg) from None
        return

    def list_versions(self) -> List[int]:
        """
            List every integer corpus version present.

            :returns: Sorted list of versions.
        """
        rtnval = list(self._available_versions)
        return rtnval

    def latest_version(self) -> int:
        """
            Return the highest available corpus version.

            :returns: Integer version.
        """
        rtnval = self._available_versions[-1]
        return rtnval

    def generate(
            self,
            *,
            request: PackGenerationRequest,
            template_version: Optional[int]
        ) -> Path:
        """
            Render the corpus into ``<target_dir>/pychestrate-ext-<name>/``.

            :param request: Caller-supplied :class:`PackGenerationRequest`.
            :param template_version: Override version. ``None`` selects
                                     :func:`latest_version`.

            :returns: Absolute path to the generated pack root.
            :raises: ConfigurationError on bad inputs / target collisions.
        """
        if template_version is None:
            chosen_version = self.latest_version()
        else:
            chosen_version = template_version
            if chosen_version not in self._available_versions:
                err_msg_lines = ["Requested template_version is not available."]
                err_msg_lines.append("REQUESTED: {}".format(chosen_version))
                err_msg_lines.append("AVAILABLE: {}".format(self._available_versions))
                err_msg = os.linesep.join(err_msg_lines)
                raise ConfigurationError(err_msg) from None

        target_dir = request.target_dir
        if not target_dir.is_dir():
            err_msg_lines = ["Target parent directory does not exist."]
            err_msg_lines.append("PATH: {}".format(target_dir))
            err_msg = os.linesep.join(err_msg_lines)
            raise ConfigurationError(err_msg) from None

        pack_dir_name = PACK_DIRECTORY_PREFIX + request.normalized_name
        pack_root = target_dir / pack_dir_name
        if pack_root.exists():
            if pack_root.is_dir() and any(pack_root.iterdir()):
                err_msg_lines = ["Refusing to overwrite non-empty pack directory."]
                err_msg_lines.append("PATH: {}".format(pack_root))
                err_msg = os.linesep.join(err_msg_lines)
                raise ConfigurationError(err_msg) from None
            if pack_root.is_file():
                err_msg_lines = ["Target pack path exists as a file."]
                err_msg_lines.append("PATH: {}".format(pack_root))
                err_msg = os.linesep.join(err_msg_lines)
                raise ConfigurationError(err_msg) from None

        manifest = load_template_manifest(
            corpus_root=self._corpus_root, version=chosen_version
        )
        environment = _build_template_environment(
            corpus_root=self._corpus_root, version=chosen_version
        )
        render_context = _build_render_context(
            request=request, template_version=chosen_version
        )

        pack_root.mkdir(parents=True, exist_ok=True)

        for template_file in manifest.files:
            self._materialize_file(
                pack_root=pack_root,
                template_file=template_file,
                environment=environment,
                render_context=render_context,
                normalized_name=request.normalized_name,
                template_version=chosen_version,
            )

        rtnval = pack_root
        return rtnval

    def _materialize_file(
            self,
            *,
            pack_root: Path,
            template_file: PackTemplateFile,
            environment: jinja2.Environment,
            render_context: Dict,
            normalized_name: str,
            template_version: int
        ) -> None:
        """
            Write a single corpus file into the destination tree.

            :param pack_root: Generated pack root directory.
            :param template_file: Single :class:`PackTemplateFile` entry.
            :param environment: Active Jinja2 environment.
            :param render_context: Jinja2 render context.
            :param normalized_name: Normalized pack name.
            :param template_version: Active corpus version (used for the
                                     ``_meta.yaml`` baseline marker).

            :returns: None.
        """
        destination_relative = _render_destination_relative(
            relative_path=template_file.relative_path,
            normalized_name=normalized_name,
        )
        destination_path = pack_root / destination_relative
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        if template_file.render_mode == COPY_RENDER_MODE:
            byte_content = template_file.source_path.read_bytes()
            destination_path.write_bytes(byte_content)
            return

        if template_file.render_mode == JINJA_RENDER_MODE:
            template_relative_for_loader = str(
                template_file.source_path.relative_to(
                    self._corpus_root / "v{}".format(template_version)
                )
            )
            template = environment.get_template(template_relative_for_loader)
            rendered = template.render(**render_context)
            destination_path.write_text(rendered, encoding="utf-8")
            return

        err_msg_lines = ["Unknown render_mode."]
        err_msg_lines.append("VALUE: {}".format(template_file.render_mode))
        err_msg_lines.append("PATH: {}".format(template_file.source_path))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None
