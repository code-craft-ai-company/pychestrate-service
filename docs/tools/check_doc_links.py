#!/usr/bin/env python3
"""
    Check the links in the repository's documentation.

    Every relative link in the Markdown and reStructuredText documents
    (the READMEs, CONTRIBUTING, DEVELOPING, SECURITY, CHANGELOG, ROADMAP, AGENTS, the user
    manual, the runbooks, and the docs site sources) must point at a
    file or directory that exists, and a ``#fragment`` on a link to a
    Markdown or reStructuredText document must name one of that
    document's headings or targets. External (``http``, ``https``,
    ``mailto``) links are counted but not fetched: CI must not fail
    because a third-party site is slow, and many of the repository's
    external links point at private repositories.

    Run from anywhere::

        python3 docs/tools/check_doc_links.py

    Exit status: 0 when every link resolves, 1 otherwise. Needs
    ``docutils`` (installed with Sphinx) to read reStructuredText.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import glob
import io
import os
import re
import sys
import unicodedata

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

import docutils.core
import docutils.nodes


REPO_ROOT: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: The documents checked, as globs relative to the repository root.
DOCUMENT_GLOBS: Tuple[str, ...] = (
    "*.md",
    "*.rst",
    ".github/**/*.md",
    "alembic/*.rst",
    "deployment/*.md",
    "docs/*.rst",
    "source/testroots/README.md",
    "userguide/*.rst",
)

_EXTERNAL_SCHEMES: Tuple[str, ...] = ("http://", "https://", "mailto:", "ftp://")

_MD_FENCE = re.compile(r"^\s*(```|~~~)")
_MD_INLINE_CODE = re.compile(r"`[^`\n]*`")
_MD_LINK = re.compile(r"!?\[(?:[^\]\[]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_MD_REFERENCE_DEFINITION = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$")
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_MD_HTML_ANCHOR = re.compile(r"""<a\s+(?:name|id)=["']([^"']+)["']""")


@dataclass(frozen=True)
class Link:
    """
        One link found in a document.

        :param source: Repository-relative path of the document.
        :param line: Line number of the link (best effort for RST).
        :param target: The link target as written.
    """
    source: str
    line: int
    target: str


def _document_paths() -> List[str]:
    """
        Expand :data:`DOCUMENT_GLOBS` into repository-relative paths.

        :returns: Sorted, de-duplicated paths.
    """
    found: Set[str] = set()
    for pattern in DOCUMENT_GLOBS:
        for path in glob.glob(os.path.join(REPO_ROOT, pattern), recursive=True):
            if os.path.isfile(path) and "/_build/" not in path:
                found.add(os.path.relpath(path, REPO_ROOT))
    rtnval = sorted(found)
    return rtnval


def _github_slug(heading: str) -> str:
    """
        Compute the anchor GitHub gives a Markdown heading.

        :param heading: The heading text, without the ``#`` marks.

        :returns: The slug: lower case, punctuation removed, spaces
                  replaced by hyphens.
    """
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = text.replace("`", "").lower()
    kept = []
    for char in text:
        category = unicodedata.category(char)
        if char in (" ", "-", "_") or category[0] in ("L", "N"):
            kept.append(char)
    rtnval = "".join(kept).replace(" ", "-")
    return rtnval


def _markdown_links(*, relpath: str, text: str) -> List[Link]:
    """
        Extract the link targets of a Markdown document, skipping fenced
        code blocks and inline code.

        :param relpath: Repository-relative path of the document.
        :param text: The document.

        :returns: The links found.
    """
    links: List[Link] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if _MD_FENCE.match(line) is not None:
            in_fence = not in_fence
            continue
        if in_fence is True:
            continue
        definition = _MD_REFERENCE_DEFINITION.match(line)
        if definition is not None:
            links.append(Link(source=relpath, line=number, target=definition.group(1)))
            continue
        for match in _MD_LINK.finditer(_MD_INLINE_CODE.sub("", line)):
            links.append(Link(source=relpath, line=number, target=match.group(1)))
    rtnval = links
    return rtnval


def _markdown_anchors(*, text: str) -> Set[str]:
    """
        Collect the anchors a Markdown document offers: heading slugs
        (with GitHub's ``-1``, ``-2`` suffixes for repeats) and explicit
        ``<a name=...>`` anchors.

        :param text: The document.

        :returns: The anchor names.
    """
    anchors: Set[str] = set()
    counts: Dict[str, int] = {}
    in_fence = False
    for line in text.splitlines():
        if _MD_FENCE.match(line) is not None:
            in_fence = not in_fence
            continue
        if in_fence is True:
            continue
        heading = _MD_HEADING.match(line)
        if heading is not None:
            slug = _github_slug(heading.group(1))
            seen = counts.get(slug, 0)
            anchors.add(slug if seen == 0 else "{}-{}".format(slug, seen))
            counts[slug] = seen + 1
        for anchor in _MD_HTML_ANCHOR.findall(line):
            anchors.add(anchor)
    rtnval = anchors
    return rtnval


def _parse_rst(*, relpath: str, text: str) -> Tuple[docutils.nodes.document, str]:
    """
        Parse a reStructuredText document with plain docutils, the way
        GitHub renders it.

        :param relpath: Repository-relative path, for messages.
        :param text: The document.

        :returns: The parsed document tree and the warnings and errors
                  docutils reported (Sphinx-only directives and roles
                  among them, which callers ignore).
    """
    stream = io.StringIO()
    doctree = docutils.core.publish_doctree(
        text,
        source_path=os.path.join(REPO_ROOT, relpath),
        settings_overrides={
            "report_level": 2,
            "halt_level": 5,
            "warning_stream": stream,
            "file_insertion_enabled": False,
            "raw_enabled": False,
        },
    )
    rtnval = (doctree, stream.getvalue())
    return rtnval


def _line_of(*, text: str, needle: str) -> int:
    """
        Find the line on which ``needle`` first appears (docutils does
        not record line numbers for inline references).

        :param text: The document.
        :param needle: The text to look for.

        :returns: The 1-based line number, or 0 when not found.
    """
    position = text.find(needle)
    if position < 0:
        return 0
    rtnval = text.count("\n", 0, position) + 1
    return rtnval


def _rst_links(*, relpath: str, text: str, doctree: docutils.nodes.document) -> List[Link]:
    """
        Extract the link targets of a parsed reStructuredText document:
        hyperlink references with a URI and image URIs.

        :param relpath: Repository-relative path of the document.
        :param text: The document, for line numbers.
        :param doctree: The parsed document.

        :returns: The links found.
    """
    finder = getattr(doctree, "findall", None) or doctree.traverse
    links: List[Link] = []
    for reference in finder(docutils.nodes.reference):
        uri = reference.get("refuri", None)
        if uri is not None and len(uri) > 0:
            links.append(Link(source=relpath, line=_line_of(text=text, needle=uri), target=uri))
    for image in finder(docutils.nodes.image):
        uri = image.get("uri", None)
        if uri is not None and len(uri) > 0:
            links.append(Link(source=relpath, line=_line_of(text=text, needle=uri), target=uri))
    rtnval = links
    return rtnval


def _rst_anchors(*, doctree: docutils.nodes.document) -> Set[str]:
    """
        Collect every node id of a parsed reStructuredText document
        (section ids and explicit targets).

        :param doctree: The parsed document.

        :returns: The anchor names.
    """
    finder = getattr(doctree, "findall", None) or doctree.traverse
    anchors: Set[str] = set()
    for node in finder(docutils.nodes.Element):
        for node_id in node.get("ids", []):
            anchors.add(node_id)
    rtnval = anchors
    return rtnval


def _unresolved_rst_references(*, relpath: str, messages: str) -> List[str]:
    """
        List the ``name`_`` references docutils could not resolve, and
        names defined twice with different targets.

        :param relpath: Repository-relative path of the document.
        :param messages: The warnings and errors docutils reported.

        :returns: One message per problem.
    """
    problems: List[str] = []
    for line in messages.splitlines():
        if ("(WARNING/" not in line) and ("(ERROR/" not in line) and ("(SEVERE/" not in line):
            continue
        if "Unknown target name" in line or "Duplicate explicit target name" in line:
            location, _, detail = line.partition(": (")
            line_number = location.rsplit(":", 1)[-1]
            problems.append("{}:{}: {}".format(relpath, line_number, detail.split(") ", 1)[-1]))
    rtnval = problems
    return rtnval


class _AnchorCache:
    """
        Parse each target document once and remember its anchors.
    """

    def __init__(self) -> None:
        self._anchors: Dict[str, Set[str]] = {}
        return

    def anchors_of(self, *, path: str) -> Set[str]:
        """
            Return the anchors of a Markdown or reStructuredText file.

            :param path: Absolute path of the target document.

            :returns: Its anchor names (empty for other file types).
        """
        if path not in self._anchors:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
            if path.endswith(".md"):
                self._anchors[path] = _markdown_anchors(text=text)
            elif path.endswith(".rst"):
                relpath = os.path.relpath(path, REPO_ROOT)
                doctree, _ = _parse_rst(relpath=relpath, text=text)
                self._anchors[path] = _rst_anchors(doctree=doctree)
            else:
                self._anchors[path] = set()
        rtnval = self._anchors[path]
        return rtnval


def check_links(*, verbose: bool) -> Tuple[List[str], int, int]:
    """
        Check every link in the documentation.

        :param verbose: Print each document as it is checked.

        :returns: ``(problems, relative links checked, external links
                  skipped)``.
    """
    problems: List[str] = []
    checked = 0
    external = 0
    cache = _AnchorCache()

    for relpath in _document_paths():
        absolute = os.path.join(REPO_ROOT, relpath)
        with open(absolute, "r", encoding="utf-8") as handle:
            text = handle.read()
        if relpath.endswith(".md"):
            links = _markdown_links(relpath=relpath, text=text)
        else:
            doctree, messages = _parse_rst(relpath=relpath, text=text)
            links = _rst_links(relpath=relpath, text=text, doctree=doctree)
            problems.extend(_unresolved_rst_references(relpath=relpath, messages=messages))
        if verbose is True:
            print("{}: {} links".format(relpath, len(links)))

        for link in links:
            if link.target.startswith(_EXTERNAL_SCHEMES):
                external += 1
                continue
            checked += 1
            path_part, _, anchor = link.target.partition("#")
            if len(path_part) == 0:
                target_path = absolute
            else:
                target_path = os.path.normpath(os.path.join(os.path.dirname(absolute), path_part))
            where = "{}:{}".format(link.source, link.line)
            if os.path.exists(target_path) is False:
                problems.append("{}: {} -- no such file".format(where, link.target))
                continue
            if len(anchor) == 0 or os.path.isdir(target_path):
                continue
            if target_path.endswith((".md", ".rst")) is False:
                continue
            if anchor not in cache.anchors_of(path=target_path):
                problems.append("{}: {} -- no such heading or target".format(where, link.target))

    rtnval = (problems, checked, external)
    return rtnval


def main() -> int:
    """
        Command-line entry point.

        :returns: The process exit status.
    """
    parser = argparse.ArgumentParser(description="Check the repository documentation's links.")
    parser.add_argument("--verbose", action="store_true", help="list each document checked")
    args = parser.parse_args()

    problems, checked, external = check_links(verbose=args.verbose)
    for problem in problems:
        print(problem)
    print(
        "{} relative links checked, {} external links not fetched, {} problems".format(
            checked, external, len(problems)
        )
    )
    rtnval = 1 if len(problems) > 0 else 0
    return rtnval


if __name__ == "__main__":
    sys.exit(main())
