"""
.. module:: health_monitor
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Contains the HealthMonitor class for resource health tracking and automated health checks

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import ipaddress
import socket
import urllib.request
import urllib.error

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import ensure_utc, utc_now


# =============================================================================
# Constants
# =============================================================================

# Probes run inside the web request (and on the Pychestrate server,
# not near the device), so a probe may not hold a worker thread for
# longer than this.
MAX_PROBE_TIMEOUT_SECONDS = 30

# Command probes executed ``subprocess.run(command, shell=True)`` on the
# Pychestrate server as the service account: anyone able to configure a
# health check could run arbitrary commands there. They are no longer
# accepted, and configurations saved before this change are not run.
COMMAND_PROBES_UNSUPPORTED_MESSAGE = (
    "Command probes are not supported: they would run on the Pychestrate "
    "server, not on the device. Configure a URL probe that targets the "
    "device instead."
)

PROBE_URL_SCHEMES = ('http', 'https')

# Valid health statuses
VALID_HEALTH_STATUSES = {'online', 'offline', 'degraded', 'maintenance'}

# Health statuses that block allocation
BLOCKED_HEALTH_STATUSES = {'offline', 'maintenance'}

# Trigger types for health transitions
TRIGGER_USER = 'user'
TRIGGER_HEALTH_CHECK = 'health_check'
TRIGGER_SYSTEM = 'system'

# A person changing a health status must say why (the reason is the audit
# trail's record of the change); this is the shortest reason accepted.
MIN_MANUAL_REASON_LENGTH = 3


# =============================================================================
# Request/Response Dataclasses
# =============================================================================

@dataclass
class HealthCheckConfigRequest:
    """Request dataclass for configuring health checks."""
    resource_id: int
    probe_url: Optional[str] = None
    probe_command: Optional[str] = None
    interval_seconds: int = 60
    timeout_seconds: int = 10
    failure_threshold: int = 3
    success_threshold: int = 1
    enabled: bool = True



@dataclass
class HealthCheckConfigResponse:
    """Response dataclass for health check configuration."""
    id: int
    resource_id: int
    resource_name: str
    probe_url: Optional[str]
    probe_command: Optional[str]
    interval_seconds: int
    timeout_seconds: int
    failure_threshold: int
    success_threshold: int
    consecutive_failures: int
    consecutive_successes: int
    last_check_time: Optional[datetime]
    last_check_result: Optional[bool]
    enabled: bool


@dataclass
class HealthTransitionResponse:
    """Response dataclass for health status transition."""
    id: int
    resource_id: int
    resource_name: str
    old_status: str
    new_status: str
    reason: Optional[str]
    triggered_by: str
    user_id: Optional[str]
    timestamp: datetime


@dataclass
class HealthTransitionListResponse:
    """Response dataclass for paginated health transition list."""
    transitions: List[HealthTransitionResponse]
    total: int
    offset: int
    limit: int


@dataclass
class HealthCheckResult:
    """Result of a health check execution."""
    resource_id: int
    resource_name: str
    healthy: bool
    old_status: str
    new_status: str
    status_changed: bool
    error_message: Optional[str] = None


@dataclass
class HealthCheckSummary:
    """Summary of running all health checks."""
    total_checked: int
    healthy_count: int
    unhealthy_count: int
    status_changes: int
    results: List[HealthCheckResult]


# =============================================================================
# Exceptions
# =============================================================================

class HealthMonitorError(Exception):
    """Base exception for health monitor errors."""
    
    def __init__(self, message: str, error_code: str = "HEALTH_MONITOR_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ResourceNotFoundError(HealthMonitorError):
    """Exception raised when a resource is not found."""
    
    def __init__(self, message: str, error_code: str = "RESOURCE_NOT_FOUND"):
        super().__init__(message, error_code)


class InvalidHealthStatusError(HealthMonitorError):
    """Exception raised when an invalid health status is provided."""
    
    def __init__(self, message: str, error_code: str = "INVALID_HEALTH_STATUS"):
        super().__init__(message, error_code)


class HealthChangeReasonRequiredError(HealthMonitorError):
    """Exception raised when a manual health status change gives no reason."""

    def __init__(self, message: str, error_code: str = "HEALTH_CHANGE_REASON_REQUIRED"):
        super().__init__(message, error_code)


class HealthCheckConfigNotFoundError(HealthMonitorError):
    """Exception raised when health check config is not found."""
    
    def __init__(self, message: str, error_code: str = "HEALTH_CHECK_CONFIG_NOT_FOUND"):
        super().__init__(message, error_code)


class InvalidHealthCheckConfigError(HealthMonitorError):
    """Exception raised when health check configuration is invalid."""

    def __init__(self, message: str, error_code: str = "INVALID_HEALTH_CHECK_CONFIG"):
        super().__init__(message, error_code)


class ProbeTargetRejectedError(HealthMonitorError):
    """Exception raised when a probe URL targets an address the server must not call."""

    def __init__(self, message: str, error_code: str = "PROBE_TARGET_REJECTED"):
        super().__init__(message, error_code)


# =============================================================================
# Probe target guard
# =============================================================================

def _forbidden_probe_address_reason(address: str) -> Optional[str]:
    """
    Why the server must not send a probe to ``address``, or None when it may.

    Private ranges stay allowed -- lab devices live there. Loopback,
    link-local (including the 169.254.169.254 cloud-metadata endpoint),
    unspecified, multicast and reserved addresses are refused, so a
    health check cannot be used to reach the Pychestrate server itself,
    its local services, or the host's metadata service.

    :param address: IPv4 or IPv6 address literal.
    :returns: A human-readable reason, or None when the address is allowed.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "an address that is not valid ({})".format(address)
    mapped = getattr(ip, 'ipv4_mapped', None)
    if mapped is not None:
        ip = mapped
    if ip.is_loopback:
        return "a loopback address ({})".format(ip)
    if ip.is_link_local:
        return "a link-local address ({})".format(ip)
    if ip.is_unspecified:
        return "an unspecified address ({})".format(ip)
    if ip.is_multicast:
        return "a multicast address ({})".format(ip)
    if ip.is_reserved:
        return "a reserved address ({})".format(ip)
    return None


