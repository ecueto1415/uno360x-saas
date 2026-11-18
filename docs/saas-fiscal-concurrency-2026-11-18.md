# SaaS fiscal concurrency

The common fiscal addon and the INCIVI fiscal override use an independent PostgreSQL sequence for each authorized range. Existing next numbers are migrated from the previous cursor column. Number reservation runs after accounting and payload validations. The invoice lock and the unique constraints on invoice and issuer/e-NCF remain active.

PostgreSQL sequences are not transactional. If a transaction fails after reservation, its number remains consumed and will not be assigned to another invoice. This can leave an unused number. Exhausted ranges stop allocation. Used ranges remain protected against modification or deletion.

The issuer worker allows five concurrent documents. Each task owns its authenticated client. The durable uncertain state is written before submission, and acceptance is consulted immediately after the tracking number is saved. Pending results retain the eight-second polling interval. A submission with unknown outcome is reconciled instead of automatically resubmitted.

Both active SaaS databases were migrated on 2026-11-18. INCIVI retained its six ranges and next E31/E34 numbers of 4. Native OUTSOLUTECH was excluded. Production validation used existing documents and read-only number checks, without reserving an e-NCF or submitting a new fiscal document.

## Laboratory validation

Three and five concurrent confirmations used real Odoo transactions, PostgreSQL allocation, dummy-certificate XML signing, and simulated DGII responses. Every confirmation was repeated to verify reuse of the existing document. All eight invoices received distinct numbers, and no extra submission occurred.

Three boxes saved confirmation in 0.149 to 0.207 seconds and reached simulated acceptance in 1.952 to 2.167 seconds. Five boxes saved confirmation in 0.257 to 0.409 seconds and reached simulated acceptance in 2.085 to 2.346 seconds. All completed on their first transaction attempt.

In the five-box run, Odoo and the fiscal process peaked at 139.52 MiB and 2.11 CPU cores. PostgreSQL peaked at 225.42 MiB and 0.75 CPU cores. Resource samples were taken every 200 ms on a 12-logical-CPU laboratory host. These measurements do not establish live DGII latency or production capacity.

Additional checks covered exhaustion, editing an unused range, protection of used ranges, preservation of migrated numbers, no reuse after rollback, parallel dispatch, duplicate command replay, and unknown submission outcomes. Detailed measurements are in validation/fiscal-concurrency-20261118.json.

## Deployment and rollback

Pause SaaS preparation and fiscal triggers, back up each SaaS database and its current ranges, and stop its application container before changing the addon. Update uno360x_ecf_core so init creates the PostgreSQL sequences. Confirm that every next number equals the previous cursor or first authorized number. Refresh installation fingerprints before restarting applications and fiscal triggers. Rebuild pristine templates and ready reserves for new accounts.

Before reverting to the previous cursor implementation, stop fiscal operations and carry each current sequence's next number into the previous cursor. A source-only rollback could otherwise reuse numbers. Keep both database backups and the range snapshot.
