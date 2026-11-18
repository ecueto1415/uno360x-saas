# INCIVI billing navigation measurements

Menu external IDs are fetched in one batch. Invoice list field metadata is also fetched in one request, preserving the same permission filtering. Before/after comparisons returned identical navigation, allowed menu IDs, columns and rows. Warm SQL calls fell from 194 to 32. Fresh-process list preparation fell from 1.1773 to 0.9337 seconds.

The existing areas.js prepares the invoice form after the billing page loads, using the current authenticated user's language, time zone, company and permissions. Preparation calls only get_views and reads an invoice page to discover same-origin asset links. It prefetches up to four hashed asset files. It does not create records, reserve fiscal numbers or emit documents. It runs once per page, respects data-saving mode and aborts pending preparation after 12 seconds.

Chrome Network measurements used an existing INCIVI session and invoice E310000000003. With browser cache disabled, the list load event was 1.55 seconds before and 1.61 seconds after; there was no measurable improvement in total list loading in this run. The invoice load event fell from 11.73 seconds to 2.97 seconds when opened after preparation from the list. Total initial network activity fell from 16.94 to 7.55 seconds. These are individual samples, not a latency guarantee.

The first billing page after restarting the application still took 3.11 seconds, with background view and document preparation taking 8.32 and 7.20 seconds respectively. Preparation moves this cost earlier while the user sees the list. Opening an invoice immediately can still encounter part of that wait. A separate list measurement with normal browser cache enabled recorded 1.49 seconds.

The browser's cache setting was restored after measurement. Existing fiscal documents remained at six, with no fiscal submission or e-NCF reservation during validation. Native OUTSOLUTECH was excluded. The publication updates active SaaS runtimes and the eight pristine template profiles.
