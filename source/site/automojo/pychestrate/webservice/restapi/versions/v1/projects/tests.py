"""
.. module:: tests
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API endpoints for project test management

.. moduleauthor:: Automation Mojo LLC

This module provides REST API endpoints for project test management:
- Test specification CRUD endpoints
- Test job endpoints
- Test results endpoints

Requirements: 12.1
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request, g
from flask_restx import Namespace, Resource, fields

from ..resources.base import (
    require_auth,
    get_pagination_params,
    paginated_response,
    error_response,
    validation_error,
    not_found_error,
    create_error_model,
    exception_to_response,
    AuthenticationError,
    AuthorizationError,
)

from .projects import check_project_permission


# =============================================================================
# Namespace Configuration
# =============================================================================

TESTS_NAMESPACE_PATH = "/projects"

tests_ns = Namespace(
    "Project Tests v1",
    description="Project test management endpoints"
)

# =============================================================================
# API Models
# =============================================================================

error_model = create_error_model(tests_ns)

test_spec_create_model = tests_ns.model('TestSpecCreate', {
    'name': fields.String(required=True, description='Specification name'),
    'framework': fields.String(required=True, description='Test framework (pytest, unittest, testbase, custom)'),
    'test_command': fields.String(required=True, description='Test command'),
    'test_selection': fields.String(description='Test selection pattern'),
    'build_ref': fields.Integer(description='Build specification reference'),
    'infra_ref': fields.Integer(description='Infrastructure specification reference'),
    'environment': fields.Raw(description='Environment variables'),
    'timeout_minutes': fields.Integer(description='Timeout in minutes'),
    'result_format': fields.String(description='Result format (junit_xml, tap, json)'),
    'description': fields.String(description='Description')
})

test_spec_response_model = tests_ns.model('TestSpecResponse', {
    'id': fields.Integer(required=True, description='Specification ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'name': fields.String(required=True, description='Specification name'),
    'framework': fields.String(required=True, description='Test framework'),
    'test_command': fields.String(description='Test command'),
    'test_selection': fields.String(description='Test selection pattern'),
    'build_ref': fields.Integer(description='Build specification reference'),
    'infra_ref': fields.Integer(description='Infrastructure specification reference'),
    'environment': fields.Raw(description='Environment variables'),
    'timeout_minutes': fields.Integer(description='Timeout in minutes'),
    'result_format': fields.String(description='Result format'),
    'description': fields.String(description='Description'),
    'version': fields.Integer(description='Specification version'),
    'created_at': fields.DateTime(description='Creation timestamp'),
    'updated_at': fields.DateTime(description='Last update timestamp')
})

test_spec_list_model = tests_ns.model('TestSpecList', {
    'items': fields.List(fields.Nested(test_spec_response_model), description='List of specifications'),
    'total': fields.Integer(required=True, description='Total'),
    'offset': fields.Integer(required=True, description='Offset'),
    'limit': fields.Integer(required=True, description='Limit')
})

test_result_summary_model = tests_ns.model('TestResultSummary', {
    'total': fields.Integer(description='Total tests'),
    'passed': fields.Integer(description='Passed tests'),
    'failed': fields.Integer(description='Failed tests'),
    'skipped': fields.Integer(description='Skipped tests'),
    'errors': fields.Integer(description='Error count'),
    'duration_seconds': fields.Float(description='Duration in seconds')
})

test_job_trigger_model = tests_ns.model('TestJobTrigger', {
    'spec_id': fields.Integer(required=True, description='Specification ID'),
    'build_id': fields.Integer(description='Build ID to test'),
    'infra_job_id': fields.Integer(description='Infrastructure job ID'),
    'parameters': fields.Raw(description='Parameters')
})

test_job_response_model = tests_ns.model('TestJobResponse', {
    'id': fields.Integer(required=True, description='Job ID'),
    'project_id': fields.Integer(required=True, description='Project ID'),
    'spec_id': fields.Integer(required=True, description='Specification ID'),
    'spec_name': fields.String(description='Specification name'),
    'spec_version': fields.Integer(description='Specification version'),
    'build_id': fields.Integer(description='Build ID'),
    'infra_job_id': fields.Integer(description='Infrastructure job ID'),
    'status': fields.String(required=True, description='Job status'),
    'triggered_by_id': fields.String(description='Triggered by user ID'),
    'triggered_by_username': fields.String(description='Triggered by username'),
    'result_summary': fields.Nested(test_result_summary_model, description='Result summary'),
    'started_at': fields.DateTime(description='Start timestamp'),
    'completed_at': fields.DateTime(description='Completion timestamp'),
    'duration_seconds': fields.Integer(description='Duration in seconds'),
    'created_at': fields.DateTime(description='Creation timestamp')
})

test_job_list_model = tests_ns.model('TestJobList', {
    'items': fields.List(fields.Nested(test_job_response_model), description='List of jobs'),
    'total': fields.Integer(required=True, description='Total'),
    'offset': fields.Integer(required=True, description='Offset'),
    'limit': fields.Integer(required=True, description='Limit')
})

test_case_result_model = tests_ns.model('TestCaseResult', {
    'name': fields.String(required=True, description='Test name'),
    'classname': fields.String(description='Class name'),
    'status': fields.String(required=True, description='Status'),
    'duration_seconds': fields.Float(description='Duration'),
    'failure_message': fields.String(description='Failure message'),
    'failure_trace': fields.String(description='Failure trace')
})


# =============================================================================
# Helper Functions
# =============================================================================

def test_spec_to_dict(spec_response):
    """Convert TestSpecResponse dataclass to dict."""
    return {
        'id': spec_response.id,
        'project_id': spec_response.project_id,
        'name': spec_response.name,
        'framework': spec_response.framework.value if hasattr(spec_response.framework, 'value') else spec_response.framework,
        'test_command': spec_response.test_command,
        'test_selection': spec_response.test_selection,
        'build_ref': spec_response.build_ref,
        'infra_ref': spec_response.infra_ref,
        'environment': spec_response.environment,
        'timeout_minutes': spec_response.timeout_minutes,
        'result_format': spec_response.result_format.value if hasattr(spec_response.result_format, 'value') else spec_response.result_format,
        'description': spec_response.description,
        'version': spec_response.version,
        'created_at': spec_response.created_at.isoformat() if spec_response.created_at else None,
        'updated_at': spec_response.updated_at.isoformat() if spec_response.updated_at else None
    }


def test_job_to_dict(job_response):
    """Convert TestJobResponse dataclass to dict."""
    result_summary = None
    if job_response.result_summary:
        rs = job_response.result_summary
        result_summary = {
            'total': rs.total,
            'passed': rs.passed,
            'failed': rs.failed,
            'skipped': rs.skipped,
            'errors': rs.errors,
            'duration_seconds': rs.duration_seconds
        }
    
    return {
        'id': job_response.id,
        'project_id': job_response.project_id,
        'spec_id': job_response.spec_id,
        'spec_name': job_response.spec_name,
        'spec_version': job_response.spec_version,
        'build_id': job_response.build_id,
        'infra_job_id': job_response.infra_job_id,
        'status': job_response.status.value if hasattr(job_response.status, 'value') else job_response.status,
        'triggered_by_id': str(job_response.triggered_by_id) if job_response.triggered_by_id else None,
        'triggered_by_username': job_response.triggered_by_username,
        'result_summary': result_summary,
        'started_at': job_response.started_at.isoformat() if job_response.started_at else None,
        'completed_at': job_response.completed_at.isoformat() if job_response.completed_at else None,
        'duration_seconds': job_response.duration_seconds,
        'created_at': job_response.created_at.isoformat() if job_response.created_at else None
    }


def test_case_to_dict(case_result):
    """Convert TestCaseResult dataclass to dict."""
    return {
        'name': case_result.name,
        'classname': case_result.classname,
        'status': case_result.status,
        'duration_seconds': case_result.duration_seconds,
        'failure_message': case_result.failure_message,
        'failure_trace': case_result.failure_trace
    }


# =============================================================================
# Test Specification Endpoints
# =============================================================================

@tests_ns.route("/<int:project_id>/test-specs")
@tests_ns.param('project_id', 'The project identifier')
class TestSpecCollection(Resource):
    """Test specification collection."""
    
    @tests_ns.doc('list_test_specs')
    @tests_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @tests_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @tests_ns.response(200, 'Success', test_spec_list_model)
    @tests_ns.response(401, 'Unauthorized', error_model)
    @tests_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def get(self, project_id):
        """List test specifications."""
        try:
            check_project_permission(project_id, 'test.read')
            offset, limit = get_pagination_params()
            
            from automojo.pychestrate.core.managers.test_manager import TestManager
            
            test_manager = TestManager(g.db_session)
            result = test_manager.list_specs(project_id=project_id, offset=offset, limit=limit)
            
            return paginated_response(
                items=[test_spec_to_dict(s) for s in result.specs],
                total=result.total,
                offset=result.offset,
                limit=result.limit
            ), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @tests_ns.doc('create_test_spec')
    @tests_ns.expect(test_spec_create_model)
    @tests_ns.response(201, 'Specification created', test_spec_response_model)
    @tests_ns.response(400, 'Validation error', error_model)
    @tests_ns.response(401, 'Unauthorized', error_model)
    @tests_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Create a test specification."""
        try:
            check_project_permission(project_id, 'test.create')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.test_manager import (
                TestManager, TestSpecCreateRequest, TestFramework, TestResultFormat
            )
            
            framework_str = data.get('framework', 'pytest').lower()
            try:
                framework = TestFramework(framework_str)
            except ValueError:
                return validation_error(f"Invalid framework: {framework_str}", field="framework")
            
            result_format_str = data.get('result_format', 'junit_xml').lower()
            try:
                result_format = TestResultFormat(result_format_str)
            except ValueError:
                result_format = TestResultFormat.JUNIT_XML
            
            create_request = TestSpecCreateRequest(
                name=data.get('name', ''),
                framework=framework,
                test_command=data.get('test_command', ''),
                test_selection=data.get('test_selection', ''),
                build_ref=data.get('build_ref'),
                infra_ref=data.get('infra_ref'),
                environment=data.get('environment', {}),
                timeout_minutes=data.get('timeout_minutes', 60),
                result_format=result_format,
                description=data.get('description', '')
            )
            
            test_manager = TestManager(g.db_session)
            spec_response = test_manager.create_spec(project_id, create_request, g.current_user_id)
            
            return test_spec_to_dict(spec_response), 201
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@tests_ns.route("/<int:project_id>/test-specs/<int:spec_id>")
@tests_ns.param('project_id', 'The project identifier')
@tests_ns.param('spec_id', 'The specification identifier')
class TestSpecItem(Resource):
    """Individual test specification."""
    
    @tests_ns.doc('get_test_spec')
    @tests_ns.response(200, 'Success', test_spec_response_model)
    @tests_ns.response(401, 'Unauthorized', error_model)
    @tests_ns.response(403, 'Forbidden', error_model)
    @tests_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, spec_id):
        """Get a test specification."""
        try:
            check_project_permission(project_id, 'test.read')
            from automojo.pychestrate.core.managers.test_manager import TestManager
            
            test_manager = TestManager(g.db_session)
            spec_response = test_manager.get_spec(spec_id)
            
            if spec_response is None or spec_response.project_id != project_id:
                return not_found_error('TestSpec', str(spec_id))
            
            return test_spec_to_dict(spec_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @tests_ns.doc('delete_test_spec')
    @tests_ns.response(204, 'Specification deleted')
    @tests_ns.response(401, 'Unauthorized', error_model)
    @tests_ns.response(403, 'Forbidden', error_model)
    @tests_ns.response(404, 'Not found', error_model)
    @require_auth
    def delete(self, project_id, spec_id):
        """Delete a test specification."""
        try:
            check_project_permission(project_id, 'test.create')
            from automojo.pychestrate.core.managers.test_manager import TestManager
            
            test_manager = TestManager(g.db_session)
            test_manager.delete_spec(spec_id, g.current_user_id)
            
            return '', 204
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Test Job Endpoints
# =============================================================================

@tests_ns.route("/<int:project_id>/test-jobs")
@tests_ns.param('project_id', 'The project identifier')
class TestJobCollection(Resource):
    """Test job collection."""
    
    @tests_ns.doc('list_test_jobs')
    @tests_ns.param('offset', 'Number of records to skip', type=int, default=0)
    @tests_ns.param('limit', 'Maximum number of records to return', type=int, default=50)
    @tests_ns.param('spec_id', 'Filter by specification ID', type=int)
    @tests_ns.param('status', 'Filter by status', type=str)
    @tests_ns.response(200, 'Success', test_job_list_model)
    @tests_ns.response(401, 'Unauthorized', error_model)
    @tests_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def get(self, project_id):
        """List test jobs."""
        try:
            check_project_permission(project_id, 'test.read')
            offset, limit = get_pagination_params()
            spec_id = request.args.get('spec_id', type=int)
            
            from automojo.pychestrate.core.managers.test_manager import TestManager
            
            test_manager = TestManager(g.db_session)
            result = test_manager.list_jobs(project_id=project_id, spec_id=spec_id, offset=offset, limit=limit)
            
            return paginated_response(
                items=[test_job_to_dict(j) for j in result.jobs],
                total=result.total,
                offset=result.offset,
                limit=result.limit
            ), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)
    
    @tests_ns.doc('trigger_test_job')
    @tests_ns.expect(test_job_trigger_model)
    @tests_ns.response(201, 'Job triggered', test_job_response_model)
    @tests_ns.response(400, 'Validation error', error_model)
    @tests_ns.response(401, 'Unauthorized', error_model)
    @tests_ns.response(403, 'Forbidden', error_model)
    @require_auth
    def post(self, project_id):
        """Trigger a test job."""
        try:
            check_project_permission(project_id, 'test.trigger')
            data = request.json
            if not data:
                return validation_error("Request body required")
            
            from automojo.pychestrate.core.managers.test_manager import TestManager, TestJobTriggerRequest
            
            trigger_request = TestJobTriggerRequest(
                spec_id=data.get('spec_id'),
                build_id=data.get('build_id'),
                infra_job_id=data.get('infra_job_id'),
                parameters=data.get('parameters', {})
            )
            
            test_manager = TestManager(g.db_session)
            job_response = test_manager.trigger_job(trigger_request, g.current_user_id)
            
            return test_job_to_dict(job_response), 201
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@tests_ns.route("/<int:project_id>/test-jobs/<int:job_id>")
@tests_ns.param('project_id', 'The project identifier')
@tests_ns.param('job_id', 'The job identifier')
class TestJobItem(Resource):
    """Individual test job."""
    
    @tests_ns.doc('get_test_job')
    @tests_ns.response(200, 'Success', test_job_response_model)
    @tests_ns.response(401, 'Unauthorized', error_model)
    @tests_ns.response(403, 'Forbidden', error_model)
    @tests_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, job_id):
        """Get a test job."""
        try:
            check_project_permission(project_id, 'test.read')
            from automojo.pychestrate.core.managers.test_manager import TestManager
            
            test_manager = TestManager(g.db_session)
            job_response = test_manager.get_job(job_id)
            
            if job_response is None or job_response.project_id != project_id:
                return not_found_error('TestJob', str(job_id))
            
            return test_job_to_dict(job_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@tests_ns.route("/<int:project_id>/test-jobs/<int:job_id>/cancel")
@tests_ns.param('project_id', 'The project identifier')
@tests_ns.param('job_id', 'The job identifier')
class TestJobCancel(Resource):
    """Test job cancel endpoint."""
    
    @tests_ns.doc('cancel_test_job')
    @tests_ns.response(200, 'Job cancelled', test_job_response_model)
    @tests_ns.response(401, 'Unauthorized', error_model)
    @tests_ns.response(403, 'Forbidden', error_model)
    @tests_ns.response(404, 'Not found', error_model)
    @require_auth
    def post(self, project_id, job_id):
        """Cancel a test job."""
        try:
            check_project_permission(project_id, 'test.cancel')
            from automojo.pychestrate.core.managers.test_manager import TestManager
            
            test_manager = TestManager(g.db_session)
            job_response = test_manager.cancel_job(job_id, g.current_user_id)
            
            return test_job_to_dict(job_response), 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


@tests_ns.route("/<int:project_id>/test-jobs/<int:job_id>/results")
@tests_ns.param('project_id', 'The project identifier')
@tests_ns.param('job_id', 'The job identifier')
class TestJobResults(Resource):
    """Test job results endpoint."""
    
    @tests_ns.doc('get_test_results')
    @tests_ns.response(200, 'Success')
    @tests_ns.response(401, 'Unauthorized', error_model)
    @tests_ns.response(403, 'Forbidden', error_model)
    @tests_ns.response(404, 'Not found', error_model)
    @require_auth
    def get(self, project_id, job_id):
        """Get detailed test results."""
        try:
            check_project_permission(project_id, 'test.read')
            from automojo.pychestrate.core.managers.test_manager import TestManager
            
            test_manager = TestManager(g.db_session)
            results = test_manager.get_test_results(job_id)
            
            return {'results': [test_case_to_dict(r) for r in results]}, 200
        except AuthenticationError as e:
            return error_response('UNAUTHORIZED', str(e), None, 401)
        except AuthorizationError as e:
            return error_response('FORBIDDEN', str(e), {'permission': e.permission}, 403)
        except Exception as e:
            return exception_to_response(e)


# =============================================================================
# Namespace Publishing
# =============================================================================

def publish_namespaces(version_prefix):
    """
    Publish the tests namespace.
    
    :param version_prefix: The version prefix for the API path
    :returns: List of (namespace, path) tuples
    """
    ns_list = [
        (tests_ns, "".join([version_prefix, TESTS_NAMESPACE_PATH]))
    ]
    return ns_list
