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
- **Temporary:** `jenifer_directa.inbox_provider=microsoft`. The transport continues
  to read Microsoft's retained copy through existing OAuth. Zoho IMAP works, but
  the Microsoft-origin test messages were classified as spam by Zoho.
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
- Microsoft -> Jenifer public address -> Zoho routing alias: test found in Zoho
  spam; aligned SPF was correctly recognized after the authentication parser change.
- Eleven isolated transport tests passed, including hybrid routing, TLS, historical
  baseline, common deduplication, uncertain delivery and forged-header rejection.
- No customer collection, fiscal document or automatic historical reply was sent.

## Pending before moving inbox processing fully to Zoho

Microsoft's custom-domain DKIM had no keys. Keys were created and these CNAMEs
published in Wix, without replacing the Zoho DKIM selector:

| Host | Target |
| --- | --- |
| selector1._domainkey | selector1-outsolutech-com._domainkey.outsolutech965.w-v1.dkim.mail.microsoft |
| selector2._domainkey | selector2-outsolutech-com._domainkey.outsolutech965.w-v1.dkim.mail.microsoft |

Both records resolve through public DNS, but Microsoft's enable operation still
reported DNS synchronization pending at the last check. **Microsoft DKIM signing
is not yet enabled.** Do not disable spam protection or broadly allow the domain.

After Microsoft accepts/enables DKIM, send a fresh routine test to Jenifer's public
address. Require Inbox delivery and a valid authentication result, verify body and
attachment read-only retrieval, then change only `jenifer_directa.inbox_provider`
to `zoho`. Coordinate its existing checkpoint to avoid replaying setup or historical
messages. Reload the cached native engine and verify a single reply. Retain the
Microsoft forwarding copy and license until the history/migration decision is made.

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
