.. _09-00-code-organization-and-conventions:

*********************************
Code Organization and Conventions
*********************************


REST API Framework — Production State
=====================================

The production webservice runs on ``ccai.webworks``.  The bootstrap
at ``source/site/app_pychestrate_main.py`` builds the application via
``ccai.webworks.webapplication.establish_webapp_persona`` and
attaches handlers with ``@app.attach_route(...)``.  The runtime request
type is ``ccai.webworks.routing.request.Request``; the runtime
response types live under ``ccai.webworks.routing.response``
(``Response``, ``JSONResponse``, ``HTMLResponse``, ``RedirectResponse``,
``StreamingResponse``).  Handlers signal HTTP errors by raising
``ccai.webworks.routing.exceptions.HTTPException`` (or one of the
documented subclasses ``NotFound`` / ``BadRequest`` / ``Unauthorized`` /
``Forbidden`` / ``MethodNotAllowed``); the dispatcher converts those to
responses.

Per the migration, **flask and flask_restx are no longer installed in
the production environment**.  Any module that imports ``flask`` or
``flask_restx`` will fail at import time inside the running service.


flask_restx ``*_controller.py`` files are pre-migration scaffold
================================================================

A number of files named ``*_controller.py`` still live next to feature
modules under
``source/site/ccai/pychestrate/webservice/**/restapi/v1/``.  These
were written against ``flask_restx`` before the webworks migration and
are **not loaded by the production bootstrap**.  They are dead code
that exists only as a reference for porting.

Conventions for working with these files:

* **Do not refit the dead controllers** through additional flask-side
  helpers (e.g., a flask error-mapping helper, a flask validator).
  Refactors of dead code are noise; they do not affect any wire
  surface and they obscure the dead-vs-live state for future
  contributors.

* **Port them, do not improve them.**  When a feature's REST surface
  needs work, write a sibling ``*_routes.py`` module under the same
  ``restapi/v1/`` folder that registers handlers via
  ``app.attach_route(...)`` and uses the webworks request / response
  types.  Wire the registration into ``register_service_extensions()``
  in ``app_pychestrate_main.py``.  See
  ``source/site/ccai/pychestrate/webservice/identity/flags/restapi/v1/flags_routes.py``
  for the reference template.

* **Delete the flask_restx controller after the port is wired and
  verified.**  Git history retains the file for any future engineer who
  wants to consult the pre-migration shape.  Do not leave the
  superseded controller alongside its replacement.


RFC 7807 problem documents
==========================

Every 4xx / 5xx response from the webservice's REST surface SHALL be
an RFC 7807 problem document served with the
``application/problem+json`` content type.  The framework-agnostic
builder lives at
``source/site/ccai/pychestrate/webservice/api/problem_json.py``;
the webworks adapter lives at
``source/site/ccai/pychestrate/webservice/api/problem_json_webworks.py``
and exposes ``problem_response_for_http_status(...)`` plus
``build_webworks_problem_response(...)``.

The webworks dispatcher does **not** carry custom bodies through
``HTTPException`` — when a handler raises ``HTTPException`` the
dispatcher rebuilds the body in its content-negotiated shape,
discarding any body the exception carried.  Therefore handlers must
**return** problem responses rather than raise them.  The webworks
helper exposes only return-shaped builders for this reason.
