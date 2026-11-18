# Faster billing list delivery

The billing list previously required four stylesheets and two JavaScript files. It now delivers the same sources, in the same order, as one CSS and one deferred JavaScript response. Other areas retain their existing files. No tenant data, menu permission result, invoice query result or fiscal operation is cached in these bundles.

The asset URL contains its SHA-256 content hash. Responses support ETag/304 and a year-long immutable browser cache. File modification time and size invalidate the in-process content cache, so later CSS/image work does not require generated bundle rebuilds. Invalid kinds return 404; an old hash redirects to the current URL. Only fixed module source paths are readable. The normal session gateway remains in place.

## Chrome measurements

In the existing INCIVI Chrome session, with browser cache disabled and no network throttling, the Network Load event measured 1.62, 1.44 and 1.32 seconds before, and 0.870, 0.894 and 0.814 seconds after. The median fell from 1.44 to 0.870 seconds, a 39.6% reduction. Three samples do not establish a latency guarantee. The first page after restarting the app took 1.89 seconds, of which the document took 1.35 seconds; server cold-start work still exists. Background invoice prefetch remains separate from the list's Load event. Normal browser caching was restored after measurement.

## Validation and publication

Read-only maintenance probes returned the same list/menu/permission hash before and after. Both SaaS backends served the exact concatenated bytes, returned 304 to an ETag request, rejected unknown asset types, and redirected old versions. INCIVI retained six fiscal documents and the same next numbers (E31: 4, E34: 4). No e-NCF was reserved and no document was issued. Native OUTSOLUTECH was excluded.

Publication selectively replaces the common shell QWeb view, synchronizes active profiles and restarts only the two SaaS app containers. It rebuilds the eight pristine SaaS profiles and replenishes the development reserve. The Git patch intentionally excludes unrelated pre-existing live baseline customizations; those were preserved on the server. A pre-change source backup is retained server-side for reversal.
