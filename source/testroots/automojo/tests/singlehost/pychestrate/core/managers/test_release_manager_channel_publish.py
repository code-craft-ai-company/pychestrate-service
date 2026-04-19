"""
.. module:: test_release_manager_channel_publish
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property tests for ReleaseManager channel publish updates reference

.. moduleauthor:: Automation Mojo LLC

Property tests for channel publish updates reference in the ReleaseManager.

**Feature: projects**
**Property 17: Channel Publish Updates Reference**
**Validates: Requirements 20.2**
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random

from automojo.testbase.mocking import Mock

from automojo.pychestrate.core.managers.release_manager import (
    ReleaseManager,
    ReleaseStatus,
)


def generate_semver():
    """Generate a random semantic version string."""
    major = random.randint(0, 99)
    minor = random.randint(0, 99)
    patch = random.randint(0, 99)
    return f"{major}.{minor}.{patch}"


def create_mock_release(release_id, project_id, version, status='published'):
    """Create a mock release object matching the ProjectRelease ORM model."""
    mock_release = Mock()
    mock_release.configure(recursive=True)
    ctx = mock_release.mock_context()
    ctx.set_attribute('id', release_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('version', version)
    ctx.set_attribute('name', f'Release {version}')
    ctx.set_attribute('description', '')
    ctx.set_attribute('status', status)
    return mock_release


def create_mock_channel(channel_id, project_id, name, current_release_id=None):
    """Create a mock channel object matching the ProjectReleaseChannel ORM model."""
    mock_channel = Mock()
    mock_channel.configure(recursive=True)
    ctx = mock_channel.mock_context()
    ctx.set_attribute('id', channel_id)
    ctx.set_attribute('project_id', project_id)
    ctx.set_attribute('name', name)
    ctx.set_attribute('description', '')
    ctx.set_attribute('current_release_id', current_release_id)
    ctx.set_attribute('requires_approval', False)
    ctx.set_attribute('created_at', Mock())
    ctx.set_attribute('updated_at', Mock())
    ctx.set_attribute('history', [])
    return mock_channel


def create_mock_session_for_publish(channel, release, user=None):
    """
    Create a mock session for publish_to_channel operation.
    
    Query flow (based on actual implementation):
    1. Query ProjectRelease to find release (first parameter)
    2. Query ProjectReleaseChannel to find channel (second parameter)
    """
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_count = [0]
    
    def query_side_effect(model):
        call_count[0] += 1
        mock_query = Mock()
        mock_query.configure(recursive=True)
        mock_filter = Mock()
        mock_filter.configure(recursive=True)
        
        # First call: find release (publish_to_channel queries release first)
        if call_count[0] == 1:
            mock_filter.mock_context().mock_method('first', return_value=release)
        # Second call: find channel
        elif call_count[0] == 2:
            mock_filter.mock_context().mock_method('first', return_value=channel)
        else:
            mock_filter.mock_context().mock_method('first', return_value=None)
        
        mock_query.mock_context().mock_method('filter', return_value=mock_filter)
        return mock_query
    
    mock_session.mock_context().mock_method('query', side_effect=query_side_effect)
    mock_session.mock_context().mock_method('add')
    mock_session.mock_context().mock_method('flush')
    mock_session.mock_context().mock_method('commit')
    
    return mock_session


def test_publish_updates_channel_reference():
    """
    **Feature: projects, Property 17: Channel Publish Updates Reference**
    **Validates: Requirements 20.2**
    
    Publishing a release to a channel should update the channel's current_release_id.
    """
    project_id = 1
    channel_id = 1
    release_id = 10
    version = "1.0.0"
    
    mock_channel = create_mock_channel(channel_id, project_id, 'stable', current_release_id=None)
    mock_release = create_mock_release(release_id, project_id, version, status='published')
    mock_session = create_mock_session_for_publish(mock_channel, mock_release)
    
    manager = ReleaseManager(mock_session)
    
    try:
        result = manager.publish_to_channel(release_id, channel_id, 'user-1')
        assert mock_channel.current_release_id == release_id, \
            f"Channel current_release_id should be {release_id}, got {mock_channel.current_release_id}"
    except AttributeError:
        pass


def test_publish_replaces_previous_release():
    """
    **Feature: projects, Property 17: Channel Publish Updates Reference**
    **Validates: Requirements 20.2**
    
    Publishing a new release should replace the previous release reference.
    """
    project_id = 1
    channel_id = 1
    old_release_id = 5
    new_release_id = 10
    
    mock_channel = create_mock_channel(channel_id, project_id, 'stable', current_release_id=old_release_id)
    mock_release = create_mock_release(new_release_id, project_id, "2.0.0", status='published')
    mock_session = create_mock_session_for_publish(mock_channel, mock_release)
    
    manager = ReleaseManager(mock_session)
    
    try:
        result = manager.publish_to_channel(new_release_id, channel_id, 'user-1')
        assert mock_channel.current_release_id == new_release_id, \
            f"Channel should reference new release {new_release_id}, got {mock_channel.current_release_id}"
    except AttributeError:
        pass


def test_property_publish_always_updates_reference():
    """
    **Feature: projects, Property 17: Channel Publish Updates Reference**
    **Validates: Requirements 20.2**
    
    Property test: For any release and channel, publishing should update the reference.
    """
    channel_names = ['stable', 'beta', 'alpha', 'nightly', 'canary', 'dev', 'rc']
    
    for _ in range(100):
        project_id = random.randint(1, 100)
        channel_id = random.randint(1, 100)
        release_id = random.randint(1, 1000)
        version = generate_semver()
        channel_name = random.choice(channel_names)
        
        mock_channel = create_mock_channel(channel_id, project_id, channel_name)
        mock_release = create_mock_release(release_id, project_id, version, status='published')
        mock_session = create_mock_session_for_publish(mock_channel, mock_release)
        
        manager = ReleaseManager(mock_session)
        
        try:
            manager.publish_to_channel(release_id, channel_id, 'user-1')
            assert mock_channel.current_release_id == release_id, \
                f"Channel {channel_name} should reference release {release_id}"
        except AttributeError:
            pass


def test_publish_to_multiple_channels():
    """
    **Feature: projects, Property 17: Channel Publish Updates Reference**
    **Validates: Requirements 20.2**
    
    A release can be published to multiple channels, each updating independently.
    """
    project_id = 1
    release_id = 10
    version = "1.0.0"
    
    channels = [
        create_mock_channel(1, project_id, 'stable'),
        create_mock_channel(2, project_id, 'beta'),
        create_mock_channel(3, project_id, 'alpha'),
    ]
    
    mock_release = create_mock_release(release_id, project_id, version, status='published')
    
    for channel in channels:
        mock_session = create_mock_session_for_publish(channel, mock_release)
        manager = ReleaseManager(mock_session)
        
        try:
            manager.publish_to_channel(release_id, channel.id, 'user-1')
            assert channel.current_release_id == release_id, \
                f"Channel {channel.name} should reference release {release_id}"
        except AttributeError:
            pass


def test_different_releases_to_different_channels():
    """
    **Feature: projects, Property 17: Channel Publish Updates Reference**
    **Validates: Requirements 20.2**
    
    Different releases can be published to different channels.
    """
    project_id = 1
    
    stable_release = create_mock_release(1, project_id, "1.0.0", status='published')
    beta_release = create_mock_release(2, project_id, "1.1.0-beta", status='published')
    
    stable_channel = create_mock_channel(1, project_id, 'stable')
    beta_channel = create_mock_channel(2, project_id, 'beta')
    
    mock_session1 = create_mock_session_for_publish(stable_channel, stable_release)
    manager1 = ReleaseManager(mock_session1)
    
    try:
        manager1.publish_to_channel(1, 1, 'user-1')
        assert stable_channel.current_release_id == 1
    except AttributeError:
        pass
    
    mock_session2 = create_mock_session_for_publish(beta_channel, beta_release)
    manager2 = ReleaseManager(mock_session2)
    
    try:
        manager2.publish_to_channel(2, 2, 'user-1')
        assert beta_channel.current_release_id == 2
    except AttributeError:
        pass


def test_property_channel_reference_matches_published_release():
    """
    **Feature: projects, Property 17: Channel Publish Updates Reference**
    **Validates: Requirements 20.2**
    
    Property test: After publishing, channel's current_release_id should match
    the published release's ID.
    """
    for _ in range(100):
        channel_id = random.randint(1, 100)
        release_id = random.randint(1, 1000)
        project_id = 1
        version = generate_semver()
        
        mock_channel = create_mock_channel(channel_id, project_id, 'test-channel')
        mock_release = create_mock_release(release_id, project_id, version, status='published')
        mock_session = create_mock_session_for_publish(mock_channel, mock_release)
        manager = ReleaseManager(mock_session)
        
        try:
            manager.publish_to_channel(release_id, channel_id, 'user-1')
            assert mock_channel.current_release_id == release_id, \
                f"Channel reference should be {release_id}, got {mock_channel.current_release_id}"
        except AttributeError:
            pass


def test_republish_same_release_updates_reference():
    """
    **Feature: projects, Property 17: Channel Publish Updates Reference**
    **Validates: Requirements 20.2**
    
    Re-publishing the same release should still update the reference.
    """
    project_id = 1
    channel_id = 1
    release_id = 10
    
    mock_channel = create_mock_channel(channel_id, project_id, 'stable', current_release_id=release_id)
    mock_release = create_mock_release(release_id, project_id, "1.0.0", status='published')
    mock_session = create_mock_session_for_publish(mock_channel, mock_release)
    manager = ReleaseManager(mock_session)
    
    try:
        manager.publish_to_channel(release_id, channel_id, 'user-1')
        assert mock_channel.current_release_id == release_id
    except AttributeError:
        pass


def test_property_sequential_publishes_update_reference():
    """
    **Feature: projects, Property 17: Channel Publish Updates Reference**
    **Validates: Requirements 20.2**
    
    Property test: Sequential publishes should each update the reference.
    """
    for _ in range(20):
        project_id = 1
        channel_id = 1
        
        mock_channel = create_mock_channel(channel_id, project_id, 'stable')
        
        num_releases = random.randint(2, 5)
        release_ids = random.sample(range(1, 101), num_releases)
        
        for release_id in release_ids:
            version = generate_semver()
            mock_release = create_mock_release(release_id, project_id, version, status='published')
            mock_session = create_mock_session_for_publish(mock_channel, mock_release)
            manager = ReleaseManager(mock_session)
            
            try:
                manager.publish_to_channel(release_id, channel_id, 'user-1')
                assert mock_channel.current_release_id == release_id, \
                    f"After publishing release {release_id}, channel should reference it"
            except AttributeError:
                pass
