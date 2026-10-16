===========================
Choosing What the UI Shows
===========================

Pychestrate serves four automation domains, and a team that only runs
one of them should not navigate past the other three. **UI profiles**
let a deployment, and then each user, choose which **surfaces** the
shell presents.

Surfaces
========

A surface is a named slice of the interface that is shown or hidden as
a unit:

``Build Automation``
    Builds, pipelines, and release channels.
``Testing Automation``
    Test runs, the test catalog, and test metrics.
``Robotic Process Automation``
    RPA specifications and jobs.
``Infrastructure``
    Environments, provisioning runs, and blast-radius guards.

Projects, Resources, Fleet, Insights, and Admin are always shown. The
Runs page belongs to every domain that produces runs and stays visible
while any of them is enabled.

Surfaces change what is *presented*, not what is *allowed*. A hidden
page still opens by URL and still enforces its permissions; when you
land on one, a notice explains that the area is hidden from your
navigation and links to your preferences.

The deployment profile
======================

An administrator sets the deployment-wide default at
``/admin/ui-profile`` (permission ``system:ui.profile.manage``). The
selection is stored as the system variable ``ui.profile.surfaces``. At
least one surface must stay enabled. Saving takes effect on the next
page load for everyone and is recorded in the audit log.

The same setting is available as ``GET|PUT /api/v1/admin/ui-profile``.

Personal preferences
====================

Every signed-in user can narrow their own view at
``/account/preferences`` (the **Preferences** link in the header). Only
surfaces the deployment allows are offered. Your selection is the
intersection with the deployment default; if an administrator later
removes every surface you chose, your view falls back to the deployment
default and the page tells you so. **Use deployment default** removes
your selection.

The preference is also available as
``GET|PUT|DELETE /api/v1/me/preferences/ui.surfaces``.

What follows the profile
========================

* The sidebar and the palette: both are built from the navigation
  manifest, which the service filters by your effective surfaces.
* The home view's link grid, built from the same manifest.
* The project sub-navigation tabs (Builds, Runs, Pipelines, Test catalog,
  RPA).
  The tab for the page you are on always stays visible.
* The hidden-surface notice on pages that belong to a hidden surface.
