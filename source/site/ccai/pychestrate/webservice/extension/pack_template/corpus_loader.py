"""
.. module:: extension.pack_template.corpus_loader
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Walk a corpus version directory into a :class:`PackTemplateManifest`.

.. moduleauthor:: Code Craft AI LLC

The corpus is laid out as a tree of files alongside the generator code.
Each file is treated as either a Jinja2 template (any path ending in
``.jinja``) or an opaque copy. The loader produces a deterministic
manifest: walking the corpus root in sorted order so generated packs
have a stable file ordering.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from pathlib import Path
from typing import List, Tuple

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.extension.pack_template.models import (
    COPY_RENDER_MODE,
    JINJA_RENDER_MODE,
    PackTemplateFile,
    PackTemplateManifest,
)


JINJA_SUFFIX: str = ".jinja"


def discover_corpus_versions(*, corpus_root: Path) -> Tuple[int, ...]:
    """
        List integer versions present under ``corpus_root``.

        :param corpus_root: Directory containing ``v1/``, ``v2/``, ...

        :returns: Sorted tuple of integer versions.
        :raises: ConfigurationError if ``corpus_root`` does not exist.
    """
    if not corpus_root.is_dir():
        err_msg_lines = ["Corpus root is not a directory."]
        err_msg_lines.append("PATH: {}".format(corpus_root))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    discovered: List[int] = []
    for entry in corpus_root.iterdir():
        if not entry.is_dir():
            continue
        entry_name = entry.name
        if not entry_name.startswith("v"):
            continue
        version_suffix = entry_name[1:]
        if not version_suffix.isdigit():
            continue
        version_int = int(version_suffix)
        discovered.append(version_int)

    discovered.sort()
    rtnval = tuple(discovered)
    return rtnval


def load_template_manifest(*, corpus_root: Path, version: int) -> PackTemplateManifest:
    """
        Load every file under ``corpus_root / vN`` into a manifest.

        :param corpus_root: Directory containing version subtrees.
        :param version: Integer version to load.

        :returns: :class:`PackTemplateManifest`.
        :raises: ConfigurationError if the version directory is missing.
    """
    version_root = corpus_root / "v{}".format(version)
    if not version_root.is_dir():
        err_msg_lines = ["Corpus version directory not found."]
        err_msg_lines.append("CORPUS_ROOT: {}".format(corpus_root))
        err_msg_lines.append("VERSION: {}".format(version))
        err_msg = os.linesep.join(err_msg_lines)
        raise ConfigurationError(err_msg) from None

    files: List[PackTemplateFile] = []
    for source_path in sorted(version_root.rglob("*")):
        if not source_path.is_file():
            continue
        relative_to_version = source_path.relative_to(version_root)
        relative_str = str(relative_to_version)
        if relative_str.endswith(JINJA_SUFFIX):
            destination_relative = relative_str[: -len(JINJA_SUFFIX)]
            render_mode = JINJA_RENDER_MODE
        else:
            destination_relative = relative_str
            render_mode = COPY_RENDER_MODE
        files.append(
            PackTemplateFile(
                relative_path=destination_relative,
                source_path=source_path,
                render_mode=render_mode,
            )
        )

    rtnval = PackTemplateManifest(
        template_version=version,
        files=tuple(files),
    )
    return rtnval


def builtin_corpus_root() -> Path:
    """
        Return the absolute path of the in-tree corpus root.

        :returns: Path to ``…/extension/pack_template/corpus``.
    """
    rtnval = Path(__file__).parent / "corpus"
    return rtnval
