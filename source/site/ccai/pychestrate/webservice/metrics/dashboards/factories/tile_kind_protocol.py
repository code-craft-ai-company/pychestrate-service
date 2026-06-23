"""
.. module:: metrics.dashboards.factories.tile_kind_protocol
    :synopsis: ``dashboard_tile_kind`` factory contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, List, Mapping, Tuple

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


@dataclass(frozen=True)
class TileKindRecord:
    """
        Caller-facing description of a registered tile kind.

        :param kind: Stable identifier matching
                     :attr:`TileInstance.kind`.
        :param webcomponent_tag: WebComponent tag the M2 UI
                                 mounts.
        :param default_size: ``(width, height)`` in grid cells.
        :param description: Human-readable description.
    """
    kind: str
    webcomponent_tag: str
    default_size: Tuple[int, int]
    description: str = ""
    default_config: Mapping[str, Any] = field(default_factory=dict)


class DashboardTileKindProtocol(FactoryProtocolBase):
    """
        Contract for ``dashboard_tile_kind`` extensions.
    """

    factory_protocol_name: str = "dashboard_tile_kind"
    protocol_schema_version: int = 1

    @classmethod
    def kind_name(cls) -> str:
        """
            Stable identifier matching
            :attr:`TileInstance.kind`.
        """
        raise NotImplementedError("Subclasses must implement kind_name")

    @classmethod
    def record(cls) -> TileKindRecord:
        """
            Static description used by REST listings + the M2
            UI tile-picker.
        """
        raise NotImplementedError("Subclasses must implement record")

    @classmethod
    def validate_config(
            cls,
            *,
            config: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        """
            Validate the tile's config payload. Return
            ``(True, ())`` on success;
            ``(False, ("reason1", ...))`` otherwise.
        """
        raise NotImplementedError("Subclasses must implement validate_config")
