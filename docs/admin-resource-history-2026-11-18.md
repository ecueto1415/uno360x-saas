# Weekly resource history in the owner console

Clicking the CPU, RAM or disk gauge in Resources opens a seven-day chart in the existing admin style. It includes hourly averages, a min/max band, recorded peak, latest sample, pointer/keyboard/touch selection and a values table. Missing periods remain blank. The dialog survives the normal dashboard refresh and preserves an older selected hour during chart resizing/refresh. Its close control remains visible while scrolling.

The existing one-minute snapshot exporter appends real server telemetry to `/var/lib/uno360x-admin-export/resource-history.sqlite3`. Records are deduplicated by timestamp, retained for eight days, and the API returns only the latest seven days in at most 169 hourly buckets. This database contains no client identity, documents, credentials or fiscal information. It is root-owned and group-readable by the admin service (0640). The HTTP application opens it read-only; sampling failure does not suppress the normal dashboard snapshot.

Historical CPU and available-RAM measurements were imported once from the system sysstat files: 1,008 samples covering the previous week. The CPU formula matches the existing gauge, excluding idle, I/O wait and steal. RAM uses measured MemAvailable after checking the historical capacity against the current capacity. Unsupported/mismatched samples are omitted. Disk usage was not present in those archives and is not invented: its recorded history starts on 18 November 2026 around 21:08 America/Santo_Domingo. The chart explicitly states the available start time. New measurements continue approximately every minute.

GET `/api/resources/history?metric=cpu|memory|disk` requires the existing authenticated owner session and dedicated administrative origin. Invalid/duplicate parameters are rejected. No POST history action exists. Assets use the existing self-only CSP; charts use local SVG and no external library. Existing authentication, MFA, customer controls and SaaS/Odoo services are preserved.

## Publication and reversal

The admin-only release is `/opt/uno360x-admin/releases/resources-week-20261118`, selected by `/opt/uno360x-admin/current`. The existing exporter at `/usr/local/lib/uno360x-admin/export.py` imports the same history module installed as `/usr/local/lib/uno360x-admin/resource_history.py`. The existing exporter timer supplies the cadence; no new timer or provisioning change is required. Source mirrors live code in `admin_console/` and `deployment/admin_export.py`.

Before publication, the old release target and exporter were saved under `/var/backups/uno360x-admin-resource-history-20261118`. Reversal restores that exporter and the previous admin symlink and restarts only the admin service. The small telemetry database can remain for later use. No customer database or native OUTSOLUTECH is modified.

## Validation

Five Python tests verify aggregation, duplicate samples, bounds/retention, truthful missing history, sysstat import, existing live-sample priority, dedicated-origin/owner authentication and invalid query rejection. The 21 existing admin authentication, MFA, quota and CSP tests passed. Five DOM tests verify clicks, keyboard/range use, missing-time gaps, racing metric requests, focus restoration, modal persistence and selected-hour preservation. Run Python tests with the project on PYTHONPATH; run `node --test tests/resource-history.test.cjs` with jsdom 26.1.0 on NODE_PATH (development only).

Chrome showed real RAM and CPU weekly graphs and the disk point at the right edge of the otherwise empty week. Live unauthenticated history requests returned 401, static assets and health returned 200, the exporter completed successfully, and successive automatic samples were observed. The active owner login remained valid through publication.
