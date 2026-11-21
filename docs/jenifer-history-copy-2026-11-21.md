# Jenifer Microsoft history copy to Zoho — 2026-11-21

Status: completed. All 724 source email records were independently verified in
Zoho with zero new appends during the final verification pass and zero unresolved
records. The Microsoft originals remain intact.

## Scope and safeguards

- Authorized source and destination: only j.encarnacion@outsolutech.com.
- Microsoft source uses the existing delegated IMAP OAuth connection. Every
  source folder is selected read-only and bodies are fetched with BODY.PEEK[].
  No source MOVE, DELETE, STORE, EXPUNGE, forwarding or license operation occurs.
- Destination is the same user's Zoho IMAP mailbox with certificate-validated TLS.
  Credentials are read in RAM from existing restricted Odoo records, never copied
  into scripts, logs, repository files or migration metadata.
- No UI or computer-control tools are used for this server migration continuation.
  All execution is through the existing SSH connection.
- No SMTP sending occurs in migration code. Historical messages stay outside Zoho
  Inbox under `Historial Microsoft Jenifer`, so the live agent does not reply to them.
- ecueto and all other Microsoft mailboxes, DNS, MX and authentication remain intact.
- Original Microsoft mail remains as a backup. This is a copy, not mailbox deletion.

## Storage and format

The initial Microsoft inventory advertised roughly 81 MB, including 52 calendar
holiday objects. Calendar, contacts, notes and tasks remain in Microsoft because
they are not email; no conversion into Zoho calendar/contact objects is attempted.
Mail folders include Inbox, Sent, junk, drafts, deleted, archive and conversations.

Visible archive folders include `Recibidos`, `Enviados MS`, `No deseado`,
`Borradores`, `Eliminados MS`, `Archivo`, `Salida` and `Chats MS`. Seven empty
non-mail containers created during preflight were removed only after checking
they contained no mail. These archive folders are not new live inboxes.

Some original Exchange MIME messages were accepted by Zoho but not readable back
in their initial form. The portable representation preserves visible sender,
recipients, subject, date, text/HTML and file attachments, and includes the complete
downloaded original bytes as `Original Microsoft.eml`. Its SHA-256 is checked on
read-back. Original Message-ID and reply references are preserved in the embedded
original; later portable copies use a deterministic technical archive Message-ID
to keep malformed/colliding historic IDs out of the destination parser.

The first few normalized messages passed semantic header/body/attachment comparison
before the portable EML representation was introduced. Their Microsoft originals
also remain intact. No original was deleted or overwritten.

Exchange RFC822.SIZE is sometimes a pre-conversion size estimate. The migration
checks the exact IMAP literal byte count and then reads each destination message
back; it does not falsely treat an estimate mismatch as lost bytes.

## Deduplication, restart and concurrency

Identity combines original Message-ID with canonical headers, decoded text and
attachment hashes. Transit headers and MIME boundary changes do not create extra
copies. Messages with genuinely different content are not silently merged.

Three bounded destination sessions use per-identity locks and a durable SQLite
ledger. A message already indexed in Zoho is reused. Recent incoming forwarded
messages are also checked against live folders. Accepted-but-unconfirmed appends
are never blindly resent. Definite server rejections are logged and retried within
a small bound, with reconciliation before retry.

Under concurrent APPEND, a returned Zoho UID was observed to differ from the actual
stored UID. Read-back therefore reconciles by deterministic archive Message-ID and
full original identity, rather than sending again because a receipt UID is absent.

Unusable intermediate imports were moved to recoverable Zoho Trash only after a
readable equivalent was verified. One extra diagnostic copy was likewise moved
to Trash after its identical retained copy was verified. There is no permanent
purge. The migration ledger records exclusions for unreadable intermediate items.

Ledger: `/var/lib/jenifer-directa/microsoft-zoho-history.sqlite`, restricted to the
server administrator. It stores folder/UID identities, hashes and status, not mail
bodies or credentials. Its source_metadata table also retains all 724 original
internal dates, flags and date headers. Duplicate source records can have different
internal storage times even when their message and date header are identical;
those metadata variants are retained without creating duplicate emails in Zoho.
The common agent dispatch ledger is not reset or restored.

## Running and verification

The two migration source files must be adjacent. On the authorized server:

```
sudo /opt/odoo18/venv/bin/python3.12 migrate_mail_history_parallel.py --apply
sudo /opt/odoo18/venv/bin/python3.12 migrate_mail_history_parallel.py --verify-only
```

The second command must find every source email already covered and append zero
messages. It reads source and destination again and detects exact archive duplicates.
It does not activate Odoo jobs or send mail. An unknown or changed folder requires
review rather than silently omitting content.

Fifteen isolated tests passed for exact original EML preservation, attachment
differences, Unicode folders, literal truncation, parallel deduplication, uncertain
outcomes, stale UID receipts and verification-only write prevention.

## Final evidence

- Source records: Inbox 188, Sent 535, junk 1; total **724**.
- Distinct source identities: **547**. The remaining **177** source records are
  repetitions under the reviewed original-ID/header/body/attachment identity.
- Destination archive: Recibidos **186**, Enviados MS **358**, No deseado **1**;
  total **545**. Two other unique source messages were already in live Zoho folders.
- Direct IMAP archive message count **545** equals the ledger's **545** distinct
  source identities mapped to the archive. This independent count also excludes
  extra physical copies in the archive, including copies that already exist live.
- Fresh full --verify-only pass: source **724**, existing **724**, copied **0**,
  unresolved **0**, archive duplicate index count **0**. The source comparison
  portion completed in 40 seconds after full destination indexing.
- Fetched source literal bytes, including repeated source messages: **54,548,924**.
  This is not the cached RFC822.SIZE estimate or a claim about Zoho quota usage.
- Read-back includes original EML SHA-256 verification and semantic headers,
  decoded text and attachment hashes. Sample old Inbox and Sent messages retained
  their original internal date and flags. A repeated Sent record had a different
  source internal storage time; the original date header is unchanged and both
  source internal metadata records remain in the ledger.
- Final provider settings: **Zoho sending / Zoho inbox**. Agent timer active;
  last agent service result success, exit status 0. Native Odoo reminder jobs
  46/47/53 remain disabled. CareFusion's hold was not changed.
- Authoritative Microsoft MX remains
  `10 outsolutech-com.mail.protection.outlook.com`. No other mailbox was migrated,
  edited, deleted or de-licensed. Calendar/contact/note/task data remain in Microsoft.
- No desktop, browser, mouse or keyboard control was used in the continuation.
- Source and final verification code plus tests are retained in the repository;
  server-only report and restricted ledger are retained for reconciliation.
