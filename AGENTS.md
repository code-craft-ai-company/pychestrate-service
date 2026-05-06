# Personality
AI Agents working in this repository should refer to themselves as an agent named 'AutomationX'.


# Rules
- Look in the '<repository>/specs' folder for specification files that help to steer development work
- Look in the '<repository>/userguide' folder for files containing standards and conventions
- Look in the '<repository>/prompts' folder for pre-build prompts
- Do not create or modify files inside the .venv folder, they are modified by the setup scripts

# Project Overview
This folder contains the source code for the 'Automation Mojo - Pychestrate' web service. The 'Automation Mojo - Pychestrate' website acts as the user interface for the 'Pychestrate' continuous integration and orchestration system.  The 'Pychestrate' web service acts as the user interface for a microservice based orchestration systems.  The 'Pychestrate' web interfaces will provide.

* System Configuration - Global Variables, Security, User Management, Secrets and Credentials
* Resource Management - Track and deconflict usage of ( devices, IPs ) with checkout and checkin
* Build Orchestrations
* Infrastructre Orchestration
* Test Orchestrations
* Projects - Provide a way to organize jobs and resources


# Testing Conventions
The 'pychestrate-service' package repository utilizes the 'testbase' framework in order to run tests.  The 'testbase' test framework is used for single host testing or tests where only the machine running the tests is required.

Test are organized at the lowest level by resource configuration.  For example, all the single host tests for this package are in the folder 'source/testroots/automojo/tests/singlehost/pychestrate'.

AI based testing should run only the 'singlehost' tests tests with:

```
    source .venv/bin/activate
    
    testbase testing run --root source/testroots/automojo --includes=automojo.tests.singlehost --output=./.output
```

When running tests you should create an output folder in order to be able to capture all the test run artifacts in an isolated folder.

## XTest Pages
For testing controls, create a 'xtest' leaf that is accessible in debug and development environments. The base '/xtest' path has links
to all the control test pages.  The control test pages contain fixed, no backend required JSON data that is used to test individual
controls. For example 'xtest/build-info-card'


## Implementation
The REST API surface runs on `automojo.webworks` (the Automation Mojo native web framework).  Routes are registered with `@app.attach_route(...)`; the runtime request type is `automojo.webworks.routing.request.Request` and the response types live under `automojo.webworks.routing.response`.  Flask and flask_restx are NOT installed in the production environment — any module that imports `flask` or `flask_restx` will fail at import time inside the running service.

The customer-facing web interface also runs on webworks (see "Web Interface" below); flask is no longer used anywhere in the production bootstrap.

For details on the framework state, the dead pre-migration scaffold, and the RFC 7807 problem-document contract, see [userguide/09-00-code-organization-and-conventions.rst](userguide/09-00-code-organization-and-conventions.rst).

## Web Services Entrypoint
The main entry point is `<repository folder>/source/site/app_pychestrate_main.py`.  It calls `automojo.webworks.webapplication.establish_webapp_persona` to build the app, registers feature routes via `register_service_extensions()`, runs `app.startup()`, installs `PychestrateSessionMiddleware` (per-request SQLAlchemy session + cookie-resolved actor), and then serves with `automojo.webworks.wsgi.server.run_server`.

## Web Interface
The customer-facing web interface code is organized under `<repository folder>/source/site/automojo/pychestrate/webservice/webinterface/` and runs on webworks alongside the REST API. The three blueprints (`/config`, `/resources`, `/projects`) each expose a top-level `register_<area>_routes(*, app)` registrar that `app_pychestrate_main` invokes during bootstrap. Templates render through the jinja2 + `url_for` shim in `webinterface/foundation`; sessions are HMAC-signed cookies; CSRF is enforced per-POST via `auth_guard.enforce_csrf_or_redirect`.

Rules:

* All interactions with the data model should go through a postback URL and then through functions in the data-access module.  The consumer-facing web interface should not directly use any REST APIs as they require special authentication.
* Per-feature route modules (`routes_*.py`) define their own lazy-import builder seams locally — never import a builder from a sibling per-feature module, otherwise a mock patch on one freezes the binding in the other.


## REST API Interface
The REST API is published on the same webworks app as the web interface entrypoint and consumed by the (future) Automation Mojo website code as well as by tests and the `pyc` CLI.  Routes are versioned with a `/api/v1/` prefix; for example:

https://automationmojo.com/api/v1/flags

