# Personality
AI Agents working in this repository should refer to themselves as an agent named 'CodeCraftX'.


# Rules
- Look in the '<repository>/specs' folder for specification files that help to steer development work
- Look in the '<repository>/userguide' folder for files containing standards and conventions
- Look in the '<repository>/prompts' folder for pre-build prompts
- Do not create or modify files inside the .venv folder, they are modified by the setup scripts

# Project Overview
This folder contains the source code for the 'Code Craft AI - Pychestrate' web service. The 'Code Craft AI - Pychestrate' website acts as the user interface for the 'Pychestrate' continuous integration and orchestration system.  The 'Pychestrate' web service acts as the user interface for a microservice based orchestration systems.  The 'Pychestrate' web interfaces will provide.

* System Configuration - Global Variables, Security, User Management, Secrets and Credentials
* Resource Management - Track and deconflict usage of ( devices, IPs ) with checkout and checkin
* Build Orchestrations
* Infrastructre Orchestration
* Test Orchestrations
* Projects - Provide a way to organize jobs and resources


# Testing Conventions
The 'pychestrate-service' package repository utilizes the 'testbase' framework in order to run tests.  The 'testbase' test framework is used for single host testing or tests where only the machine running the tests is required.

Test are organized at the lowest level by resource configuration.  For example, all the single host tests for this package are in the folder 'source/testroots/ccai/tests/singlehost/pychestrate'.

AI based testing should run only the 'singlehost' tests tests with:

```
    source .venv/bin/activate
    
    testbase testing run --root source/testroots/ccai --includes=ccai.tests.singlehost --output=./.output
```

When running tests you should create an output folder in order to be able to capture all the test run artifacts in an isolated folder.

## XTest Pages
For testing controls, create a 'xtest' leaf that is accessible in debug and development environments. The base '/xtest' path has links
to all the control test pages.  The control test pages contain fixed, no backend required JSON data that is used to test individual
controls. For example 'xtest/build-info-card'


## Implementation
The REST API surface runs on `ccai.webworks` (the Code Craft AI native web framework).  Routes are registered with `@app.attach_route(...)`; the runtime request type is `ccai.webworks.routing.request.Request` and the response types live under `ccai.webworks.routing.response`.  Flask and flask_restx are NOT installed in the production environment — any module that imports `flask` or `flask_restx` will fail at import time inside the running service.

The customer-facing web interface also runs on webworks (see "Web Interface" below); flask is no longer used anywhere in the production bootstrap.

For details on the framework state, the dead pre-migration scaffold, and the RFC 7807 problem-document contract, see [userguide/09-00-code-organization-and-conventions.rst](userguide/09-00-code-organization-and-conventions.rst).

## Web Services Entrypoint
The main entry point is `<repository folder>/source/site/app_pychestrate_main.py`.  It calls `ccai.webworks.webapplication.establish_webapp_persona` to build the app, registers feature routes via `register_service_extensions()`, runs `app.startup()`, installs `PychestrateSessionMiddleware` (per-request SQLAlchemy session + cookie-resolved actor), and then serves with `ccai.webworks.wsgi.server.run_server`.

## Web Interface
The customer-facing web interface code is organized under `<repository folder>/source/site/ccai/pychestrate/webservice/webinterface/` and runs on webworks alongside the REST API. The three blueprints (`/config`, `/resources`, `/projects`) each expose a top-level `register_<area>_routes(*, app)` registrar that `app_pychestrate_main` invokes during bootstrap. Templates render through the jinja2 + `url_for` shim in `webinterface/foundation`; sessions are HMAC-signed cookies; CSRF is enforced per-POST via `auth_guard.enforce_csrf_or_redirect`.

Rules:

* All interactions with the data model should go through a postback URL and then through functions in the data-access module.  The consumer-facing web interface should not directly use any REST APIs as they require special authentication.
* Per-feature route modules (`routes_*.py`) define their own lazy-import builder seams locally — never import a builder from a sibling per-feature module, otherwise a mock patch on one freezes the binding in the other.


## REST API Interface
The REST API is published on the same webworks app as the web interface entrypoint and consumed by the (future) Code Craft AI website code as well as by tests and the `pyc` CLI.  Routes are versioned with a `/api/v1/` prefix; for example:

https://code-craft.ai/api/v1/flags

REST routes for a given feature live next to the feature module under `<repository folder>/source/site/ccai/pychestrate/webservice/<feature>/restapi/v1/<feature>_routes.py`.  Each `*_routes.py` exposes a `register_<feature>_routes(*, app, version_prefix)` function that the bootstrap calls from `register_service_extensions()`.  See `webservice/identity/flags/restapi/v1/flags_routes.py` for the reference template.

Sibling `*_controller.py` files — written against `flask_restx` before the webworks migration — may still exist next to some `*_routes.py` files.  They are dead-on-import scaffold and **must not be refit**; port them to webworks then delete the controller (see the userguide note for the convention).


