"""
.. module:: cli.extensions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Extension surface for the ``pyc`` CLI.

.. moduleauthor:: Automation Mojo LLC

External ``pychestrate-ext-<name>`` packs subclass
:class:`CLISubcommandExtension` to add subcommands under
``pyc ext <ext-name>``. The base lives here (under the CLI package)
rather than under ``webservice.extensions`` because the CLI is
distributed independently of the service runtime — keeping the base
co-located keeps the CLI build self-contained.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.cli.extensions.cli_subcommand import (
    CLISubcommandDescriptor,
    CLISubcommandExtension,
)
from automojo.pychestrate.cli.extensions.discovery import (
    ResolvedExtCommand,
    find_descriptor,
    find_mounted_route_for_verb,
    find_subcommand_class,
    resolve_ext_command,
)
from automojo.pychestrate.cli.extensions.example_subcommand import (
    PycExtExampleSubcommand,
)


__all__ = [
    "CLISubcommandDescriptor",
    "CLISubcommandExtension",
    "PycExtExampleSubcommand",
    "ResolvedExtCommand",
    "find_descriptor",
    "find_mounted_route_for_verb",
    "find_subcommand_class",
    "resolve_ext_command",
]
