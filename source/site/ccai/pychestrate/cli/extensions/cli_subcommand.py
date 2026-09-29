"""
.. module:: cli.extensions.cli_subcommand
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``CLISubcommandExtension`` resource base for ``pyc ext <name>``.

.. moduleauthor:: Code Craft AI LLC

Layer 8's published catalog includes ``CLISubcommandExtension`` per
``8-plugin-api`` Requirement 2. External packs subclass this base to
contribute ``pyc ext <ext-name> <subcommand>`` invocations. Each
subcommand declares a :class:`CLISubcommandDescriptor` row pointing
at the REST operation it wraps so the parser can render arguments
without re-parsing OpenAPI per pack.

The base lives under :mod:`cli.extensions` (alongside the CLI
package) rather than under :mod:`webservice.extensions` because the
CLI is distributed separately from the service runtime (the
standard-library-only ``pychestrate-cli`` package) — keeping the base
co-located keeps the CLI build self-contained and frees pack authors
from depending on the full service codebase.

Its base class is the service's
:class:`~ccai.pychestrate.webservice.extensions.resource_extension.ResourceExtension`
when the service is installed next to the CLI (the server process,
where the plugin-api catalog must list ``CLISubcommandExtension`` as a
published resource base), and a stand-in with the same class
attributes when only ``pychestrate-cli`` is installed.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import ClassVar, Tuple

try:
    from ccai.pychestrate.webservice.extensions.resource_extension import ResourceExtension
except ImportError:
    class ResourceExtension:  # type: ignore[no-redef]
        """
            Stand-in for the service's resource-extension base when
            only the standalone ``pychestrate-cli`` package is
            installed.
        """

        resource_extension_name: ClassVar[str] = ""


@dataclass(frozen=True)
class CLISubcommandDescriptor:
    """
        Single subcommand under ``pyc ext <ext-name>``.

        :param verb: Subcommand verb shown to operators
                     (e.g., ``"echo"`` becomes ``pyc ext example echo``).
        :param operation_id: ``operationId`` of the REST operation the
                             subcommand wraps. The CLI resolves this
                             against the catalog or builds a synthetic
                             operation when documented as such.
        :param positional_arg_names: Tuple of positional argument
                                     names in declaration order.
        :param flag_arg_names: Tuple of optional ``--flag`` argument
                               names.
        :param description: Operator-facing one-line summary.
    """
    verb: str
    operation_id: str
    positional_arg_names: Tuple[str, ...]
    flag_arg_names: Tuple[str, ...]
    description: str


class CLISubcommandExtension(ResourceExtension):
    """
        Base class for an extension contributing ``pyc ext`` subcommands.

        Subclasses set :attr:`ext_name` (segment under ``pyc ext``) and
        override :meth:`declare_subcommands` to return a non-empty
        tuple of :class:`CLISubcommandDescriptor`.

        :attr:`required_capabilities` mirrors the sandbox capability
        keys the underlying REST endpoint requires; the service's
        extension router uses the same set, so authors keep the
        descriptor consistent across both surfaces.
    """

    resource_extension_name: ClassVar[str] = "cli_subcommand"
    ext_name: ClassVar[str] = ""
    cli_schema_version: ClassVar[int] = 1

    is_published: ClassVar[bool] = True
    published_docs_url: ClassVar[str] = (
        "/docs/extensions/resources/CLISubcommandExtension.html"
    )
    published_reference: ClassVar[str] = (
        "ccai.pychestrate.cli.extensions.example_subcommand"
        ".PycExtExampleSubcommand"
    )

    @classmethod
    def declare_subcommands(cls) -> Tuple[CLISubcommandDescriptor, ...]:
        """
            Return the subcommands this extension contributes.

            :returns: Tuple of :class:`CLISubcommandDescriptor`.
        """
        raise NotImplementedError("Subclasses must implement declare_subcommands")

    @classmethod
    def required_capabilities(cls) -> Tuple[str, ...]:
        """
            Sandbox capability keys propagated from the REST endpoint.
            Default is the empty tuple — pure read-only subcommands
            need nothing.

            :returns: Tuple of capability key strings.
        """
        rtnval: Tuple[str, ...] = tuple()
        return rtnval
