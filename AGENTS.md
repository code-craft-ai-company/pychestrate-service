# Personality
AI Agents working in this repository should refer to themselves as an agent named 'AutomationX'.


# Project Overview
This folder contains the source code for the 'Automation Mojo - Pychestrate' web service. The 'Automation Mojo - Pychestrate' website acts as the user interface for the 'Pychestrate' continuous integration and orchestration system.

## Implementation
The website along with its REST API interface is written in python and is based on the Flask web framework and Flask-RestX.

## Web Services Entrypoint
The main entry point for the Automation Mojo website for both the REST API and the web interface is located in the file "<repository folder>/source/site/automojo/automojowebsite/app_automjo_website.py".

## Web Interface
The customer facing web interface code is organized under "<repository folder>/source/site/automojo/automojowebsite/webinterface"

Rules:

* All interactions with the data model should go through a postback URL and then through functions in the 'automojo.automojo_website.datum.dbio' module.  The consumer facing web interface should not direct use any REST APIs as they require special authentication.


## REST API Interface
REST APIs, the web service publishes rest API's that are meant to be consumed by the Automation Mojo website code.  There are currently no public REST services
being offered through the company website.  The REST APIs are referenced on the site using a versioned path prefix.  For example, REST API's for version '1' of
rest interface would be prefixed with.

https://automationmojo.com/api/v1/

The code for REST API's is organized under "<repository folder>/source/site/automojo/automojowebsite/restapi"

Specific code for a given versions of API's are organized under a folder associated with the version.  For example the code for version '1' of the API's would be under the folder "<repository folder>/source/site/automojo/automojowebsite/restapi/v1"


# Testing Conventions
The 'pychestrate-core' package repository utilizes the 'testbase' framework in order to run tests.  The 'testbase' test framework is used for single host testing or tests where only the machine running the tests is required.

Test are organized at the lowest level by resource configuration.  For example, all the single host tests are in the folder 'source/testroots/automojo/tests/pychestrate/singlehost/core'.

AI based testing should run only the 'singlehost' tests tests with:

```
    source .venv/bin/activate
    
    testbase testing run --root source/testroots/automojo --includes=automojo.tests.pychestrate.singlehost --output=<desired output folder>
```

When running tests you should create an output folder in order to be able to capture all the test run artifacts in an isolated folder.

## Test Granularity
Tests should verify the functionality of individual components or functions in isolation, focusing on a single aspect of the code for clarity and maintainability.

Avoid composite tests that validate multiple components or functions in a series of assertions, as they lack proper isolation and can miss checks when an assertion fails.


# Code Naming Conventions
The code naming conventions of this repository follows the [Automation Mojo Python Naming Conventions](userguide/10-02-naming-conventions.rst)


# Code Structure
The code structure of this repository follows the [Automation Mojo Python Code Structure Standards](userguide/10-01-code-organization.rst)


# Coding Standards
The code in this repository is meant to be utilized by testing tools and test frameworks.  Therefore, the code must prioritize:

*  debuggability over performance
*  readability over conciseness

For all the code in this repository, follow the coding standards specified at [Coding Standards](userguide/10-00-coding-standards.rst)

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



# Environment Setup

## Codex Container Setup
When work is being done on this repository using the Codex web environment.  Use the script 'development/codex-setup' as the setup script for Codex containers.

## Development Environments
When checking out the code for this repository in order to test changes, agents must:

* run the 'repository-setup/rehome-repository' script.  It creates a needed '.env' file.
* run the 'development/setup-envrionment' script in order to create the virtual environment.

# Running Tests
This repository uses `testbase` tests in order to test the functionality of the code in this package.

When you setup the environment, the '.venv/bin/activate' script is modified so that it will pull in the appropriate environment
variables from the '.env' file.  The environment setup script also creates an alias that makes it easy to run the 'testbase' command from the virtual environment command line.

## TestBase
In order to run the `testbase` tests, you must first enter the virtual environment by running the command:

```
    source <repository-root>/.venv/bin/activate
```

For running the `testbase` tests located under the folder '<repository-root>/source/testbase', use the commands:

``` 
    cd <repository-root>

    testbase testing run --root "<repository-root>/source/testbase" --include  automojo
```

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

# Project Specific Rules


# Pull Request Guidelines


# Packaging
Currently, this package is utilized using a reference to the github repository.  It is currently not published.
