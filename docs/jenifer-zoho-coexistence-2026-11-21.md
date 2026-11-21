# Jenifer: Zoho and Microsoft coexistence — 2026-11-21

## Applied configuration

- Domain MX remains `10 outsolutech-com.mail.protection.outlook.com` in Wix.
- Microsoft accepted domain `outsolutech.com` is Internal Relay. Existing Microsoft
  mailboxes remain provisioned, including ecueto, ventas, rlebron and ocampusano.
- Enabled outbound connector `OUTSOLUTECH - Zoho Mail coexistencia`, restricted to
  `outsolutech.com`, smart host `mx.zoho.com`, TLS with CA certificate validation.
- Zoho Split Delivery sends unknown Zoho recipients to the Microsoft protection
  host. No changes to the website A records or www CNAME.
- SPF is a single record authorizing both providers:
  `v=spf1 include:spf.protection.outlook.com include:zohomail.com -all`.
- Zoho DKIM selector `zohomail202611` is verified and enabled.
- Added Jenifer's non-primary routing alias `j.encarnacion.zoho@outsolutech.com`.
  Microsoft forwards her incoming mail to that alias **and retains a mailbox copy**.
  Her public address remains `j.encarnacion@outsolutech.com`.
- No Microsoft mailbox, license or historical message was deleted. Historical
  mail has not been copied to Zoho in this change; it remains in Microsoft.

## Jenifer transport

Native database: `Outsolutech_prueba` (daily OUTSOLUTECH installation despite its
historical name). No SaaS tenant, invoice or fiscal configuration was changed.

- `ir.mail_server(4)`, `Jenifer - Zoho Mail`, active, priority 1, sender filter only
  Jenifer, `smtppro.zoho.com:587`, STARTTLS with certificate validation.
- The user entered the password directly in Odoo. No password was committed or
  added to a file. The transport reads this restricted record into RAM.
- Previous Microsoft outgoing server 2 is archived, with its configuration retained.
- `jenifer_directa.mail_provider=zoho` and `jenifer_directa.zoho_server_id=4`.
- Final configuration: `jenifer_directa.inbox_provider=zoho`. The temporary
  Microsoft inbox fallback was removed after a new authenticated message reached
  Zoho Inbox, was read in full and answered successfully from the same transport.
- Existing scheduled-mail pause, collection schedules and cron activation were
  not changed. The failed/paused service was not globally resumed.
- Native Odoo was reloaded once (service restart completed in 2.05 seconds), so
  its cached private-chat engine reloads the transport. Local login returned 200.

The patch retains one shared dispatch ledger across providers, including iBids
deduplication. Only mailbox UID checkpoints and inbound UID dispatch keys are
namespaced for Zoho. First activation baselines historical Zoho messages without
replying. Uncertain SMTP acceptance is never retried automatically.

Zoho SMTP automatically saves Sent. With a Zoho inbox, no manual APPEND is made.
In temporary hybrid mode, one archival Sent copy is additionally stored in Microsoft;
this is a copy in each provider, not two copies in a single mailbox.

Zoho's first receiver Authentication-Results header is recognized for aligned SPF,
DKIM or DMARC for allowlisted internal users. A later forged header, an unrelated
SPF domain or an X-MS internal marker cannot override a failed Zoho verdict.

## Validation

- Microsoft connector validation delivered successfully to compras, licitaciones,
  ericsson.cueto and vacantes using TLS 1.3 with trusted certificates.
- Ericsson Zoho -> ecueto Microsoft: received and found using the Outlook connector.
- Jenifer Zoho SMTP login and Zoho IMAP read-only login: successful.
- Standalone Jenifer Zoho -> ecueto: accepted and received; retry returned duplicate;
  one Zoho Sent copy verified after indexing completed.
- Effective configured hybrid transport -> ecueto: accepted and received; retry
  returned duplicate; one Microsoft Sent archival copy verified.
- Initial Microsoft -> Jenifer public address -> Zoho routing alias tests were
  classified as spam. After Microsoft DKIM activation, fresh test
  `20261121-dkim1` reached Zoho Inbox with DKIM and aligned SPF passing; it was
  absent from the spam folder. Full body retrieval and internal sender trust passed.
- Reply from the pure Zoho transport was received in ecueto's Microsoft mailbox
  at 17:59:21 UTC / 13:59:21 Santo Domingo. One Zoho Sent copy was verified; retry
  returned duplicate. No uncertain deliveries remain.
- Effective provider settings were read back as Zoho/Zoho. The existing Zoho UID
  checkpoint was advanced only over the identified technical test message (UID 3).
  No customer messages or historical Microsoft checkpoints were replayed.
- Read-only Microsoft IMAP verification confirmed that the original incoming test
  was also retained in Jenifer's Microsoft mailbox. Authoritative DNS still reports
  the Microsoft MX. Odoo remains active.
- Eleven isolated transport tests passed, including hybrid routing, TLS, historical
  baseline, common deduplication, uncertain delivery and forged-header rejection.
- No customer collection, fiscal document or automatic historical reply was sent.

## Completed Microsoft DKIM authentication

Microsoft's custom-domain DKIM had no keys. Keys were created and these CNAMEs
published in Wix, without replacing the Zoho DKIM selector:

| Host | Target |
| --- | --- |
| selector1._domainkey | selector1-outsolutech-com._domainkey.outsolutech965.w-v1.dkim.mail.microsoft |
| selector2._domainkey | selector2-outsolutech-com._domainkey.outsolutech965.w-v1.dkim.mail.microsoft |

After DNS synchronization, Microsoft accepted the enable operation. Defender shows
**Enabled — Signing DKIM signatures for this domain**, last checked
2026-11-21 13:57:21 Santo Domingo. Both CNAME records and their public keys resolve.
Zoho's existing verified DKIM selector remains separate and enabled. No spam or
quarantine protection was disabled and no broad domain allow rule was introduced.

Microsoft forwarding copies, historical messages and the existing license remain
in place. Historical mailbox migration and reactivation of paused automatic mail
jobs are separate from this transport/authentication change.

## Source and rollback

Worker backup: `/opt/jenifer-directa/worker.py.pre-zoho-20261121`.
The tracked patch installer validates its reviewed source anchors and parses the
result before output. It does not activate a provider or change secrets/routing.

For rollback, select provider `microsoft`, reactivate outgoing server 2, archive
server 4, and restore the worker backup with its original ownership/mode under the
worker lock. Reload native Odoo. Keep the common dispatch ledger; never restore an
old state.sqlite over it, since that could resend mail. Forwarding can be disabled
independently while keeping the Microsoft copy. Do not change MX for rollback.

Official references checked 2026-11-21:

- https://www.zoho.com/mail/help/adminconsole/coexistence-with-office365.html
- https://www.zoho.com/mail/help/imap-access.html
- https://www.zoho.com/mail/help/zoho-smtp.html
- https://learn.microsoft.com/en-us/exchange/mail-flow-best-practices/manage-accepted-domains/manage-accepted-domains
- https://learn.microsoft.com/en-us/defender-office-365/email-authentication-dkim-configure
