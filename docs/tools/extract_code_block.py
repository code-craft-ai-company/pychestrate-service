#!/usr/bin/env python3
"""
    Print the body of a named ``code-block`` from a reStructuredText file.

    The operator runbook's smoke-test scripts are ordinary code blocks
    with a ``:name:`` option. CI extracts them with this script and runs
    them, so the commands operators copy are the commands CI tests::

        python3 docs/tools/extract_code_block.py \\
            userguide/13-00-alpha-deployment.rst smoke-before-setup > smoke.sh
        bash smoke.sh

    Exit status: 0 when exactly one block has the name, 1 otherwise.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import argparse
import re
import sys

from typing import List, Optional


_DIRECTIVE_PATTERN = re.compile(r"^(?P<indent>\s*)\.\.\s+(code-block|code|sourcecode)::")
_OPTION_PATTERN = re.compile(r"^(?P<indent>\s+):(?P<name>[A-Za-z][\w-]*):\s*(?P<value>.*)$")


def _indent_of(line: str) -> int:
    """
        Count the leading spaces of a line.

        :param line: A line of text.

        :returns: The number of leading space characters.
    """
    rtnval = len(line) - len(line.lstrip(" "))
    return rtnval


def extract_named_blocks(*, lines: List[str], block_name: str) -> List[str]:
    """
        Find every ``code-block`` whose ``:name:`` option equals
        ``block_name`` and return their bodies, dedented.

        :param lines: The file's lines, without line endings.
        :param block_name: The ``:name:`` value to look for.

        :returns: One string per matching block.
    """
    bodies: List[str] = []
    index = 0
    while index < len(lines):
        match = _DIRECTIVE_PATTERN.match(lines[index])
        if match is None:
            index += 1
            continue

        directive_indent = len(match.group("indent"))
        index += 1
        found_name: Optional[str] = None
        while index < len(lines):
            option = _OPTION_PATTERN.match(lines[index])
            if option is None or len(option.group("indent")) <= directive_indent:
                break
            if option.group("name") == "name":
                found_name = option.group("value").strip()
            index += 1

        body: List[str] = []
        while index < len(lines):
            line = lines[index]
            if len(line.strip()) > 0 and _indent_of(line) <= directive_indent:
                break
            body.append(line)
            index += 1

        if found_name != block_name:
            continue

        while len(body) > 0 and len(body[0].strip()) == 0:
            body.pop(0)
        while len(body) > 0 and len(body[-1].strip()) == 0:
            body.pop()
        content_indents = [_indent_of(line) for line in body if len(line.strip()) > 0]
        dedent = min(content_indents) if len(content_indents) > 0 else 0
        bodies.append("\n".join(line[dedent:] for line in body) + "\n")

    rtnval = bodies
    return rtnval


def main() -> int:
    """
        Command-line entry point.

        :returns: The process exit status.
    """
    parser = argparse.ArgumentParser(description="Print a named code-block from an RST file.")
    parser.add_argument("rst_file", help="the reStructuredText file to read")
    parser.add_argument("block_name", help="the code-block's :name: option")
    args = parser.parse_args()

    with open(args.rst_file, "r", encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    bodies = extract_named_blocks(lines=lines, block_name=args.block_name)
    if len(bodies) != 1:
        print(
            "expected exactly one code-block named {!r} in {}, found {}".format(
                args.block_name, args.rst_file, len(bodies)
            ),
            file=sys.stderr,
        )
        return 1

    sys.stdout.write(bodies[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
