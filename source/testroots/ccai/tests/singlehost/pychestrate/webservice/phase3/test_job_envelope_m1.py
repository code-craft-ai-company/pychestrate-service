"""
.. module:: test_job_envelope_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 5-job-envelope M1 — schema, canonical, signer, codec.

.. moduleauthor:: Code Craft AI LLC

Covers the M1 spec's core behavior:

* ``EnvelopeCodec.build(dispatch_request)`` produces a populated
  envelope with all required top-level fields.
* Missing required fields raise ``SemanticError`` naming every
  absent field.
* Canonical serialize/parse round-trip preserves structural equality.
* Canonical serialization is order-independent (keys sorted).
* Ed25519 ``sign`` / ``verify`` round-trip returns ``valid=True``.
* ``verify`` detects any single-byte mutation of the payload and
  returns ``valid=False`` with ``reason="signature_mismatch"``.
* Unknown ``key_id`` on verify surfaces ``reason="unknown_key"`` —
  never crashes, never falls through.
* Expired signed envelopes surface ``reason="expired"``.
* Unsupported ``schema_version`` raises
  ``EnvelopeSchemaVersionError`` on parse.
* Persisting a signed envelope through ``persist_signed_envelope``
  materializes a ``JobEnvelopeRecord`` row.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple

from ccai import testbase

from ccai.errors.exceptions import ConfigurationError, SemanticError

from ccai.pychestrate.webservice.jobs.envelope import (
    DispatchRequest,
    EnvelopeSchemaVersionError,
    EnvelopeSerializationError,
    EnvelopeSignerBootstrapConfig,
    JobDeadline,
    JobEnvelope,
    JobEnvelopeRecord,
    JobForwardingInfo,
    JobPipelineRef,
    JobRefs,
    JobResultsLocator,
    ScopedSecret,
    SignedJobEnvelope,
    build,
    get_envelope,
    install_envelope_signer,
    list_envelopes_for_run,
    parse,
    persist_signed_envelope,
    sign,
    verify,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    canonical as canonical_mod,
    signer as signer_mod,
    startup as startup_mod,
)
from ccai.pychestrate.webservice.jobs.envelope.schema import (
    ENVELOPE_SCHEMA_VERSION,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


DEV_PROJECT_UUID = "00000000-0000-4000-8000-00000000aaaa"
DEV_JOB_UUID = "00000000-0000-4000-8000-00000000bbbb"
DEV_RUN_UUID = "00000000-0000-4000-8000-00000000cccc"
DEV_CLIENT_UUID = "00000000-0000-4000-8000-00000000dddd"
DEV_POD_UUID = "00000000-0000-4000-8000-00000000eeee"


def _install_dev_signer() -> None:
    """
        Install an ephemeral Ed25519 signing key for the test process.
        Sets PYCHESTRATE_DEV_MODE so the ``dev`` source path is
        honored, installs, then clears the env var so later tests do
        not inherit dev mode implicitly.
    """
    import os
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev",
                file_path=None,
                env_var=None,
                key_id="test-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    return


def _build_dispatch_request() -> DispatchRequest:
    """
        Construct a fully-populated DispatchRequest for the happy
        path tests. Shared across cases so every test exercises the
        same structural shape.
    """
    now = datetime.now(timezone.utc)
    soft = now + timedelta(minutes=30)
    hard = now + timedelta(minutes=60)

    rtnval = DispatchRequest(
        project_id=DEV_PROJECT_UUID,
        job_id=DEV_JOB_UUID,
        job_name="regression-smoke",
        job_type="testbase-singlehost",
        run_id=DEV_RUN_UUID,
        client_id=DEV_CLIENT_UUID,
        pod_id=DEV_POD_UUID,
        issuer="pychestrate.example.com/0.3.1",
        pipeline=JobPipelineRef(pipeline_id="pl-1", instance_id="inst-1"),
        refs=JobRefs(
            branch="main",
            build="build-4421",
            flavor="debug",
            release="v2.0",
            commit_sha="a" * 40,
        ),
        params={"timeout_seconds": 120, "tags": ["smoke", "nightly"]},
        scoped_secrets=(
            ScopedSecret(
                name="ARTIFACT_UPLOAD_TOKEN",
                value="opaque-short-lived-1",
                expires_at=hard + timedelta(minutes=5),
                token_type="bearer",
            ),
        ),
        results=JobResultsLocator(
            backend_key_prefix="runs/2026/04/24/{}".format(DEV_RUN_UUID),
            backend_driver="s3",
        ),
        forwarding=JobForwardingInfo(
            progress_url="https://pychestrate.example.com/api/v1/runs/progress",
            summary_url="https://pychestrate.example.com/api/v1/runs/summary",
            auth_method="bearer",
        ),
        deadline=JobDeadline(soft_deadline_at=soft, hard_deadline_at=hard),
        extension_claims={},
    )
    return rtnval


def test_build_populates_every_required_field():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: build(dispatch_request) produces an envelope with every
    required top-level field present and correctly typed.**
    """
    envelope = build(request=_build_dispatch_request())
    testbase.assert_equal(envelope.schema_version, ENVELOPE_SCHEMA_VERSION)
    testbase.assert_equal(len(envelope.envelope_id) > 0, True)
    testbase.assert_equal(envelope.project_id, DEV_PROJECT_UUID)
    testbase.assert_equal(envelope.job_id, DEV_JOB_UUID)
    testbase.assert_equal(envelope.run_id, DEV_RUN_UUID)
    testbase.assert_equal(envelope.pipeline.pipeline_id, "pl-1")
    testbase.assert_equal(len(envelope.scoped_secrets), 1)
    testbase.assert_equal(envelope.extension_claims, {})
    return