REST routes for a given feature live next to the feature module under `<repository folder>/source/site/automojo/pychestrate/webservice/<feature>/restapi/v1/<feature>_routes.py`.  Each `*_routes.py` exposes a `register_<feature>_routes(*, app, version_prefix)` function that the bootstrap calls from `register_service_extensions()`.  See `webservice/identity/flags/restapi/v1/flags_routes.py` for the reference template.

Sibling `*_controller.py` files — written against `flask_restx` before the webworks migration — may still exist next to some `*_routes.py` files.  They are dead-on-import scaffold and **must not be refit**; port them to webworks then delete the controller (see the userguide note for the convention).


# Code Naming Conventions
The code naming conventions of this repository follows the [Automation Mojo Python Naming Conventions](https://github.com/automationmojo/automojo-docs/blob/main/userguide/10-01-naming-conventions.rst)


# Code Structure
The code structure of this repository follows the [Automation Mojo Python Code Structure Standards](https://github.com/automationmojo/automojo-docs/blob/main/userguide/10-01-code-organization.rst)


# Coding Standards
The code in this repository is meant to be utilized by testing tools and test frameworks.  Therefore, the code must prioritize:

*  debuggability over performance
*  readability over conciseness

For all the code in this repository, follow the coding standards specified at [Coding Standards](https://github.com/automationmojo/automojo-docs/blob/main/userguide/10-00-coding-standards.rst)


# CSS Formatting
When writing CSS in html document and css documents, do not optimize for whitespace performance. Leave the CSS declarations spread across multiple lines as below:

```
body {
    box-sizing: border-box;
    background-color: var(--color-content-background);
}
```

# Pack Management
This project utilizes python poetry for package management.  The dependencies are updated with the command:

```
    poetry update --no-cache
```

# Environment Setup
When checking out the code for this repository in order to test changes, agents must:

* run the 'repository-setup/rehome-repository' script.  It creates a needed '.env' file.
* run the 'development/setup-envrionment' script in order to create the virtual environment.

# Writing Tests

A 'testbase' test takes the form of a function with a 'test_' prefix like so:

```
def test_something():
    return
```

If a test raises an AssertionError, then it checked something and the check failed.  That is a Failure.  If the test raises any other exception, then the test framework treats that as an Error much like the 'unittest' framework does.

You can create resource factories.

```
@testbase.register.resource_factory()
def create_landscape(constraints={}) -> Generator[Landscape, None, None]:
    """
        Creates the global :class:`Landscape` instance.

        :param constraints: Optional dictionary of constraints used while constructing the Landscape.

        :returns: A generator yielding the Landscape object.
    """
    lscape = LandscapeSingleton()
    yield lscape
```

You can create resources using the factories in a scope in the test tree.  Resources have scope for every test below where they are declared.

```
testbase.originate.parameter(create_landscape, identifier='lscape')
```

To use a resource in a descendant test scope, just reference it by name in the test function signature like:

```
def test_use_landscape(lscape: Landscape):

    blah = lscape.get_something()
    testbase.assert_equal(blah is not None, True)
    return

```

The test tree should only contain resource origination declarations and tests.  It should not contain factories unless the usage of the factory is very isolated.  It is preferable to place factories in a folder such as a factory that creates the AutomationPodSimple object might be located at 'source/testroots/automojo/testshared/factories/automationpods/automationpodsimple.py'

# Using TestBase Mocking

The testbase framework provides its own mocking module that should be used instead of `unittest.mock`. Import the mocking utilities from `automojo.testbase.mocking`.

## Basic Mock Usage

```python
from automojo.testbase.mocking import Mock

# Create a mock object
mock = Mock()

# Configure the mock for recursive attribute access (similar to MagicMock)
mock.configure(recursive=True)

# Get the mock context for configuration
ctx = mock.mock_context()

# Set attributes on the mock
ctx.set_attribute('id', 'test-id')
ctx.set_attribute('name', 'test-name')

# Mock a method with a return value
ctx.mock_method('some_method', return_value='expected_value')

# Mock a method with a side effect (callable)
ctx.mock_method('another_method', side_effect=lambda: 'dynamic_value')

# Mock a property
ctx.mock_property('some_property', return_value='prop_value')
```

## Chaining Mock Calls

For chained method calls like `session.query(Model).filter(...).first()`:

```python
from automojo.testbase.mocking import Mock

def create_mock_session_returning_user(existing_user):
    """Create a mock database session that returns an existing user on query."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    mock_query = Mock()
    mock_query.configure(recursive=True)
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', return_value=existing_user)
    
    mock_query.mock_context().mock_method('filter', return_value=mock_filter)
    mock_session.mock_context().mock_method('query', return_value=mock_query)
    
    return mock_session
```

## Using Side Effects for Multiple Calls

```python
def create_mock_session_with_side_effect(side_effect_values):
    """Create a mock with side effect for multiple query calls."""
    mock_session = Mock()
    mock_session.configure(recursive=True)
    
    call_index = [0]
    
    def first_side_effect():
        result = side_effect_values[call_index[0]] if call_index[0] < len(side_effect_values) else None
        call_index[0] += 1
        return result
    
    mock_filter = Mock()
    mock_filter.configure(recursive=True)
    mock_filter.mock_context().mock_method('first', side_effect=first_side_effect)
    
    # ... continue chaining
    return mock_session
```

## MockContext Assertion Methods

The `MockContext` provides assertion methods for verifying mock usage:

- `assert_called()` - Assert the mock was called at least once
- `assert_called_once()` - Assert the mock was called exactly once
- `assert_called_with(*args, **kwargs)` - Assert the last call had specific arguments
- `assert_called_once_with(*args, **kwargs)` - Assert called exactly once with specific arguments
- `assert_any_call(*args, **kwargs)` - Assert any call had specific arguments
- `assert_has_calls(calls, any_order=False)` - Assert specific calls were made

## Patching Modules, Classes, and Instances

For patching existing code:

```python
from automojo.testbase.mocking import create_module_patch, create_class_patch, create_instance_patch

# Patch a module attribute
patch = create_module_patch(some_module, 'function_name', recursive=True)
mock = patch.activate()
mock.configure(return_value='mocked_value')
# ... run test ...
patch.deactivate()

# Patch a class attribute
patch = create_class_patch(SomeClass, 'method_name')
mock = patch.activate()
# ... run test ...
patch.deactivate()

# Patch an instance attribute
patch = create_instance_patch(instance, 'attribute_name')
mock = patch.activate()
# ... run test ...
patch.deactivate()
```

## Migration from unittest.mock

| unittest.mock | testbase.mocking |
|---------------|------------------|
| `MagicMock()` | `Mock()` with `mock.configure(recursive=True)` |
| `mock.return_value = x` | `ctx.mock_method('__call__', return_value=x)` or `mock.configure(return_value=x)` |
| `mock.side_effect = fn` | `ctx.mock_method('name', side_effect=fn)` or `mock.configure(side_effect=fn)` |
| `mock.attr = value` | `ctx.set_attribute('attr', value)` |
| `mock.method.return_value` | `ctx.mock_method('method', return_value=value)` |
| `patch('module.attr')` | `create_module_patch(module, 'attr')` |
| `mock.assert_called_once()` | `ctx.assert_called_once()` |


# Evaluating Test Results
There is a machine processable JSOS stream file in the output folder.

"*outputfolder*/testrun_results_stream.jsos"

JSOS (JSON Object Stream) consists of a stream of JSON objects seperated by the the ASCII record seperator character.  When a
test starts it writes a preview to the stream.  The test preview has a 'result' equal to 'UNSET'.  Example Preview:

```
{
    "name": "automojo.tests.singlehost.interop.protocols.dns.test_dnsaddress#test_write_passes_address",
    "monikers": [],
    "pivots": {},
    "instance": "abb868e4-ce97-4bae-b0af-715da0d61d92",
    "parent": "5aad244e-41dc-438f-97a6-bd8365cccdd2",
    "rtype": "TEST",
    "result": "UNSET",
    "start": "2025-07-15T22:07:03.275239",
    "stop": ""
}
```

When a test finishes it writes a result to the stream.  A test result will always have a 'detail' attribute. Example Result:

```
{
    "name": "automojo.tests.singlehost.interop.protocols.dns.test_dnsaddress#test_write_passes_address",
    "monikers": [],
    "pivots": {},
    "instance": "abb868e4-ce97-4bae-b0af-715da0d61d92",
    "parent": "5aad244e-41dc-438f-97a6-bd8365cccdd2",
    "rtype": "TEST",
    "result": "PASSED",
    "start": "2025-07-15T22:07:03.275239",
    "stop": "2025-07-15T22:07:03.276034",
    "detail": {
        "errors": [],
        "failures": [],
        "warnings": []
    }
}
```

# Change Recommendations
Before making a recommendation to change a file.  Make sure you have the latest version of the file.


# Project Specific Rules


# Pull Request Guidelines


# Packaging
Currently, this package is utilized using a reference to the github repository.  It is currently not published.
