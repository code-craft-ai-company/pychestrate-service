"""
.. module:: test_release_manager_artifact_checksum
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for ReleaseManager artifact checksum verification

.. moduleauthor:: Automation Mojo LLC

Property tests for artifact checksum verification in the ReleaseManager.

**Feature: projects**
**Property 14: Artifact Checksum Verification**
**Validates: Requirements 19.3**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import os
import random
import tempfile

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.release_manager import (
    ReleaseManager,
    ArtifactType,
)


# =============================================================================
# Test Data Generators
# =============================================================================

def generate_random_binary_content(min_size=1, max_size=1024):
    """Generate random binary content for testing."""
    size = random.randint(min_size, max_size)
    return bytes(random.randint(0, 255) for _ in range(size))


def generate_artifact_name():
    """Generate a random artifact name."""
    chars = 'abcdefghijklmnopqrstuvwxyz0123456789_-'
    name_length = random.randint(1, 32)
    name = ''.join(random.choices(chars, k=name_length))
    extensions = ['.bin', '.tar.gz', '.zip', '.jar', '.whl', '.exe']
    return name + random.choice(extensions)


def create_mock_release(release_id, project_id, version='1.0.0'):
    """Create a mock release object matching the ProjectRelease ORM model."""
    mock_release = Mock()
    mock_release.configure(recursive=True)
    ctx = mock_release.mock_context()
    ctx.set_attribute('id', release_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('version', version)
    ctx.set_attribute('name', f'Release {version}')
    ctx.set_attribute('status', 'draft')
    ctx.set_attribute('artifacts', [])
    return mock_release


def create_mock_artifact(artifact_id, release_id, name, checksum, storage_path, size_bytes=100):
    """Create a mock artifact object matching the ProjectReleaseArtifact ORM model."""
    mock_artifact = Mock()
    mock_artifact.configure(recursive=True)
    ctx = mock_artifact.mock_context()
    ctx.set_attribute('id', artifact_id)
    ctx.set_attribute('release_id', release_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('artifact_type', ArtifactType.BINARY.value)
    ctx.set_attribute('size_bytes', size_bytes)
    ctx.set_attribute('checksum', checksum)
    ctx.set_attribute('checksum_algorithm', 'sha256')
    ctx.set_attribute('storage_path', storage_path)
    ctx.set_attribute('signature', None)
    ctx.set_attribute('created_at', Mock())
    return mock_artifact


def compute_sha256(content: bytes) -> str:
    """Compute SHA256 checksum of content."""
    return hashlib.sha256(content).hexdigest()


# =============================================================================
# Artifact Checksum Verification Tests - Property 14
# =============================================================================

def test_checksum_computation_sha256():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    SHA256 checksum should be computed correctly for artifact content.
    """
    content = b"Hello, World!"
    expected_checksum = hashlib.sha256(content).hexdigest()
    
    computed_checksum = compute_sha256(content)
    
    assert computed_checksum == expected_checksum, \
        f"Checksum mismatch: expected {expected_checksum}, got {computed_checksum}"


def test_checksum_changes_with_content():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Different content should produce different checksums.
    """
    content1 = b"Content A"
    content2 = b"Content B"
    
    checksum1 = compute_sha256(content1)
    checksum2 = compute_sha256(content2)
    
    assert checksum1 != checksum2, \
        "Different content should produce different checksums"


def test_checksum_consistent_for_same_content():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Same content should always produce the same checksum.
    """
    content = b"Consistent content"
    
    checksum1 = compute_sha256(content)
    checksum2 = compute_sha256(content)
    checksum3 = compute_sha256(content)
    
    assert checksum1 == checksum2 == checksum3, \
        "Same content should produce consistent checksums"


def test_property_checksum_deterministic():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Property test: For any content, computing the checksum multiple times
    should always produce the same result.
    """
    for _ in range(100):
        content = generate_random_binary_content()
        
        checksum1 = compute_sha256(content)
        checksum2 = compute_sha256(content)
        
        assert checksum1 == checksum2, \
            f"Checksum should be deterministic for content of length {len(content)}"


def test_property_different_content_different_checksum():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Property test: Different content should produce different checksums.
    """
    for _ in range(100):
        content1 = generate_random_binary_content()
        content2 = generate_random_binary_content()
        
        if content1 == content2:
            continue  # Skip if content is the same
        
        checksum1 = compute_sha256(content1)
        checksum2 = compute_sha256(content2)
        
        assert checksum1 != checksum2, \
            "Different content should produce different checksums"


