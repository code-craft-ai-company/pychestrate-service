.. _15-00-lab-administration:

***************************************************
Managing the Lab: Devices, Pools, IPs, Reservations
***************************************************

This guide is for the person who looks after the lab: the devices, the pools
they sit in, the IP addresses, and who may use what and when. It follows the
tasks in the order you meet them. If you have not yet signed in and created a
project, start with `Getting Started <02-00-getting-started.rst>`_; the
concepts (a resource, a pool, a check-out, a reservation) are in the
`Overview <01-00-overview.rst>`_.

All of it lives under **Fleet** in the sidebar: **Older Resources** opens the
list of devices this chapter describes, and **IP Pools**, **Reservations** and
**Resource Health** open the other pages that go with it. (There is a newer set
of resource records under **Resources and Pools**; the next section says how the
two differ.) Creating and changing devices, pools and IP pools needs the
resource-management permission that the built-in **system-admin** role holds.


Project resources and their pools (preview)
===========================================

Fleet also has **Resources and Pools**. Its page is scoped to a project: choose
the project at the top and the page lists that project's **Resources** and,
below them, its **Pools**. These are a newer set of records than the Resources
pages described in the rest of this chapter, and the two are not connected yet:
a device registered on one does not appear on the other. Jobs do not use
either yet; the plan is to move to this newer set (see ``specs/model-convergence.md``
in the source tree).

To register a device, open **Register a device** above the pools and fill in a
**Name** and a **Hostname** (the hostname, with the MAC address if you give
one, is what tells one device from another; registering the same pair twice
is refused). The **MAC address**, **IPv4 address**, **Vendor**, **Model**,
**Location** and **Notes** are optional, and **Tags** takes a comma-separated
list. The device starts as *available*. The form shows for people who hold the
resource-write permission (``system:resources.write``).

To put a device in a pool, open the pool and choose the device from the
**Add resource** list. It offers the project's devices that are not in the pool
and not retired.


Resource pools
==============

A **resource pool** groups devices, for example a rack or a test bench. Open
**Resources**, **Resource Pools**, choose **Create Pool**, give it a **Pool
Name** (letters, digits, underscores and hyphens) and a description, and save.
A device belongs to one pool. A deployment can flag one pool as its default;
a device created without a pool goes there, and the form says which.


Devices
=======

A **device** is a resource of type *Device*. The other types (IP address,
port, credential, generic) work the same way; only what they stand for
differs. Open **Resources**, **Resources**, choose **Create Resource**, and
fill in:

* **Resource Name**: letters, digits, underscores, hyphens and periods.
* **Resource Type** and **Resource Pool**.
* **Capacity**: how many check-outs may be active at once. Use 1 for a device
  only one person or job can hold, and more for something shareable.
* **Tags**: labels to find and filter by.
* **Metadata**: a JSON object for anything else worth recording, such as a
  serial number or a rack position.

A new device starts **Online**. A name that already exists, or metadata that
is not a JSON object, is refused with the error next to the field.

To register many devices, choose **Import** on the **Resources** list (or the
link on the create page). Paste CSV, or cells copied from a spreadsheet: the first
row names the columns and each row after it is a device.

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Column
     - What goes in it
   * - ``name``
     - Required. Letters, digits, underscores, hyphens and periods.
   * - ``type``
     - Optional. ``device`` (the default), ``ip_address``, ``port``,
       ``credential`` or ``generic``.
   * - ``pool``
     - Optional. The name of an existing pool; blank uses the default pool.
   * - ``capacity``
     - Optional. A whole number of at least 1; the default is 1.
   * - ``description``, ``tags``
     - Optional. Tags are separated by spaces, commas or semicolons, and new
       tags are created.
   * - ``metadata``, ``meta.<key>``
     - Optional. ``metadata`` is a JSON object; a column such as
       ``meta.serial`` sets one metadata key without any JSON.

Choose **Preview**. Every row is read and checked against the lab (the pool
must exist, and the pool must not already hold a resource of that name), and
the page shows what would be made and what is wrong with each row. Nothing is
created yet. A column the page does not recognise refuses the whole file, so a
misspelt header cannot silently drop a column of data. When every row is
ready, choose **Import**: all of the devices are created, or, if anything has
changed or is wrong, none. One import takes at most 500 devices.


