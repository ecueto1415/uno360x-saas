# Internal PostgreSQL seed retention

The shared SaaS PostgreSQL held 509 internal `uno_tpl_` databases on 2026-11-18. These were versioned factory seeds, not customer databases. Their combined logical size was approximately 31 GiB. Current plans require eight profiles; past seed versions had accumulated without a retention job.

`deployment/prune_seed_templates.py` defaults to a read-only plan. `--apply` operates exclusively on the verified, private, managed rootless SaaS PostgreSQL server. Native OUTSOLUTECH is outside its resources. Customer database names (`tenant_...`), system databases, open databases, databases with sessions and shared seed-role dependencies are ineligible.

The policy preserves current profiles, two independently verified prior archives per module combination, all nonretired reserve references, every preparation snapshot and seeds younger than one hour. The initial plan and every deletion receipt are retained privately under `/var/lib/uno360x-saas/shared-postgres/seed-maintenance`. Compressed database/filestore archives remain intact; only redundant live factory database copies and their exclusively owned seed roles are retired.

Before each deletion, the matching archive checksum and safe tar structure are verified. A short builder lock prevents racing reserve creation. The original database OID, owner, closed state and absence of sessions are checked again. The seed is briefly opened only to local administrative inspection. A read-only transaction verifies the factory UUID, neutral company identity, no customer credentials, no active automation and no fiscal, sales, purchasing, inventory or payroll business records. The database is closed before normal `DROP DATABASE` and `DROP ROLE`; FORCE and session termination are never used. A failed pristine check recloses the seed and stops the run for investigation.

Queued or running customer provisioning has priority: cleanup defers. Protection is refreshed during the run. File archives, client storage, quota settings, logs and unrelated backups are not deleted.

The daily rootless systemd job runs around 03:30–03:40 America/Santo_Domingo (07:30 UTC plus up to ten minutes), with low CPU and I/O priority. It uses the same safety checks and private maintenance lock. To disable future runs, stop and disable only `uno360x-seed-maintenance.timer`. Database copies can be recreated from retained verified archives through the existing reserve seed builder.

Validation includes selection safety tests, text PostgreSQL OID handling, refusing all mutations without a recovery archive, a one-database production-SaaS canary, complete deletion receipts, comparison of nonseed database OIDs and business/fiscal counters, current template verification and active backend health. No fiscal document is issued or e-NCF reserved during validation.