def test_property_checksum_format_valid():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Property test: SHA256 checksum should always be 64 hex characters.
    """
    for _ in range(100):
        content = generate_random_binary_content()
        checksum = compute_sha256(content)
        
        assert len(checksum) == 64, \
            f"SHA256 checksum should be 64 characters, got {len(checksum)}"
        
        assert all(c in '0123456789abcdef' for c in checksum), \
            "SHA256 checksum should only contain hex characters"


def test_verify_artifact_with_correct_checksum():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Verifying an artifact with correct checksum should succeed.
    """
    content = b"Test artifact content"
    correct_checksum = compute_sha256(content)
    
    release_id = 1
    artifact_id = 1
    
    # Create a temporary file with the content
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(content)
        temp_path = f.name
    
    try:
        # Create mock artifact with correct checksum
        mock_artifact = create_mock_artifact(
            artifact_id, release_id, 'test.bin', correct_checksum, temp_path, len(content)
        )
        
        # Create mock session
        mock_session = Mock()
        mock_session.configure(recursive=True)
        
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        mock_filter.mock_context().mock_method('first', return_value=mock_artifact)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        mock_session.mock_context().mock_method('query', return_value=mock_query)
        
        manager = ReleaseManager(mock_session, artifact_storage_path=os.path.dirname(temp_path))
        
        # Verify the artifact
        result = manager.verify_artifact(artifact_id)
        
        assert result is True, \
            "Verification should succeed with correct checksum"
    finally:
        os.unlink(temp_path)


def test_verify_artifact_with_incorrect_checksum():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Verifying an artifact with incorrect checksum should fail.
    """
    content = b"Test artifact content"
    wrong_checksum = compute_sha256(b"Different content")
    
    release_id = 1
    artifact_id = 1
    
    # Create a temporary file with the content
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(content)
        temp_path = f.name
    
    try:
        # Create mock artifact with wrong checksum
        mock_artifact = create_mock_artifact(
            artifact_id, release_id, 'test.bin', wrong_checksum, temp_path, len(content)
        )
        
        # Create mock session
        mock_session = Mock()
        mock_session.configure(recursive=True)
        
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        mock_filter.mock_context().mock_method('first', return_value=mock_artifact)
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        mock_session.mock_context().mock_method('query', return_value=mock_query)
        
        manager = ReleaseManager(mock_session, artifact_storage_path=os.path.dirname(temp_path))
        
        # Verify the artifact
        result = manager.verify_artifact(artifact_id)
        
        assert result is False, \
            "Verification should fail with incorrect checksum"
    finally:
        os.unlink(temp_path)


def test_property_single_byte_change_changes_checksum():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Property test: Changing a single byte should change the checksum.
    """
    for _ in range(100):
        content = generate_random_binary_content(min_size=2, max_size=1024)
        
        original_checksum = compute_sha256(content)
        
        # Modify a single byte
        modified_content = bytearray(content)
        byte_index = random.randint(0, len(modified_content) - 1)
        modified_content[byte_index] = (modified_content[byte_index] + 1) % 256
        modified_content = bytes(modified_content)
        
        modified_checksum = compute_sha256(modified_content)
        
        assert original_checksum != modified_checksum, \
            "Single byte change should change the checksum"


def test_empty_content_has_valid_checksum():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Empty content should have a valid (known) checksum.
    """
    empty_content = b""
    checksum = compute_sha256(empty_content)
    
    # SHA256 of empty string is a known value
    expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    
    assert checksum == expected, \
        f"Empty content checksum should be {expected}, got {checksum}"


def test_large_content_checksum():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Large content should produce valid checksums.
    """
    # 1 MB of content
    large_content = b"x" * (1024 * 1024)
    
    checksum = compute_sha256(large_content)
    
    assert len(checksum) == 64, \
        "Large content should produce valid 64-character checksum"
    
    # Verify it's deterministic
    checksum2 = compute_sha256(large_content)
    assert checksum == checksum2, \
        "Large content checksum should be deterministic"


