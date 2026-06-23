"""
.. module:: orchestration.test.artifact_browser
    :synopsis: 6-artifact-browser — renderer dispatch over result trees.

Public surface:

* :class:`RendererChoice`, :class:`RendererRecord` — IO shapes.
* :func:`select_renderer`, :func:`list_renderer_records`.
* :class:`ArtifactRendererProtocol` factory contract +
  reference :class:`PlainTextRenderer` and
  :class:`LogStreamRenderer`.
* :class:`ArtifactBrowserEventTopics`.
* Errors: :class:`ArtifactBrowserError`,
  :class:`NoMatchingRendererError`,
  :class:`ArtifactPathInvalidError`.
* :func:`register_builtin_extensions`.

The feature owns no persistent state — directory listings come
from ``5-artifact-store`` (M2 wiring); M1 ships the renderer
registry + selection algorithm.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.orchestration.test.artifact_browser.errors import (
    ArtifactBrowserError,
    ArtifactPathInvalidError,
    NoMatchingRendererError,
)
from ccai.pychestrate.webservice.orchestration.test.artifact_browser.events import (
    ArtifactBrowserEventTopics,
)
from ccai.pychestrate.webservice.orchestration.test.artifact_browser.factories.renderer_protocol import (
    ArtifactRendererProtocol,
    RendererMatch,
    RendererRecord,
)
from ccai.pychestrate.webservice.orchestration.test.artifact_browser.factories.log_stream_renderer import (
    LogStreamRenderer,
)
from ccai.pychestrate.webservice.orchestration.test.artifact_browser.factories.plain_text_renderer import (
    PlainTextRenderer,
)
from ccai.pychestrate.webservice.orchestration.test.artifact_browser.service import (
    ArtifactRef,
    RendererChoice,
    list_renderer_records,
    select_renderer,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree renderer reference implementations.
    """
    register_factory_implementation(implementation=LogStreamRenderer)
    register_factory_implementation(implementation=PlainTextRenderer)
    return
