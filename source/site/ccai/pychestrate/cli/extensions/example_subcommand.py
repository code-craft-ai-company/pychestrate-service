"""
.. module:: cli.extensions.example_subcommand
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference :class:`CLISubcommandExtension` shipped in-tree.

.. moduleauthor:: Code Craft AI LLC

Wraps the ``ExampleEchoEndpoints`` REST surface declared in p10i.
``pyc ext example echo --message=<text>`` round-trips through the
service's ``/api/v1/ext/example/echo`` route and prints the response.

This is the catalog's published reference for
``CLISubcommandExtension`` — external authors copy the shape, the
M2 router uses it for end-to-end discovery + dispatch tests.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import ClassVar, Tuple

from ccai.pychestrate.cli.extensions.cli_subcommand import (
    CLISubcommandDescriptor,
    CLISubcommandExtension,
)


class PycExtExampleSubcommand(CLISubcommandExtension):
    """
        Reference :class:`CLISubcommandExtension` exposing
        ``pyc ext example echo``.
    """

    ext_name: ClassVar[str] = "example"

    _ECHO_DESCRIPTOR: ClassVar[CLISubcommandDescriptor] = CLISubcommandDescriptor(
        verb="echo",
        operation_id="ext_example_echo",
        positional_arg_names=tuple(),
        flag_arg_names=("message",),
        description="Echo back the --message flag through the example REST endpoint.",
    )

    @classmethod
    def declare_subcommands(cls) -> Tuple[CLISubcommandDescriptor, ...]:
        rtnval: Tuple[CLISubcommandDescriptor, ...] = (cls._ECHO_DESCRIPTOR,)
        return rtnval

    @classmethod
    def required_capabilities(cls) -> Tuple[str, ...]:
        rtnval: Tuple[str, ...] = tuple()
        return rtnval
