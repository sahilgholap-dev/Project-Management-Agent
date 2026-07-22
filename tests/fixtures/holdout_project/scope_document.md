# Meridian Field Service — Mobile Work-Order App (Scope)

Meridian Facilities Group dispatches ~60 field technicians who currently
receive work orders by phone and paper. We are building a mobile app plus a
small dispatcher web console to digitize that flow.

## In scope

**Work-order lifecycle.** Dispatchers create work orders in the web console
(site, asset, priority, description, photos). Technicians receive assigned
orders on their phones, update status (accepted / en route / on site /
complete), attach photos and notes, and capture the customer's signature on
completion. Completed orders generate a PDF service report emailed to the
site contact.

**Offline support.** Technicians often work in basements and plant rooms with
no signal. The app must work offline and synchronize when connectivity
returns.

**Scheduling board.** The console shows a day/week board of technicians and
their assigned orders, with drag-and-drop reassignment. No automatic route
optimization in this release — manual assignment only.

**ERP integration.** Completed work orders must be pushed into the client's
ERP system so invoicing can happen there. The integration is one-way (app to
ERP).

**Reporting.** A weekly summary: orders completed per technician, average
time-to-complete per priority class, and SLA breaches.

**Authentication.** Technicians sign in with company accounts. Dispatcher
console access is role-based (dispatcher, supervisor, read-only).

## Out of scope

Customer-facing portal, parts inventory, payroll, route optimization, iPad
layouts (phone-first).

## Constraints

- Pilot with the Northeast region team (12 technicians) first; the rollout to
  all 60 waits for pilot sign-off.
- The client's IT department must approve the authentication approach before
  any production data is touched.
- Target platforms: Android first (the fleet standard), iOS "if feasible
  within the timeline".

## Notes from the sales handover

The client "expects the ERP push to just work like the last vendor's did" —
no API documentation has been provided yet, and the ERP product/version was
not recorded in the CRM. Offline conflict handling (two technicians editing
the same order, or a dispatcher reassigning an order while a technician has
it open offline) was discussed in the sales cycle but never resolved.
