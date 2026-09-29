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

All of it lives under **Fleet** in the sidebar, or on the **Resources** pages
that open from it. Creating and changing devices, pools and IP pools needs the
resource-management permission that the built-in **system-admin** role holds.


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
while the device is *Online* or *Degraded* and has capacity left; at capacity
the page says so and the form comes back when someone checks in. A device that
is *Offline* or in *Maintenance* cannot be checked out.

To give a device back, open it, find your entry under **Active Allocations**
and choose **Check in**. You cannot check in someone else's allocation that
way. An administrator can: choose **Force check in**, enter the reason
(required, so it is on record), and confirm. The allocation is then marked
*Forced*. **Resources**, **Active Allocations** lists everything now checked
out and **Allocation History** what has been returned.


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

The health dashboard (**Resources**, **Health Status**) counts devices in each
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