# Code Naming Conventions
The code naming conventions of this repository follows the [Code Craft AI Python Naming Conventions](https://github.com/automationmojo/automojo-docs/blob/main/userguide/10-01-naming-conventions.rst)


# Code Structure
The code structure of this repository follows the [Code Craft AI Python Code Structure Standards](https://github.com/automationmojo/automojo-docs/blob/main/userguide/10-01-code-organization.rst)


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

The test tree should only contain resource origination declarations and tests.  It should not contain factories unless the usage of the factory is very isolated.  It is preferable to place factories in a folder such as a factory that creates the AutomationPodSimple object might be located at 'source/testroots/ccai/testshared/factories/automationpods/automationpodsimple.py'

## Test Granularity

Each test should verify a SINGLE property of the system in
isolation. Composite tests that walk through multiple components
or check multiple properties in one function lose isolation -- if
an early assertion fails, the later checks never run and the
result loses fidelity.

Annotate each test with a docstring stating the feature and the
property under test:

```
def test_unauthenticated_root_redirects_to_unlock_page():
    """
    **Feature: initial-setup-wizard**
    **Property: GET / on a fresh deploy renders the unlock page
    after a 302 redirect.**
    """
    ...
```

When two tests differ only in inputs, parameterize rather than
loop assertions inside one test.

## Resource Lifespan

Factory-produced resources have an explicit lifespan declared at
the call site:

```
from ccai.testbase.resourcelifespan import ResourceLifespan

testbase.originate.parameter(
    create_browser,
    identifier="browser",
    life_span=ResourceLifespan.Session,
)
```

Available lifespans (from `ccai.testbase.resourcelifespan.ResourceLifespan`):

| Lifespan          | Created                            | Use for                                          |
|-------------------|------------------------------------|--------------------------------------------------|
| `Session`         | Once per full test run             | Expensive shared resources: browser, DB pool     |
| `Package`         | Once per test package              | Per-feature setup, e.g. seeded admin account     |
| `Test`            | Once per test function (default)   | Request-scoped state                             |
| `Task`            | Per parameterized task             | Constraint-combo runs                            |

`ResourceLifespan.Test` is the default and cannot be explicitly
passed to `originate.parameter` -- for test-scoped resources, use
`@testbase.attach.parameter()` on the test function instead.

### Example: session-scoped Playwright browser

A real browser launch costs ~1 second. Declare the browser at
`Session` scope so the cost is paid once, and take a fresh
`BrowserContext` per test for cookie isolation:

```
from typing import Generator

from playwright.sync_api import Browser, sync_playwright

from ccai import testbase
from ccai.testbase.resourcelifespan import ResourceLifespan


@testbase.register.resource_factory()
def create_browser(
        constraints: dict = {}
    ) -> Generator[Browser, None, None]:
    """
        Session-scoped Playwright Browser. One process, reused
        across every UI test in the run.
    """
    headless = bool(constraints.get("headless", True))
    playwright_handle = sync_playwright().start()
    try:
        browser = playwright_handle.chromium.launch(headless=headless)
        try:
            yield browser
        finally:
            browser.close()
    finally:
        playwright_handle.stop()
    return


testbase.originate.parameter(
    create_browser,
    identifier="browser",
    life_span=ResourceLifespan.Session,
)


def test_root_redirects_to_unlock_page(browser: Browser):
    """
    **Feature: initial-setup-wizard**
    **Property: GET / on a fresh deploy redirects to /setup/unlock.**
    """
    context = browser.new_context()
    try:
        page = context.new_page()
        page.goto(BASE_URL + "/")
        testbase.assert_true(page.url.endswith("/setup/unlock"))
    finally:
        context.close()
    return
```

Browser tests can run from any OS (macOS / Linux / Windows) since
Playwright bundles its own browser binaries. On a fresh checkout
or CI runner the one-time setup is `playwright install chromium`
(plus `--with-deps` on minimal Linux containers for the X11 /
font system libs).

# Using TestBase Mocking

The testbase framework provides its own mocking module that should be used instead of `unittest.mock`. Import the mocking utilities from `ccai.testbase.mocking`.

## Basic Mock Usage

```python
from ccai.testbase.mocking import Mock

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
from ccai.testbase.mocking import Mock

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
from ccai.testbase.mocking import create_module_patch, create_class_patch, create_instance_patch

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

After a ``testbase testing run`` finishes, the output folder
contains both human-friendly summaries and machine-readable
streams. AI agents should consume results through the
``testbase agents`` command tree rather than parsing JSOS
directly.

## Quick path for agents

```
# Compact pass/fail/total + duration summary.
.venv/bin/testbase agents summary extract \
    --summary-file .output/testrun_summary.json

# Per-test verdict list (one line per test, "PASSED" / "FAILED" / etc.).
.venv/bin/testbase agents testresult list \
    --results-file .output/testrun_results_stream.jsos

# Only on failures: detailed error blocks for failed + errored tests.
.venv/bin/testbase agents testresult failures \
    --results-file .output/testrun_results_stream.jsos

# Run configuration (root, includes/excludes, output path, etc.).
.venv/bin/testbase agents config extract \
    --config-file .output/startup-configuration.json
```

These commands print compact, scriptable output (one record per
line, YAML-ish key/value blocks). Default loop:

1. Run ``testbase agents summary extract`` after the suite.
2. If ``passed == total``, you are done.
3. Otherwise, ``testbase agents testresult failures`` drills
   into the failed-test traceback + assertion detail.

## Raw streams (only when the agents tree is insufficient)

The output folder also carries the underlying JSON files the
``agents`` commands consume:

* ``testrun_summary.json`` -- final summary for the whole run.
* ``testrun_results_stream.jsos`` -- JSOS (JSON Object Stream)
  with one record per test-start (``result == "UNSET"``) and
  one per test-finish (``result`` set, ``detail`` populated).
  Records are separated by the ASCII record-separator character.
* ``startup-configuration.json`` -- the resolved run config:
  root, includes, excludes, marker expressions, output path.

Parse these directly only if you need a field the ``agents``
commands do not surface. Prefer the agent tree for everything
else -- it is the supported, stable contract.

# Change Recommendations
Before making a recommendation to change a file.  Make sure you have the latest version of the file.


# Project Specific Rules


# Pull Request Guidelines


# Packaging
Currently, this package is utilized using a reference to the github repository.  It is currently not published.