Check out and check in
======================

Opening a device shows who holds it and, when it can be taken, a **Checkout
Resource** form:

* **Job ID**, optional: the job the device is for.
* **Allocation Mode**: *Exclusive* keeps others off it; *Shared* lets others
  hold it too, up to its capacity.
* **Timeout (minutes)**, optional: the check-out ends by itself after this
  long. Leave it empty for no timeout.
* **Reason**, optional: what you are using it for.

Choose **Checkout**. You are told the allocation ID. The form appears only
while the device is *Online* or *Degraded* and has capacity left. The card
always says what is true instead: that you already have it checked out (with a
link to your allocation), who has it and until when, or, for a device that is
*Offline* or in *Maintenance*, that checkout is blocked, since when, why and
who set it. The form comes back when someone checks in or the device is
brought back online.

To give a device back, open it, find your entry under **Active Allocations**
and choose **Check in**. You cannot check in someone else's allocation that
way. An administrator can: choose **Force check in**, enter the reason
(required, so it is on record), and confirm. The allocation is then marked
*Forced*, and its page names who forced it and gives their reason.
**Resources**, **Active Allocations** lists everything now checked out and
**Allocation History** what has been returned; both show the reason given at
checkout under the holder's name, and the lists say how many rows there are and
keep their filters from page to page. **Resources**, **Resource list**,
**Allocation History** and **Reservations** each have a **Download CSV** button that
saves every row the current filters match (not just the page you are on), up to 5,000,
as a spreadsheet: for the devices their type, pool, health, how many are in use, tags and
description; for allocations and reservations who held or booked what, when, in which
mode and why. A device's metadata (addresses, credentials) is never in the file, and a
name that a spreadsheet could read as a formula is written as text. If more rows match
than the limit, the file holds the first 5,000 and the response says it was cut.

To see which devices are busy and which sit idle, open **Resources**,
**Utilization**. Choose the last 7, 30, 90 or 365 days (30 by default). The page
gives the number of allocations, how many devices were used, the time in use in
total, the average allocation and the most held at once, then one row per device,
busiest first: its allocations, hours in use, its share of the period (a bar and a
percentage), when it was last checked out and a mark if it is in use now. A device
nobody checked out has a row of zeros, so idle equipment is easy to spot.

*Time in use* is measured, not counted. An allocation that began before the
period counts only for the part inside it, one still held counts up to now, an
allocation with no check-in time that has ended counts until its lease was meant
to end, and allocations of one device that overlap (a shared device) count once, so a
device shared by three people at the same hour is in use for one hour.
**Download CSV** saves the same table for the period you chose, one row per
device, ready for a spreadsheet; a name that a spreadsheet could read as a formula
is written as text. The page reads up to 1,000 devices and the latest 50,000
allocations in the period and says so when it hits either limit.


Reserve a device for later
==========================

A **reservation** books a device for a window in the future. Open
**Resources**, **Reservations**, choose to create one, and pick the **Resource**,
a **Start Time** and an **End Time**, the **Allocation Mode**, and optionally
a job ID and a reason. Narrow the resource list by pool or type first if it is
long.

* You type the times in **your browser's time zone**, and the form says which
  zone that is.
* A reservation that overlaps another exclusive one on the same device is
  refused, and the message names the reservation it clashes with. The message
  gives its times in UTC.
* A reservation that starts exactly when another ends is accepted.
* You can change a reservation's times from its page, or cancel it.

The reservation list shows **Pending and active** reservations by default, so
cancelled and completed ones do not pile up. Choose another **status**
(Pending, Active, Completed, Cancelled or All) to see them, and narrow the list
by resource and by a start and end time. The times you type in the filter are
in your browser's time zone, like the form's. Reservation times on the list,
on a reservation's page and on a device's page are shown in that zone too, with
the zone abbreviation, for example ``2026-09-30 09:00 PDT``, and the UTC time as
the tooltip. Without JavaScript, or in a UTC browser, they are shown in UTC.
The message for a clashing reservation still gives its times in UTC.


See when devices are free
=========================

**Resources**, **Availability** draws one week, Monday to Monday, as a row per
device. Reservations are blocks (red for exclusive, blue for shared) and current
check-outs are yellow blocks that run to the check-out's timeout, or to the end of
the week when it has none. A device with nothing drawn is free. The red line is
now, and today's column is highlighted. Hover over a block for who has it and
when.

