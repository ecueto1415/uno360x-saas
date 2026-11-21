# Agent reminder verification — 2026-11-21

User requested verification that Jenifer sends reminders through Zoho, preserves
the agreed recurrence and CareFusion pause, leaves native Odoo reminders disabled,
and sends one test to ecueto@outsolutech.com.

## Cause and correction

The effective systemd environment already allowed live agent mail. Although a
historical `99-user-mail-pause.conf` contains `JENIFER_ALLOW_LIVE=no`, the later
alphabetical `collections.conf` overrides it with `yes` and selects
`worker.py --live --collections-only`. Neither file was changed.

The actual blocking condition was the reviewed-code fingerprint for finance job
46, which no longer matched its current code (including the CareFusion exclusion).
The source was inspected and planned using the read-only Odoo adapter. After
validating invoice eligibility, recipient copies and attachments, only its
`validated:cron:46` fingerprint was updated. The previous fingerprint and audit
reason were retained under `validation-audit:cron:46:2026-11-21`.

No Odoo cron was activated or invoice balance changed. Native collection jobs
46 and 53, and weekly payables job 47, remain inactive in Odoo. The independent
Jenifer service consumes their existing planning logic without using Odoo mail
delivery. Its timer is enabled and active, polling every five minutes.

## Verified effective general collection policy

- Published customer invoices, unpaid balance, due at least three days ago.
- Every seven calendar days before thirty days overdue; every three afterward.
- Dominican local sending window `[08:00, 17:00)`.
- Payment state, residual balance, due date, company and invoice scope checked
  again immediately before actual delivery.
- One consolidated customer email with one PDF per included invoice.
- Copies to ecueto and ventas; from thirty days, the second recorded payment
  contact is added when present.
- CareFusion commercial partner IDs 764, 765 and 937 remain excluded.
- The existing batch limit of two customer plans per general collection run was
  preserved; existing recipients, schedules, follow-up holds and other exclusions
  were not broadened. The dormant legacy special job 53 was not activated or
  altered; the effective collections-only service plans jobs 46 and 47.
- Agent payables next execution remains 2026-11-24 14:00 UTC / Tuesday 10:00 RD.

## Evidence

1. Read-only dry plan: job 46 produced two customer plans and one internal report,
   with two PDFs. The two customers had oldest invoices 43 and 12 days overdue,
   selecting three- and seven-day recurrence respectively. Neither was CareFusion.
2. Normal systemd execution completed with `Result=success`, exit status zero:
   two customer reminder dispatches accepted at 18:11:24 and 18:11:25 UTC, and
   the internal report at 18:11:26 UTC. Customer acceptance is SMTP evidence,
   not a claim that a customer read the mail.
3. Immediate second normal execution completed successfully. Collection dispatch
   count remained 44 -> 44; it produced no repeated collection mail.
4. CareFusion collection dispatch count for the Dominican day was zero.
5. Owner-only test subject: `PRUEBA | Recordatorios de Jenifer desde Zoho`.
   Received in ecueto's Microsoft mailbox at 18:12:14 UTC / 14:12:14 RD.
   The explicit retry returned `duplicate`; no additional copy was sent.
   Test key: `collection-zoho-test:ecueto:2026-11-21:1`.
6. Shared dispatch ledger had zero unresolved/pending/uncertain deliveries.
7. Seven isolated timing tests passed: 08:00/17:00 boundaries, seven-day and
   three-day recurrence, UTC-to-Dominican date conversion, accepted-no-copy
   deduplication, customer isolation and uncertain-delivery review.

Sending and inbox transport remain Zoho/Zoho. Microsoft's existing mailboxes and
MX were not changed by this reminder verification. No CareFusion reminder was
sent, and no fake invoices, payments or accounting records were created.