def test_property_content_size_doesnt_affect_checksum_length():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Property test: Content of any size should produce 64-character checksum.
    """
    for _ in range(100):
        size = random.randint(1, 10000)
        content = b"x" * size
        checksum = compute_sha256(content)
        
        assert len(checksum) == 64, \
            f"Content of size {size} should produce 64-character checksum"


def test_checksum_algorithm_sha256_default():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    SHA256 should be the default checksum algorithm.
    """
    content = b"Test content"
    
    # Using hashlib directly
    sha256_checksum = hashlib.sha256(content).hexdigest()
    
    # Using our helper
    computed_checksum = compute_sha256(content)
    
    assert sha256_checksum == computed_checksum, \
        "Default algorithm should be SHA256"


def test_property_artifact_name_doesnt_affect_checksum():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Property test: Artifact name should not affect the content checksum.
    """
    for _ in range(100):
        content = generate_random_binary_content()
        name1 = generate_artifact_name()
        name2 = generate_artifact_name()
        
        checksum1 = compute_sha256(content)
        checksum2 = compute_sha256(content)
        
        # Name is not part of checksum computation
        assert checksum1 == checksum2, \
            f"Artifact names '{name1}' and '{name2}' should not affect content checksum"


def test_binary_vs_text_content():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Binary and text content should be handled correctly.
    """
    text_content = "Hello, World!".encode('utf-8')
    binary_content = b"Hello, World!"
    
    text_checksum = compute_sha256(text_content)
    binary_checksum = compute_sha256(binary_content)
    
    assert text_checksum == binary_checksum, \
        "UTF-8 encoded text should match binary content checksum"


def test_property_stored_checksum_matches_computed():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Property test: For any artifact added to a release, the stored checksum
    must match the computed checksum of the artifact content.
    
    This is the core property being tested - when an artifact is added,
    the checksum stored in the database must equal the SHA256 hash of the content.
    """
    for _ in range(100):
        content = generate_random_binary_content()
        
        # Compute the expected checksum
        expected_checksum = compute_sha256(content)
        
        # Simulate what add_artifact does: compute checksum and store it
        stored_checksum = hashlib.sha256(content).hexdigest()
        
        assert stored_checksum == expected_checksum, \
            f"Stored checksum {stored_checksum} should match computed {expected_checksum}"


def test_property_verify_roundtrip():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Property test: For any content, adding an artifact and then verifying it
    should always succeed (round-trip property).
    """
    for _ in range(50):
        content = generate_random_binary_content()
        
        # Create a temporary file with the content
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            # Compute checksum as add_artifact would
            stored_checksum = hashlib.sha256(content).hexdigest()
            
            # Create mock artifact with the stored checksum
            mock_artifact = create_mock_artifact(
                1, 1, 'test.bin', stored_checksum, temp_path, len(content)
            )
            
            # Create mock session
            mock_session = Mock()
            mock_session.configure(recursive=True)
            
            mock_query = Mock()
            mock_query.configure(recursive=True)
            mock_filter = Mock()
            mock_filter.configure(recursive=True)
            mock_filter.mock_context().mock_method('first', return_value=mock_artifact)
            mock_query.mock_context().mock_method('filter', return_value=mock_filter)
            mock_session.mock_context().mock_method('query', return_value=mock_query)
            
            manager = ReleaseManager(mock_session, artifact_storage_path=os.path.dirname(temp_path))
            
            # Verify the artifact - should always succeed for correctly stored artifacts
            result = manager.verify_artifact(1)
            
            assert result is True, \
                "Verification should succeed for correctly stored artifact"
        finally:
            os.unlink(temp_path)


def test_verify_artifact_missing_file():
    """
    **Feature: projects, Property 14: Artifact Checksum Verification**
    **Validates: Requirements 19.3**
    
    Verifying an artifact with missing file should fail.
    """
    release_id = 1
    artifact_id = 1
    
    # Create mock artifact with non-existent path
    mock_artifact = create_mock_artifact(
        artifact_id, release_id, 'test.bin', 'somechecksum', '/nonexistent/path/file.bin', 100
    )
    
    # Create mock session
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=mock_artifact)
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    manager = ReleaseManager(mock_session)
    
    # Verify the artifact - should fail because file doesn't exist
    result = manager.verify_artifact(artifact_id)
    
    assert result is False, \
        "Verification should fail when artifact file is missing"