def test_build_missing_required_field_raises_semantic_error():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: a dict candidate missing structural identifiers raises
    SemanticError naming every missing field.**
    """
    from ccai.pychestrate.webservice.jobs.envelope.schema import (
        assert_required_fields_present,
    )
    incomplete = {"schema_version": ENVELOPE_SCHEMA_VERSION}
    raised = False
    try:
        assert_required_fields_present(candidate=incomplete)
    except SemanticError as xcpt:
        raised = True
        message = str(xcpt)
        # Must name at least a handful of missing structural fields.
        for expected_field in ("envelope_id", "project_id", "job_id", "run_id"):
            testbase.assert_equal(expected_field in message, True)
    testbase.assert_equal(raised, True)
    return


def test_canonical_round_trip_preserves_envelope():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: parse(serialize_canonical(e)) recovers an equivalent
    envelope.**
    """
    envelope = build(request=_build_dispatch_request())
    payload = canonical_mod.serialize_canonical(envelope=envelope)
    recovered = parse(canonical_payload=payload)
    testbase.assert_equal(recovered.envelope_id, envelope.envelope_id)
    testbase.assert_equal(recovered.project_id, envelope.project_id)
    testbase.assert_equal(recovered.job_id, envelope.job_id)
    testbase.assert_equal(recovered.run_id, envelope.run_id)
    testbase.assert_equal(recovered.scoped_secrets[0].name, "ARTIFACT_UPLOAD_TOKEN")
    return


def test_canonical_json_is_key_sorted_and_whitespace_free():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: the canonical JSON output has sorted top-level keys
    and no whitespace — matches the JCS subset M1 ships.**
    """
    envelope = build(request=_build_dispatch_request())
    payload = canonical_mod.serialize_canonical(envelope=envelope)
    text = payload.decode("utf-8")
    testbase.assert_equal(" " not in text, True)
    testbase.assert_equal("\n" not in text, True)
    # Top-level keys appear in alphabetical order
    as_dict = json.loads(text)
    top_keys = list(as_dict.keys())
    testbase.assert_equal(top_keys, sorted(top_keys))
    return


def test_sign_and_verify_happy_path():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: sign + verify against the same signing key returns
    valid=True.**
    """
    signer_mod.reset_for_testing()
    _install_dev_signer()
    envelope = build(request=_build_dispatch_request())
    signed = sign(envelope=envelope)

    testbase.assert_equal(signed.key_id, "test-ed25519")
    testbase.assert_equal(len(signed.signature), 64)  # Ed25519 sig length
    testbase.assert_equal(signed.canonical_payload.startswith(b"{"), True)

    result = verify(signed=signed)
    testbase.assert_equal(result.valid, True)
    testbase.assert_equal(result.reason, "")

    signer_mod.reset_for_testing()
    return


def test_verify_detects_single_byte_payload_tampering():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: a single-byte mutation of the canonical payload
    produces valid=False with reason="signature_mismatch".**
    """
    signer_mod.reset_for_testing()
    _install_dev_signer()
    envelope = build(request=_build_dispatch_request())
    signed = sign(envelope=envelope)

    # Flip one byte near the middle of the payload.
    tamper_pos = len(signed.canonical_payload) // 2
    tampered_bytes = bytearray(signed.canonical_payload)
    tampered_bytes[tamper_pos] ^= 0x01
    tampered = SignedJobEnvelope(
        envelope=signed.envelope,
        canonical_payload=bytes(tampered_bytes),
        signature=signed.signature,
        key_id=signed.key_id,
        signed_at=signed.signed_at,
    )

    result = verify(signed=tampered)
    testbase.assert_equal(result.valid, False)
    testbase.assert_equal(result.reason, "signature_mismatch")

    signer_mod.reset_for_testing()
    return


def test_verify_unknown_key_id_surfaces_unknown_key():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: a signed envelope carrying a key_id not in the verify
    set returns valid=False with reason="unknown_key".**
    """
    signer_mod.reset_for_testing()
    _install_dev_signer()
    envelope = build(request=_build_dispatch_request())
    signed = sign(envelope=envelope)
    forged = SignedJobEnvelope(
        envelope=signed.envelope,
        canonical_payload=signed.canonical_payload,
        signature=signed.signature,
        key_id="key-that-does-not-exist",
        signed_at=signed.signed_at,
    )
    result = verify(signed=forged)
    testbase.assert_equal(result.valid, False)
    testbase.assert_equal(result.reason, "unknown_key")

    signer_mod.reset_for_testing()
    return


def test_verify_expired_envelope_surfaces_expired():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: a signed envelope older than max_age_seconds
    produces valid=False with reason="expired".**
    """
    signer_mod.reset_for_testing()
    _install_dev_signer()
    envelope = build(request=_build_dispatch_request())
    signed = sign(envelope=envelope)

    far_future = signed.signed_at + timedelta(hours=1)
    result = verify(signed=signed, max_age_seconds=60, now=far_future)
    testbase.assert_equal(result.valid, False)
    testbase.assert_equal(result.reason, "expired")

    signer_mod.reset_for_testing()
    return


def test_parse_rejects_unknown_schema_version():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: parse raises EnvelopeSchemaVersionError when the
    payload carries an unsupported schema_version.**
    """
    signer_mod.reset_for_testing()
    _install_dev_signer()
    envelope = build(request=_build_dispatch_request())
    payload = canonical_mod.serialize_canonical(envelope=envelope)
    tampered = payload.replace(
        ENVELOPE_SCHEMA_VERSION.encode("utf-8"),
        b"9999-13-13",
    )

    raised = False
    try:
        parse(canonical_payload=tampered)
    except EnvelopeSchemaVersionError as xcpt:
        raised = True
        testbase.assert_equal("9999-13-13" in str(xcpt), True)
    testbase.assert_equal(raised, True)

    signer_mod.reset_for_testing()
    return


def test_persist_signed_envelope_materializes_archive_row():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: persist_signed_envelope writes a row the archive
    lookup functions return.**
    """
    signer_mod.reset_for_testing()
    _install_dev_signer()
    engine, session = build_in_memory_session()

    envelope = build(request=_build_dispatch_request())
    signed = sign(envelope=envelope)

    row = persist_signed_envelope(db_session=session, signed=signed)
    session.commit()

    testbase.assert_equal(str(row.envelope_id), envelope.envelope_id)

    fetched = get_envelope(db_session=session, envelope_id=envelope.envelope_id)
    testbase.assert_equal(fetched is not None, True)
    testbase.assert_equal(fetched.key_id, "test-ed25519")
    testbase.assert_equal(fetched.canonical_payload, signed.canonical_payload)

    run_rows = list_envelopes_for_run(db_session=session, run_id=DEV_RUN_UUID)
    testbase.assert_equal(len(run_rows), 1)

    signer_mod.reset_for_testing()
    return


def test_install_envelope_signer_dev_requires_dev_mode():
    """
    **Feature: 5-job-envelope (M1)**
    **Property: install_envelope_signer(source='dev') refuses to run
    when PYCHESTRATE_DEV_MODE is not set.**
    """
    import os
    signer_mod.reset_for_testing()
    prior = os.environ.pop(startup_mod.DEV_MODE_ENV_VAR, None)

    raised = False
    captured_message = ""
    try:
        try:
            install_envelope_signer(
                config=EnvelopeSignerBootstrapConfig(
                    source="dev",
                    file_path=None,
                    env_var=None,
                    key_id="will-not-install",
                ),
            )
        except ConfigurationError as xcpt:
            raised = True
            captured_message = str(xcpt)
    finally:
        if prior is not None:
            os.environ[startup_mod.DEV_MODE_ENV_VAR] = prior

    testbase.assert_equal(raised, True)
    testbase.assert_equal("PYCHESTRATE_DEV_MODE" in captured_message, True)
    return