def validate_probe_url(url: str, resolve: bool = True) -> Optional[str]:
    """
    Check that a probe URL is one the server may call.

    :param url: The configured probe URL.
    :param resolve: Also resolve the host name and check every address
                    it resolves to (done at probe time; skipped when a
                    configuration is saved so a temporarily unresolvable
                    device name can still be configured).
    :returns: A human-readable problem, or None when the URL is allowed.
    """
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        return "The probe URL is not a valid URL."
    if parsed.scheme not in PROBE_URL_SCHEMES:
        return "The probe URL must start with http:// or https://."
    host = parsed.hostname
    if host is None or len(host) == 0:
        return "The probe URL must include the device's host name or address."
    if host.lower() == 'localhost' or host.lower().endswith('.localhost'):
        return "The probe URL may not target the Pychestrate server itself (localhost)."

    try:
        ipaddress.ip_address(host)
        literal = True
    except ValueError:
        literal = False

    if literal is True:
        reason = _forbidden_probe_address_reason(host)
        if reason is not None:
            return "The probe URL may not target {}.".format(reason)
        return None

    if resolve is False:
        return None

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except socket.gaierror:
        return "The probe host '{}' could not be resolved.".format(host)
    for info in infos:
        reason = _forbidden_probe_address_reason(info[4][0])
        if reason is not None:
            return "The probe host '{}' resolves to {}, which probes may not target.".format(host, reason)
    return None


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects only to targets :func:`validate_probe_url` allows."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        problem = validate_probe_url(newurl, resolve=True)
        if problem is not None:
            raise ProbeTargetRejectedError("Probe redirect refused: " + problem)
        return super().redirect_request(req, fp, code, msg, headers, newurl)



