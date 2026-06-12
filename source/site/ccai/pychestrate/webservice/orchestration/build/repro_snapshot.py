"""
.. module:: orchestration.build.repro_snapshot
    :synopsis: Reproducibility-snapshot digest helpers.

The repro digest is a SHA-256 over a canonical JSON
serialization of:

* sorted (path, content_sha256) pairs of every input file,
* sorted (toolchain_key, version, fingerprint) tuples,
* sorted (env_key, env_value) tuples for the M1 environment
  fingerprint.

Two builds with identical inputs / toolchain / env hash
identically — the M2 replay endpoint reads this digest to
detect drift.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Tuple


@dataclass(frozen=True)
class BuildToolchainEntry:
    """
        One toolchain entry — e.g. ``("python", "3.12.4",
        sha256_of_binary)``.
    """
    key: str
    version: str
    fingerprint_sha256: str = ""


@dataclass(frozen=True)
class ReproSnapshot:
    """
        Frozen-dataclass bundle the digest is computed over.

        :param input_files: ``{path: content_sha256}``.
        :param toolchain: Tuple of :class:`BuildToolchainEntry`.
        :param env: ``{env_key: env_value}`` — M1 keeps this
                    tiny (build-tool selectors, OS / arch,
                    locale).
    """
    input_files: Mapping[str, str] = field(default_factory=dict)
    toolchain: Tuple[BuildToolchainEntry, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)


def canonicalize_repro_snapshot(*, snapshot: ReproSnapshot) -> str:
    """
        Render a :class:`ReproSnapshot` as canonical JSON.
    """
    payload: Dict[str, object] = {
        "input_files": [
            {"path": path, "sha256": snapshot.input_files[path]}
            for path in sorted(snapshot.input_files.keys())
        ],
        "toolchain": [
            {
                "key": entry.key,
                "version": entry.version,
                "fingerprint_sha256": entry.fingerprint_sha256,
            }
            for entry in sorted(snapshot.toolchain, key=lambda e: e.key)
        ],
        "env": [
            {"key": key, "value": snapshot.env[key]}
            for key in sorted(snapshot.env.keys())
        ],
    }
    rtnval = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    return rtnval


def compute_repro_digest(*, snapshot: ReproSnapshot) -> str:
    """
        SHA-256 hex digest of the canonicalized snapshot.
    """
    canonical = canonicalize_repro_snapshot(snapshot=snapshot)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest
