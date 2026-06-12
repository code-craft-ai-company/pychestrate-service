"""
.. module:: clients.upgrades.factories.object_store_source
    :synopsis: ObjectStoreArtifactSource reference at PRECEDENCE=100.

The reference describes object-store-backed artifacts using a
caller-supplied ``artifact_ref`` of the form
``"<bucket>/<key>:<sha256>:<byte_size>"``. M2 wires this
descriptor into the ``0-object-store`` driver registry so
agents can fetch the bytes through a streaming source.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from ccai.pychestrate.webservice.clients.upgrades.dtos import (
    ArtifactDescriptor,
)
from ccai.pychestrate.webservice.clients.upgrades.factories.upgrade_artifact_source_protocol import (
    UpgradeArtifactSourceProtocol,
)


OBJECT_STORE_SOURCE_NAME: str = "object_store"


class ObjectStoreArtifactSource(UpgradeArtifactSourceProtocol):
    """
        Reference artifact source that resolves an object-store
        ``bucket/key:sha:bytesize`` reference into a descriptor.
        M1 keeps the implementation pure (no IO) so tests can
        exercise the factory without standing up an object
        store.
    """

    factory_protocol_name: str = "upgrade_artifact_source"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 100

    @classmethod
    def source_name(cls) -> str:
        rtnval = OBJECT_STORE_SOURCE_NAME
        return rtnval

    @classmethod
    def describe(
            cls,
            *,
            artifact_ref: str
        ) -> ArtifactDescriptor:
        if artifact_ref is None or len(artifact_ref) == 0:
            err_lines = [
                "ObjectStoreArtifactSource.describe requires a non-empty ref.",
            ]
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        parts = artifact_ref.split(":")
        if len(parts) != 3:
            err_lines = [
                "ObjectStoreArtifactSource.describe expects "
                "'bucket/key:sha256:byte_size'.",
            ]
            err_lines.append("VALUE: {!r}".format(artifact_ref))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        bucket_key, sha256, byte_size_str = parts
        if "/" not in bucket_key:
            err_lines = [
                "ObjectStoreArtifactSource.describe expects 'bucket/key'.",
            ]
            err_lines.append("VALUE: {!r}".format(bucket_key))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        try:
            byte_size = int(byte_size_str)
        except ValueError as size_err:
            err_lines = [
                "ObjectStoreArtifactSource.describe expects integer byte_size.",
            ]
            err_lines.append("VALUE: {!r}".format(byte_size_str))
            err_lines.append("DETAIL: {}".format(size_err))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        if len(sha256) != 64:
            err_lines = [
                "ObjectStoreArtifactSource.describe expects 64-char sha256.",
            ]
            err_lines.append("VALUE: {!r}".format(sha256))
            err_msg = os.linesep.join(err_lines)
            raise ValueError(err_msg) from None
        rtnval = ArtifactDescriptor(
            artifact_ref=artifact_ref,
            artifact_uri="s3://" + bucket_key,
            artifact_sha256=sha256,
            byte_size=byte_size,
            content_type="application/octet-stream",
        )
        return rtnval