* Choose a **pool** to show only its devices. Without one, the first 40 devices
  are shown and the page says how many there are.
* **Previous week**, **This week** and **Next week** move through time and keep
  the pool.
* The week is laid out in your browser's time zone. The first visit reloads once
  to pick it up, and it is remembered in a cookie named ``pyc_tz``. Add
  ``tz=Europe/Berlin`` (any IANA zone) to the address to see another zone.
* The **Bookings this week** table under the drawing lists the same bookings as
  text, with links to the reservations.


IP pools
========

An **IP pool** is a range of addresses that people and jobs check out from.
Open **Fleet**, **IP Pools**, choose to create one, and give:

* **Pool Name** and **CIDR Range**, for example ``10.90.0.0/29``. IPv4 and
  IPv6 are both accepted, and a range that overlaps an existing pool is
  refused, naming the pool it overlaps.
* **Gateway** and **DNS Servers**, optional. They are always kept back from
  check-out.
* **Reserved IPs**: any other addresses to exclude, comma separated.

The pool's page shows how many addresses are usable, reserved, allocated and
available. The network and broadcast addresses are not usable, so a ``/29``
has 6 usable addresses, and with a gateway and a DNS server inside it 4 are
available.

To check out addresses, use the **Checkout** form on the pool's page. Ask for
a **count** and the pool hands out that many free addresses, or ask for one
**specific IP**. You are told how many were checked out. Asking for the
gateway, or any other reserved address, is refused and says why. The other
fields are the same as for a device. A pool with nothing left says it is at
capacity.

Addresses are returned on the pool's own page. Choose **Checkin** next to an
address, or, to return everything a job holds, enter its job ID under **Bulk
Checkin by Job** and choose **Checkin All Job IPs**.


Health checks
=============

A device's health is one of four states, and it decides whether the device can
be checked out:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - State
     - Meaning
   * - Online
     - Working. Can be checked out.
   * - Degraded
     - Working with a problem. Can still be checked out.
   * - Maintenance
     - Taken out of service on purpose. Cannot be checked out.
   * - Offline
     - Not reachable. Cannot be checked out.

Set the state by hand on the device's health page (**Resources**, **Health
Status**, then the device): choose the state, enter a **reason**, and choose
**Update Status**. The reason is required and is recorded in the audit trail.

To have the service watch a device, choose **Configure Health Check** and set:

* **Enable Health Checks**.
* **Probe URL**: the device's HTTP or HTTPS health address. A 2xx answer
  counts as healthy. The Pychestrate server calls it directly, so loopback and
  link-local addresses are refused, with the error next to the field.
* **Check Interval** (seconds), **Timeout** (1 to 30 seconds), and the
  **Failure Threshold** and **Success Threshold**: how many misses in a row
  mark the device unhealthy, and how many hits mark it healthy again. The
  defaults are 60, 10, 3 and 1.

**Run Health Check** asks the service to probe the device now instead of waiting
for the interval. The check is queued and runs in the background within a few
seconds, so the button returns at once even when the device is slow. Refresh the
device's health page to see when it was checked and whether it passed; when it
failed, the page says why (the status the device answered with, no answer in
time, or not reachable). A check that is switched off, or has no probe URL, is
refused with a message saying what to configure. If a queued check is still
waiting after two minutes, the page says the housekeeping worker is not picking
it up.

The health dashboard (**Resources**, **Resource Health**) counts devices in each
state and lists the first twenty of each. **View all** opens one state, a page
at a time.


Removing things
===============

Deleting a device deletes its allocation, reservation and health history with
it, and cancels its upcoming reservations; the confirmation says so. A device
that is checked out cannot be deleted until it is checked in, and the
confirmation warns you when that is the case; use **Force check in** if the
holder cannot. A pool that still holds devices cannot be deleted: move or
delete them first.

Deleting a device, a resource pool or an IP pool is permanent, so the
confirmation asks you to **type its name** before the Delete button turns on
(the same goes for deleting a role, a project and a secret, and for retiring an
RPA job type, each with its own name). Cancel, or Escape, submits nothing.
Smaller or reversible actions, such as removing a member, revoking a token,
cancelling a reservation or deleting a tag, ask a plain yes or no.
