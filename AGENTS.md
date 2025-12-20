# Personality
AI Agents working in this repository should refer to themselves as an agent named 'AutomationX'.


# Rules
- Look in the '<repository>/specs' folder for specification files that help to steer development work
- Look in the '<repository>/userguide' folder for files containing standards and conventions
- Look in the '<repository>/prompts' folder for pre-build prompts
- Files inside the .venv folder should not be modified, they are modified by the setup scripts

# Project Overview
This folder contains the source code for the 'Automation Mojo - Pychestrate' web service. The 'Automation Mojo - Pychestrate' website acts as the user interface for the 'Pychestrate' continuous integration and orchestration system.  The 'Pychestrate' web service acts as the user interface for a microservice based orchestration systems.  The 'Pychestrate' web interfaces will provide.

* System Configuration - Global Variables, Security, User Management
* Resource Management - Track and deconflict usage of ( devices, IPs ) with checkout and checkin
* Build Orchestrations
* Infrastructre Orchestration
* Test Orchestrations
* Projects - Provide a way to organize jobs and resources



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
The 'automojo-arcli' package repository utilizes the 'testbase' framework in order to test the functionality of the code.


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

# Change Recommendations
Before making a recommendation to change a file.  Make sure you have the latest version of the file.


# Project Specific Rules


# Pull Request Guidelines


# Packaging
Currently, this package is utilized using a reference to the github repository.  It is currently not published.
