# ReliefMesh email sender domain

ReliefMesh sends RFQ invitations, organization invites, and purchase orders through Resend. The sending identity is
configured in exactly two environment variables on the API service; no code changes are needed to switch domains.

| Variable | Purpose |
| --- | --- |
| `RELIEFMESH_EMAIL_FROM` | Sender, e.g. `ReliefMesh Procurement <procurement@reliefmesh.us>`. Must be on a Resend-verified domain. |
| `RELIEFMESH_RESEND_API_KEY` | Sending-only Resend key restricted to that domain. |

The live deployment currently uses a temporarily verified sending domain so real RFQs can be delivered. It is
configured only in deployment environment variables, never in code, UI, or docs, and is replaced by the steps below.

## Switching to the ReliefMesh domain (e.g. `reliefmesh.us`)

1. **Resend → Domains → Add domain** `reliefmesh.us` (region us-east-1). Resend shows the exact records to create.
2. **Create these DNS records at the registrar / DNS host of `reliefmesh.us`:**

   | Purpose | Type | Name | Value |
   | --- | --- | --- | --- |
   | DKIM (signs every message) | TXT | `resend._domainkey.reliefmesh.us` | `p=…` (the public key Resend generates for this domain) |
   | SPF + bounces (Return-Path) | MX | `send.reliefmesh.us` | `10 feedback-smtp.us-east-1.amazonses.com` |
   | SPF | TXT | `send.reliefmesh.us` | `v=spf1 include:amazonses.com ~all` |
   | DMARC (policy + reports) | TXT | `_dmarc.reliefmesh.us` | `v=DMARC1; p=none; rua=mailto:dmarc@reliefmesh.us` |
   | Optional: links match the sender domain | CNAME | `app.reliefmesh.us` | the Vercel target shown when the domain is added to the web project |

   Start DMARC at `p=none`, then move to `p=quarantine` once reports show only Resend-signed mail passing. Receiving
   replies at `procurement@reliefmesh.us` additionally needs inbound mail hosting (MX on the root domain).
3. **Wait for Resend to show Verified**, then create a new **sending-only** API key restricted to `reliefmesh.us`.
4. **Update the API service environment** (Render) and redeploy:
   `RELIEFMESH_EMAIL_FROM=ReliefMesh Procurement <procurement@reliefmesh.us>` and the new `RELIEFMESH_RESEND_API_KEY`.
   If the web app moves to `app.reliefmesh.us`, also set `RELIEFMESH_FRONTEND_ORIGIN` and `RELIEFMESH_CORS_ORIGINS`.
5. **Verify:** send one RFQ to Resend's test inbox `delivered@resend.dev`, confirm "Delivered" and the Insights tab
   (DKIM/SPF aligned, DMARC present), and check `/status` shows the Resend row as operational.
6. **Retire the temporary sender:** delete the old domain-restricted Resend key. Do not touch DNS records of the
   temporary domain; they may serve other sites.