# =============================================================================
# HealthMonitor Class
# =============================================================================

class HealthMonitor:
    """
    Manager class for resource health tracking and automated health checks.
    
    This class handles all health-related operations including:
    - Updating resource health status with transition logging
    - Retrieving health status history
    - Configuring automated health checks
    - Executing health checks (URL probe or command)
    - Notifying allocation holders of status changes
    
    Validates: Requirements 6.1-6.6
    """
    
    def __init__(self, db_session: DbSession, audit_logger=None):
        """
        Initialize the HealthMonitor with a database session.
        
        :param db_session: SQLAlchemy database session
        :param audit_logger: Optional AuditLogger instance for audit logging
        """
        self._db_session = db_session
        self._audit_logger = audit_logger
    
    # =========================================================================
    # Health Status Management
    # =========================================================================
    
    def update_health_status(
        self,
        resource_id: int,
        status: str,
        reason: str = "",
        user_id: str = None,
        triggered_by: str = TRIGGER_USER
    ) -> HealthTransitionResponse:
        """
        Update resource health status with transition logging.
        
        :param resource_id: The resource's unique identifier
        :param status: New health status (online, offline, degraded, maintenance)
        :param reason: Reason for the status change
        :param user_id: The ID of the user making the change (if applicable)
        :param triggered_by: What triggered the change (user, health_check, system)
        :returns: HealthTransitionResponse with the transition details
        :raises ResourceNotFoundError: If resource is not found
        :raises InvalidHealthStatusError: If status is invalid
        :raises HealthChangeReasonRequiredError: If a user-triggered change has
                                                 no reason (fewer than
                                                 MIN_MANUAL_REASON_LENGTH
                                                 characters)

        Validates: Requirements 6.1, 6.2
        """
        from ccai.pychestrate.core.orm import Resource, HealthTransitionLog

        # Validate status
        if status not in VALID_HEALTH_STATUSES:
            raise InvalidHealthStatusError(
                f"Health status must be one of: {', '.join(sorted(VALID_HEALTH_STATUSES))}"
            )

        # A person changing the status must say why
        if triggered_by == TRIGGER_USER and len((reason or "").strip()) < MIN_MANUAL_REASON_LENGTH:
            raise HealthChangeReasonRequiredError(
                f"A reason of at least {MIN_MANUAL_REASON_LENGTH} characters is required "
                "for a manual health status change"
            )

        # Get the resource
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        old_status = resource.health_status
        
        # Only log transition if status actually changed
        if old_status != status:
            # Create transition log entry
            now = utc_now()
            transition = HealthTransitionLog(
                resource_id=resource_id,
                old_status=old_status,
                new_status=status,
                reason=reason,
                triggered_by=triggered_by,
                user_id=user_id,
                timestamp=now
            )
            self._db_session.add(transition)
            
            # Update resource status
            resource.health_status = status
            resource.updated_at = now
            
            self._db_session.commit()
            
            # Log the health status change event
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type='health_status_changed',
                    user_id=str(user_id) if user_id else None,
                    details={
                        "resource_id": resource_id,
                        "resource_name": resource.name,
                        "old_status": old_status,
                        "new_status": status,
                        "reason": reason,
                        "triggered_by": triggered_by
                    }
                )
            
            return HealthTransitionResponse(
                id=transition.id,
                resource_id=resource_id,
                resource_name=resource.name,
                old_status=old_status,
                new_status=status,
                reason=reason,
                triggered_by=triggered_by,
                user_id=str(user_id) if user_id else None,
                timestamp=now
            )
        else:
            # No change, return a response indicating current state
            return HealthTransitionResponse(
                id=0,  # No transition logged
                resource_id=resource_id,
                resource_name=resource.name,
                old_status=old_status,
                new_status=status,
                reason=reason,
                triggered_by=triggered_by,
                user_id=str(user_id) if user_id else None,
                timestamp=utc_now()
            )
    
    def get_health_history(
        self,
        resource_id: int,
        offset: int = 0,
        limit: int = 50
    ) -> HealthTransitionListResponse:
        """
        Get health status transition history for a resource.
        
        :param resource_id: The resource's unique identifier
        :param offset: Number of records to skip
        :param limit: Maximum number of records to return
        :returns: HealthTransitionListResponse with paginated transition list
        :raises ResourceNotFoundError: If resource is not found
        
        Validates: Requirements 6.2
        """
        from ccai.pychestrate.core.orm import Resource, HealthTransitionLog
        
        # Verify resource exists
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        # Query transitions
        query = self._db_session.query(HealthTransitionLog).filter(
            HealthTransitionLog.resource_id == resource_id
        ).order_by(HealthTransitionLog.timestamp.desc())
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        transitions = query.offset(offset).limit(limit).all()
        
        return HealthTransitionListResponse(
            transitions=[
                HealthTransitionResponse(
                    id=t.id,
                    resource_id=t.resource_id,
                    resource_name=resource.name,
                    old_status=t.old_status,
                    new_status=t.new_status,
                    reason=t.reason,
                    triggered_by=t.triggered_by,
                    user_id=str(t.user_id) if t.user_id else None,
                    timestamp=t.timestamp
                )
                for t in transitions
            ],
            total=total,
            offset=offset,
            limit=limit
        )
    
    def get_current_health_status(self, resource_id: int) -> str:
        """
        Get the current health status of a resource.
        
        :param resource_id: The resource's unique identifier
        :returns: Current health status string
        :raises ResourceNotFoundError: If resource is not found
        """
        from ccai.pychestrate.core.orm import Resource
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        return resource.health_status


    # =========================================================================
    # Health Check Configuration
    # =========================================================================
    
    def configure_health_check(
        self,
        config: HealthCheckConfigRequest,
        user_id: str = None
    ) -> HealthCheckConfigResponse:
        """
        Configure automated health check for a resource.
        
        :param config: Health check configuration request
        :param user_id: The ID of the user configuring the health check
        :returns: HealthCheckConfigResponse with the configuration
        :raises ResourceNotFoundError: If resource is not found
        :raises InvalidHealthCheckConfigError: If configuration is invalid
        
        Validates: Requirements 6.5
        """
        from ccai.pychestrate.core.orm import Resource, HealthCheckConfig
        
        # Validate configuration
        if config.probe_command:
            raise InvalidHealthCheckConfigError(COMMAND_PROBES_UNSUPPORTED_MESSAGE)

        if not config.probe_url:
            raise InvalidHealthCheckConfigError(
                "A probe URL is required (for example http://10.0.4.21/health)."
            )

        url_problem = validate_probe_url(config.probe_url, resolve=False)
        if url_problem is not None:
            raise InvalidHealthCheckConfigError(url_problem)

        if config.timeout_seconds > MAX_PROBE_TIMEOUT_SECONDS:
            raise InvalidHealthCheckConfigError(
                "The probe timeout may be at most {} seconds.".format(MAX_PROBE_TIMEOUT_SECONDS)
            )

        if config.interval_seconds < 1:
            raise InvalidHealthCheckConfigError(
                "interval_seconds must be at least 1", error_code="INTERVAL_TOO_SHORT"
            )
        
        if config.timeout_seconds < 1:
            raise InvalidHealthCheckConfigError(
                "timeout_seconds must be at least 1", error_code="TIMEOUT_TOO_SHORT"
            )
        
        if config.failure_threshold < 1:
            raise InvalidHealthCheckConfigError(
                "failure_threshold must be at least 1", error_code="FAILURE_THRESHOLD_TOO_LOW"
            )
        
        if config.success_threshold < 1:
            raise InvalidHealthCheckConfigError(
                "success_threshold must be at least 1", error_code="SUCCESS_THRESHOLD_TOO_LOW"
            )
        
        # Get the resource
        resource = self._db_session.query(Resource).filter(
            Resource.id == config.resource_id
        ).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{config.resource_id}' not found")
        
        # Check if config already exists
        existing_config = self._db_session.query(HealthCheckConfig).filter(
            HealthCheckConfig.resource_id == config.resource_id
        ).first()
        
        if existing_config:
            # Update existing config
            existing_config.probe_url = config.probe_url
            existing_config.probe_command = config.probe_command
            existing_config.interval_seconds = config.interval_seconds
            existing_config.timeout_seconds = config.timeout_seconds
            existing_config.failure_threshold = config.failure_threshold
            existing_config.success_threshold = config.success_threshold
            existing_config.enabled = config.enabled
            
            self._db_session.commit()
            
            return self._config_to_response(existing_config, resource.name)
        else:
            # Create new config
            new_config = HealthCheckConfig(
                resource_id=config.resource_id,
                probe_url=config.probe_url,
                probe_command=config.probe_command,
                interval_seconds=config.interval_seconds,
                timeout_seconds=config.timeout_seconds,
                failure_threshold=config.failure_threshold,
                success_threshold=config.success_threshold,
                consecutive_failures=0,
                consecutive_successes=0,
                last_check_time=None,
                last_check_result=None,
                enabled=config.enabled
            )
            
            self._db_session.add(new_config)
            self._db_session.commit()
            
            # Log the health check configuration event
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type='health_check_configured',
                    user_id=str(user_id) if user_id else None,
                    details={
                        "resource_id": config.resource_id,
                        "resource_name": resource.name,
                        "probe_url": config.probe_url,
                        "probe_command": config.probe_command,
                        "enabled": config.enabled
                    }
                )
            
            return self._config_to_response(new_config, resource.name)
    
    def get_health_check_config(self, resource_id: int) -> Optional[HealthCheckConfigResponse]:
        """
        Get health check configuration for a resource.
        
        :param resource_id: The resource's unique identifier
        :returns: HealthCheckConfigResponse if found, None otherwise
        
        Validates: Requirements 6.5
        """
        from ccai.pychestrate.core.orm import Resource, HealthCheckConfig
        
        # Get the resource
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            return None
        
        # Get the config
        config = self._db_session.query(HealthCheckConfig).filter(
            HealthCheckConfig.resource_id == resource_id
        ).first()
        
        if not config:
            return None
        
        return self._config_to_response(config, resource.name)
    
    def delete_health_check_config(self, resource_id: int, user_id: str = None) -> None:
        """
        Delete health check configuration for a resource.
        
        :param resource_id: The resource's unique identifier
        :param user_id: The ID of the user deleting the configuration
        :raises HealthCheckConfigNotFoundError: If config is not found
        """
        from ccai.pychestrate.core.orm import HealthCheckConfig
        
        config = self._db_session.query(HealthCheckConfig).filter(
            HealthCheckConfig.resource_id == resource_id
        ).first()
        
        if not config:
            raise HealthCheckConfigNotFoundError(
                f"Health check config for resource '{resource_id}' not found"
            )
        
        self._db_session.delete(config)
        self._db_session.commit()
        
        # Log the deletion
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type='health_check_deleted',
                user_id=str(user_id) if user_id else None,
                details={"resource_id": resource_id}
            )


    # =========================================================================
    # Health Check Execution
    # =========================================================================
    
    def run_health_check(self, resource_id: int) -> HealthCheckResult:
        """
        Run health check for a resource and update status based on thresholds.
        
        :param resource_id: The resource's unique identifier
        :returns: HealthCheckResult with the check outcome
        :raises ResourceNotFoundError: If resource is not found
        :raises HealthCheckConfigNotFoundError: If health check is not configured
        
        Validates: Requirements 6.5, 6.6
        """
        from ccai.pychestrate.core.orm import Resource, HealthCheckConfig
        
        # Get the resource
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        # Get the config
        config = self._db_session.query(HealthCheckConfig).filter(
            HealthCheckConfig.resource_id == resource_id
        ).first()
        
        if not config:
            raise HealthCheckConfigNotFoundError(
                f"Health check not configured for resource '{resource_id}'"
            )
        
        if not config.enabled:
            return HealthCheckResult(
                resource_id=resource_id,
                resource_name=resource.name,
                healthy=resource.health_status == 'online',
                old_status=resource.health_status,
                new_status=resource.health_status,
                status_changed=False,
                error_message="Health check is disabled"
            )
        
        # Configurations saved before command probes were withdrawn are
        # never executed; the resource keeps its status and the result
        # explains how to reconfigure it.
        if not config.probe_url:
            return HealthCheckResult(
                resource_id=resource_id,
                resource_name=resource.name,
                healthy=resource.health_status == 'online',
                old_status=resource.health_status,
                new_status=resource.health_status,
                status_changed=False,
                error_message=COMMAND_PROBES_UNSUPPORTED_MESSAGE
            )

        # Execute the health check
        check_passed = False
        error_message = None

        try:
            check_passed = self._execute_url_probe(
                config.probe_url, min(config.timeout_seconds, MAX_PROBE_TIMEOUT_SECONDS)
            )
        except ProbeTargetRejectedError as rejected:
            # A target the server may not call is a configuration
            # problem, not evidence about the device's health.
            return HealthCheckResult(
                resource_id=resource_id,
                resource_name=resource.name,
                healthy=resource.health_status == 'online',
                old_status=resource.health_status,
                new_status=resource.health_status,
                status_changed=False,
                error_message=str(rejected)
            )
        except Exception as e:
            check_passed = False
            error_message = str(e)
        
        # Update consecutive counters
        now = utc_now()
        old_status = resource.health_status
        new_status = old_status
        status_changed = False
        
        if check_passed:
            config.consecutive_successes += 1
            config.consecutive_failures = 0
            
            # Check if we should mark as healthy
            if config.consecutive_successes >= config.success_threshold:
                if old_status in ('offline', 'degraded'):
                    new_status = 'online'
                    status_changed = True
        else:
            config.consecutive_failures += 1
            config.consecutive_successes = 0
            
            # Check if we should mark as unhealthy
            if config.consecutive_failures >= config.failure_threshold:
                if old_status == 'online':
                    new_status = 'degraded'
                    status_changed = True
                elif old_status == 'degraded':
                    new_status = 'offline'
                    status_changed = True
        
        config.last_check_time = now
        config.last_check_result = check_passed
        
        # Update status if changed
        if status_changed:
            reason = f"Health check {'passed' if check_passed else 'failed'} - threshold reached"
            if error_message:
                reason += f": {error_message}"
            
            self.update_health_status(
                resource_id=resource_id,
                status=new_status,
                reason=reason,
                triggered_by=TRIGGER_HEALTH_CHECK
            )
        else:
            self._db_session.commit()
        
        return HealthCheckResult(
            resource_id=resource_id,
            resource_name=resource.name,
            healthy=check_passed,
            old_status=old_status,
            new_status=new_status,
            status_changed=status_changed,
            error_message=error_message
        )
    
    def run_all_health_checks(self) -> HealthCheckSummary:
        """
        Run all configured and enabled health checks.
        
        :returns: HealthCheckSummary with results for all checks
        
        Validates: Requirements 6.5, 6.6
        """
        from ccai.pychestrate.core.orm import HealthCheckConfig
        
        # Get all enabled health check configs
        configs = self._db_session.query(HealthCheckConfig).filter(
            HealthCheckConfig.enabled == True
        ).all()
        
        results = []
        healthy_count = 0
        unhealthy_count = 0
        status_changes = 0
        
        for config in configs:
            try:
                result = self.run_health_check(config.resource_id)
                results.append(result)
                
                if result.healthy:
                    healthy_count += 1
                else:
                    unhealthy_count += 1
                
                if result.status_changed:
                    status_changes += 1
            except Exception as e:
                # Log error but continue with other checks
                results.append(HealthCheckResult(
                    resource_id=config.resource_id,
                    resource_name="unknown",
                    healthy=False,
                    old_status="unknown",
                    new_status="unknown",
                    status_changed=False,
                    error_message=str(e)
                ))
                unhealthy_count += 1
        
        return HealthCheckSummary(
            total_checked=len(results),
            healthy_count=healthy_count,
            unhealthy_count=unhealthy_count,
            status_changes=status_changes,
            results=results
        )
    
    def due_health_check_resource_ids(self, now: Optional[datetime] = None) -> List[int]:
        """
        List the resources whose health check is due: enabled, with a
        probe URL, and never run or last run at least ``interval_seconds``
        ago. Never-checked resources come first, then the longest-waiting.

        :param now: The time to judge against (defaults to now, UTC)
        :returns: Resource IDs in the order their checks should run

        Validates: Requirements 6.5
        """
        from ccai.pychestrate.core.orm import HealthCheckConfig

        now = utc_now() if now is None else ensure_utc(now)

        configs = self._db_session.query(HealthCheckConfig).filter(
            HealthCheckConfig.enabled == True,
            HealthCheckConfig.probe_url != None
        ).all()

        waiting = []
        for config in configs:
            last_check_time = config.last_check_time
            if last_check_time is None:
                waiting.append((0, now, config.resource_id))
                continue
            last_check_time = ensure_utc(last_check_time)
            interval = timedelta(seconds=max(config.interval_seconds or 0, 1))
            if last_check_time + interval <= now:
                waiting.append((1, last_check_time, config.resource_id))

        waiting.sort()
        return [resource_id for _, _, resource_id in waiting]

    def run_due_health_checks(
        self,
        now: Optional[datetime] = None,
        should_continue: Optional[Callable[[], bool]] = None
    ) -> HealthCheckSummary:
        """
        Run the health checks that are due (see
        :meth:`due_health_check_resource_ids`), longest-waiting first. This
        is what the background scheduler runs, so each check keeps its
        configured interval without anyone pressing "Run check".

        :param now: The time to judge due-ness against (defaults to now, UTC)
        :param should_continue: Asked before each check; the run stops
            early when it returns False (the caller's time budget is spent
            or it lost its lease). Checks left over stay due.
        :returns: HealthCheckSummary for the checks that ran

        Validates: Requirements 6.5, 6.6
        """
        results = []
        healthy_count = 0
        unhealthy_count = 0
        status_changes = 0

        for resource_id in self.due_health_check_resource_ids(now=now):
            if should_continue is not None and not should_continue():
                break
            try:
                result = self.run_health_check(resource_id)
            except Exception as e:
                # Keep the session usable for the checks that follow.
                self._db_session.rollback()
                result = HealthCheckResult(
                    resource_id=resource_id,
                    resource_name="unknown",
                    healthy=False,
                    old_status="unknown",
                    new_status="unknown",
                    status_changed=False,
                    error_message=str(e)
                )
            results.append(result)
            if result.healthy:
                healthy_count += 1
            else:
                unhealthy_count += 1
            if result.status_changed:
                status_changes += 1

        return HealthCheckSummary(
            total_checked=len(results),
            healthy_count=healthy_count,
            unhealthy_count=unhealthy_count,
            status_changes=status_changes,
            results=results
        )

    def _execute_url_probe(self, url: str, timeout_seconds: int) -> bool:
        """
        Execute a URL health probe.
        
        The target (and every redirect hop) is checked with
        :func:`validate_probe_url` so a probe cannot be pointed at the
        Pychestrate server, its local services, or a metadata endpoint.

        :param url: URL to probe
        :param timeout_seconds: Timeout in seconds
        :returns: True if probe succeeded (HTTP 2xx), False otherwise
        :raises ProbeTargetRejectedError: If the target may not be called
        """
        problem = validate_probe_url(url, resolve=True)
        if problem is not None:
            raise ProbeTargetRejectedError(problem)

        opener = urllib.request.build_opener(_GuardedRedirectHandler())
        try:
            request = urllib.request.Request(url, method='GET')
            with opener.open(request, timeout=timeout_seconds) as response:
                return 200 <= response.status < 300
        except ProbeTargetRejectedError:
            raise
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            return False
        except Exception:
            return False


    # =========================================================================
    # Allocation Blocking
    # =========================================================================
    
    def is_resource_healthy_for_allocation(self, resource_id: int) -> bool:
        """
        Check if a resource's health status allows allocation.
        
        :param resource_id: The resource's unique identifier
        :returns: True if resource can be allocated, False if blocked
        
        Validates: Requirements 6.3
        """
        from ccai.pychestrate.core.orm import Resource
        
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            return False
        
        return resource.health_status not in BLOCKED_HEALTH_STATUSES
    
    def get_blocked_health_statuses(self) -> set:
        """
        Get the set of health statuses that block allocation.
        
        :returns: Set of health status strings that block allocation
        """
        return BLOCKED_HEALTH_STATUSES.copy()
    
    # =========================================================================
    # Notification
    # =========================================================================
    
    def notify_allocation_holders(self, resource_id: int, message: str) -> int:
        """
        Notify users with active allocations of a resource status change.
        
        :param resource_id: The resource's unique identifier
        :param message: Message to send to allocation holders
        :returns: Number of users notified
        
        Validates: Requirements 6.4
        """
        from ccai.pychestrate.core.orm import Resource, Allocation, AllocationStatus
        
        # Get the resource
        resource = self._db_session.query(Resource).filter(Resource.id == resource_id).first()
        
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found")
        
        # Get active allocations
        active_allocations = self._db_session.query(Allocation).filter(
            Allocation.resource_id == resource_id,
            Allocation.status == AllocationStatus.ACTIVE.value
        ).all()
        
        # Collect unique user IDs
        user_ids = set()
        for allocation in active_allocations:
            if allocation.user_id:
                user_ids.add(str(allocation.user_id))
        
        # Log notification event for each user
        if self._audit_logger:
            for user_id in user_ids:
                self._audit_logger.log_event(
                    event_type='health_notification_sent',
                    user_id=user_id,
                    details={
                        "resource_id": resource_id,
                        "resource_name": resource.name,
                        "message": message,
                        "allocation_count": len([a for a in active_allocations if str(a.user_id) == user_id])
                    }
                )
        
        return len(user_ids)
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _config_to_response(self, config, resource_name: str) -> HealthCheckConfigResponse:
        """
        Convert a HealthCheckConfig ORM object to a response dataclass.
        
        :param config: HealthCheckConfig ORM object
        :param resource_name: Name of the resource
        :returns: HealthCheckConfigResponse
        """
        return HealthCheckConfigResponse(
            id=config.id,
            resource_id=config.resource_id,
            resource_name=resource_name,
            probe_url=config.probe_url,
            probe_command=config.probe_command,
            interval_seconds=config.interval_seconds,
            timeout_seconds=config.timeout_seconds,
            failure_threshold=config.failure_threshold,
            success_threshold=config.success_threshold,
            consecutive_failures=config.consecutive_failures,
            consecutive_successes=config.consecutive_successes,
            last_check_time=config.last_check_time,
            last_check_result=config.last_check_result,
            enabled=config.enabled
        )

