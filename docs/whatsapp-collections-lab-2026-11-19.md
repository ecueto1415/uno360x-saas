# WhatsApp invoice reminders - laboratory phase (2026-11-19)

Scope: invoice collection reminders for each tenant's own customers and own business number. This is not SaaS subscription collection or payment processing.

## Installed only in QA
Module: uno360x_whatsapp. Explicit installation in the isolated rootless QA database under /var/lib/uno360x-saas/qa-606-20261119. Not added to the common installation catalog, customer databases or reserves. Read-only final audit: INCIVI and CuetoExpress installed module count = 0. OUTSOLUTECH was not changed.

Routes: /uno360x/cobros/whatsapp, /factura/<id>, /aviso/<id>, /configuracion, /cliente/<partner_id>. Available under the existing Finanzas navigation when installed. Accounting managers configure numbers and recipient authorization; collectors require both their explicit collection role and existing invoice access. Granting the collection role does not grant invoice permissions.

## Implemented
- Company-specific sender metadata, recipient number and explicit authorization evidence.
- Pending invoices, preview, immutable draft/history, and clearly labeled simulation.
- Recheck balance, posted state, electronic cancellation and opt-out before simulation.
- Unique daily reminder plus transaction lock; repeated clicks do not duplicate records.
- Company and linked invoice record-rule isolation; no direct public state manipulation.
- Minimal template payload and signature verification primitive; no live transport or webhook route.

## Validation
Five protocol unit tests passed. The isolated Odoo integration script deployment/validate_whatsapp_lab.py passed permission, company isolation, invoice record-rule, payment/credit/cancellation, consent, changed-number, duplicate-click, timezone and immutable-state cases. All fictional accounting fixtures rolled back. Log: QA whatsapp/validation.log.
Five actual QWeb views rendered. Desktop and 390px mobile preview inspected; review document width 375px at 390px viewport, no horizontal overflow.
The browser inspection used exported read-only QWeb snapshots, not live authenticated POST requests. Controller POST navigation/CSRF end-to-end browser testing remains for a dedicated HTTP QA session.

## Review artifacts
dev/prepare_whatsapp_preview.py packages the actual exported HTML and local CSS into a read-only viewer. The copy blocks forms/network operations and explicitly identifies fictional data. It does not claim to connect or save settings.
The delivered PDF contains actual rendered screenshots. Business fixtures are fictional and fiscal identifiers are memory-only display mocks, never reserved or submitted.

## Pending before real messaging
Meta business onboarding per company, approved template, protected company-scoped tokens and secret rotation, verified webhook status/replies, opt-out handling from inbound messages, delivery reconciliation and uncertain-send idempotency.
No cron/automatic cadence, PDF attachment transport, card collection or payment posting is implemented. Real sending must revalidate payment immediately before dispatch, preserve a stable provider attempt identity, and avoid automatic resend on ambiguous timeouts.
Confirm business-hour/cadence policy and obtain recipient permission before enabling reminders. Do not reuse Jenifer SMTP, OpenAI or DGII credentials.

## Official references checked
- https://developers.facebook.com/documentation/business-messaging/whatsapp/overview
- https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview/
- https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview/
- https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in/
- https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint/
- https://business.whatsapp.com/policy
Checked 2026-11-19. Template approval and number eligibility are decided by Meta; no eligibility guarantee.
