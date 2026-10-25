# ReliefMesh Pages

Each page lists its mockup, the code it replaces, its layout, and the fixes to apply on top of the mockup. All pages follow `DESIGN_SYSTEM.md`. Screens without a mockup are specced from the same system at the end.

---

## 1. Mission workspace `/missions/[missionId]`

**Mockups:** `01-mission-plan.png`, `01-mission-plan-explain-drawer.png`, `02-mission-evidence.png`, `02-mission-evidence-ofac-drawer.png`, `03-mission-orders.png`, `03-mission-orders-confirm-send.png`
**Code:** `components/mission-workspace.tsx` and everything in `components/mission/`.

### Structure change (the biggest change in the app)
Today every panel is stacked on one long page. Replace that with a page header plus **stage tabs**, each showing one stage. Keep the current tab in the URL (`?tab=plan`) so links and refreshes work.

| Tab | Existing components it uses |
|---|---|
| Context | `EmergencyPanel` |
| Suppliers & Evidence | `MarketPanel`, `SupplierEvidence` |
| Plan | `OptimizerPanel`, `PlanComparison`, `PlanVersions`, `DisruptionConsole` (demo only) |
| Approval | the approval parts of `PlanVersions` plus approval history |
| Orders | `OrdersPanel`, `OperationsPanel` deliveries |
| Audit | `Timeline`, `PaymentsPanel` |

- **Default tab** when the page opens: Plan if a plan exists, otherwise Suppliers & Evidence. After a replan, switch to Plan and show a toast: "Plan v2 ready · rebuilt in 1.8 s".
- `MissionLifecycleControls` (cancel or close mission) moves into the header's "⋯" menu.
- The header keeps the live job indicators as one gray line under the meta line when active: "Evidence checks running…" or "Replanning…".
- The demo-only disruption console becomes a quiet "Demo controls" section at the bottom of the Plan tab, with a secondary button **"Disrupt supply chain"** that opens a dialog (Disruption type, Supplier, then "Apply disruption"). It only appears when `demoMode && isAdmin`, as today.

### Plan tab (`01-mission-plan.png`)
- Main column: "Plan v2" plus status text, then one sentence explaining the latest change ("Rebuilt automatically at 14:32 after Bayside Relief Supply Co withdrew. Plan v1 and its approval no longer apply. Replanned in 1.8 s."). Then the total (36px) with "+$195 vs v1", the coverage line, the **Allocation table** (Supplier · Qty v1 → v2 · Unit · Ship · v2 subtotal · vs v1, with withdrawn suppliers as a muted last row), the **Not eligible** list, and "View activity →" (goes to the Audit tab).
- Right rail: **Approval** (approval chain, the primary "Approve plan v2" button, "Approves this exact version. Expires in 24 h."), then **Mission** (Budget, Remaining, Deliver by, Destination, Disaster → Context tab), then **Previous plan** (v1 · $3,271 · Stale, "Approval revoked at 14:32", "Compare v1 and v2 →").
- "Compare v1 and v2" opens a full-width side-by-side comparison view (the old `PlanComparison`), with changed cells marked by weight, not color.
- When the viewer created the mission and the org isn't a demo org, the Approve button is replaced by the gray sentence "You requested this mission, so another approver in your organization must approve its plan."
- When a plan is approved, the rail shows "Generate POs" as the primary, with "Creates drafts. Sending is a separate step." beneath it.
- Plan states as text: `Feasible` (ok), `Approved` (neutral, dark), `Stale` (gray, and the plan never shows an Approve button), `Infeasible` (warn, plus the binding constraint as one sentence).

**Fixes on top of the mockup**
- Right edges of the island, the tab rule, and the rail must align to the same content grid.
- "Review evidence →" sits on the same line as the supplier name in Not eligible.
- The Explain drawer's Sources list gives each source a one-line description: "OFAC evidence record · LIVE · retrieved 14:20".

### Explain changes drawer (`01-mission-plan-explain-drawer.png`)
Triggered from the header text action "✦ Explain changes · AI". Shows the AI explanation (read-only) and a Sources list. If the AI isn't configured, the drawer says so plainly ("Explanations aren't available because Gemini isn't configured.").

### Suppliers & Evidence tab (`02-mission-evidence.png`)
- Top actions: "RFQ invitations →" (a drawer listing invitations and their status), secondary "Send RFQ" (dialog with Supplier email), and secondary "Discover leads" (dialog with the Apify search, results shown as leads). Use only one primary on the page.
- One row per supplier: name, quote (`70 @ $32.40 · Ship $75 · ETA Oct 27 · v1`), evidence, and the policy verdict as text.
- **Evidence density fix:** when all checks pass, collapse to one line ("5 of 5 checks clear · View checks") that expands inline. A supplier with any non-pass result opens expanded by default.
- Each check line: `OFAC · Potential match · LIVE · 14:20`. Clicking it opens the evidence drawer.
- Verdicts: Eligible (neutral), Needs review (warn), Blocked (dark, with the reason), Withdrawn (whole row muted).
- **Clear finding** and **Block supplier** are text buttons, without arrows. Clear finding opens a dialog that requires a reason (the field keeps the label "Clear finding reason"). Block asks for confirmation.
- "Seed TEST suppliers" stays, as a secondary button shown only in demo mode with no suppliers yet.
- "Buy signed dossier · 0.01 devnet USDC (x402)" moves into the supplier's evidence drawer as a secondary button.
- Keep `data-testid="supplier-{name}"` on each row.

### Evidence drawer (`02-mission-evidence-ofac-drawer.png`)
Supplier name, verdict, then Result / Provenance / Retrieved / Source link. Then a **Raw record excerpt** taken from the real API response (the mockup's "TEST fixture" text is wrong: TEST suppliers are screened against the live list, so show what actually came back). Then "Why allocation is blocked" in plain words, and the Clear finding / Block supplier actions.

### Orders tab (`03-mission-orders.png`)
- Context line at the top: "Plan v2 approved by Jordan Park at 14:40. Draft POs generated at 14:41."
- Heading "Purchase orders · TEST suppliers", with "Supplier acceptance confirms the order only. It is not payment." as its subtitle (moved up from the bottom of the mockup).
- One row per PO: PO number, supplier, quantity and total, the progress line, and the supplier's latest note. Remove the separate status word, since the progress line already says it. In the right column, show the next action or an expected date ("Expected Oct 27").
- A draft PO shows the primary **"Confirm & send"**, which opens the confirmation dialog (`03-mission-orders-confirm-send.png`): recipient email, line items, shipping, total, and "This emails the purchase order to the supplier. It can't be unsent."
- **Generate POs** and **Confirm & send** stay separate steps.
- `OperationsPanel` deliveries (email, Slack, calendar, drive notifications) go under a quiet "Notifications" heading below the POs, using the same row style.

### Approval tab (no mockup)
- Current approval status at the top, with the approval chain.
- Then an approval history table: Plan version · Status (Active, Revoked, Expired, Used) · Approver · Time · Reason (e.g. "Revoked: Bayside withdrew"). Approvals never carry over to a changed plan, so this table shows that story.
- The segregation-of-duties sentence when relevant.

### Audit tab (no mockup)
- One line at the top: "Hash chain verified · 14 events · head 7b92…e14c", or in `--critical`, "Hash chain broken at event #9" if the verification endpoint reports a break.
- A timeline table: # · Time · Event (human-readable) · Actor · Hash (shortened, with the full hash on hover and a copy button).
- Payments (x402) below: Supplier · Amount · Network (`Solana devnet · test USDC`) · Transaction (explorer link →) · Verified.

### Context tab (no mockup)
- The linked NASA EONET event: title, category, coordinates, and a link. A map like the dashboard's, showing the event and the delivery location.
- Then NWS alerts, NASA FIRMS detections (48 h), and OpenFEMA declarations as rows with provenance. If unavailable, show one gray line with the reason ("NWS unavailable · ProxyError 403") and no fake data.

---

## 2. Coordinator dashboard `/dashboard`

**Mockups:** `04-dashboard.png`, `04-dashboard-new-mission.png`
**Code:** `app/dashboard/page.tsx`, `mission-form.tsx`, `organization-form.tsx`

- Header: "Missions", the organization switcher as text with a chevron, and the primary "New mission" button on the right.
- Left (about 55%): mission rows with name, location · quantity, the state sentence, the linked event, and one next-action link.
- Right (about 40%): map of delivery locations (crosses) and linked events (triangles), joined by thin lines. Use a real tile source with attribution (e.g. a light gray basemap) and the real coordinates from the API. Label demo-only archived events as "archive".
- **New mission** opens a slide-over (`04-dashboard-new-mission.png`). Keep every existing field label, because the tests use them: "Real emergency (NASA EONET, open events)", "Mission name", "Delivery location", "Delivery deadline", "Budget (USD)", "Required item", "Quantity", max share. "Add item" is a text action with no arrow.
- **Members and organization creation move to Settings** (see section 7). The empty state for a new user with no organization shows a single centered prompt: "Create your organization to start a mission", with the organization name field, the demo checkbox (demo mode only), and "Create organization".

**Fixes on top of the mockup**
- Secondary text must be neutral gray `#5F6368`, not the slate blue it drifted to.
- Every mission row shows its linked event, not just one.

---

## 3. Supplier portal `/supplier`

**Mockups:** `05-supplier-orders.png`, `05-supplier-revise-quote.png`
**Code:** `app/supplier/page.tsx`

- Split into three tabs matching the supplier island: RFQs, My Quotes, Purchase Orders (`?tab=`).
- **Purchase Orders:** a new PO shows the primary "Accept" and a text "Decline". Accepted POs show "Mark shipped" (secondary), "Mark delivered", and "Cannot fulfill" (text), plus the tracking note field. Delivered POs show their dated event history in gray. Every row shows quantity and total.
- Keep "Accepting confirms the order only. It is not payment." and "Declining or marking Cannot fulfill makes the buyer's plan replan automatically."
- **My Quotes:** rows with status and "Revise quote". Revise opens the slide-over with unit price, available quantity, shipping, and expiry, and the notes "Any change invalidates the buyer's current plan approval and triggers automatic replanning." and "Competitors never see your quote." Footer: Cancel plus a primary save. "Withdraw quote" is a text button at the bottom with **no arrow** that opens a confirm dialog.
- Decline, Cannot fulfill, and Withdraw each confirm first, with an optional reason.

---

## 4. Supplier RFQ and quote form `/invitations/[token]`

**Mockups:** `06-supplier-quote-ai-draft.png`, `06-supplier-quote-submitted.png`
**Code:** `invitation-client.tsx`, `quote-form.tsx`

- Request summary at the top in plain text: title, buyer, quantity, destination, deadline.
- The form has **one row per required item**, each tied to its `requirement_id`, plus shipping and quote expiry.
- **AI drafting, kept accurate to what the code does:** the assistant reads **pasted text**, not uploaded files. Show it in the right column as "Draft from an existing quote · Gemini", with the paste textarea and the "Pre-fill with Gemini" secondary button. Keep the existing per-field source excerpt ("From your text: …"), which is better than the mockup.
- Each pre-filled field shows a small gray "AI draft" label beside its label. The label **disappears when the supplier edits that field.**
- A required checkbox "I reviewed the values and confirm they are correct." keeps the primary submit disabled until checked, with "Confirm review to submit." beneath it.
- After submit, the page becomes the read-only summary in `06-supplier-quote-submitted.png`: "This quote is binding. You can revise or withdraw it from My Quotes. The buyer's plan will update automatically." and a primary "View in My Quotes".
- If Gemini isn't configured or is rate limited, keep showing those states plainly (`GEMINI_NOT_CONFIGURED`, `GEMINI_RATE_LIMITED` messages stay visible to the tests).

---

## 5. System Status `/status` (public)

**Mockups:** `07-system-status.png`, `07-system-status-nws-expanded.png`
**Code:** `app/status/page.tsx`

- The page is public. When logged out it shows the marketing island; when logged in, the coordinator island.
- Summary line: "13 of 15 integrations operational · checked 14:32 · Re-check now" (an action, so **no arrow**).
- Groups: Disaster signals, Supplier screening, Agents and payments, Infrastructure, using the API's `category`. Columns: Integration · Status · Provenance · Detail · Latency 24 h · Current.
- Status words: Operational (neutral), Degraded (warn), Not configured (gray), Error (critical).
- Rows expand inline to show recent checks and the latest error.
- **Data truth:** the API returns only the **current** check today (`latency_ms`, `checked_at`), with no history. Until the backend keeps recent results, hide the sparkline column and show only the current check in the expanded row. Don't draw fake history. Adding a small check-history store in the API is a good follow-up and would unlock both features.

---

## 6. Landing page `/`

See `LANDING.md`.

---

## 7. Screens without mockups

Build these from the same system. Keep each one simple.

- **Sign in / Sign up** (`auth-form.tsx`, `sign-up-client.tsx`): a centered 400px column on white with the wordmark, title, fields, one primary, and a text link to the other form. Sign-up keeps the role choice (Coordinator / Supplier) as two outlined radio cards. Keep the button labels "Create coordinator account" and "Create supplier account".
- **Join an organization** (`join-client.tsx`) and **accept an RFQ** (`invitation-client.tsx` before the form): same centered column, the invitation facts in plain text, and one primary ("Accept invitation", "Accept RFQ").
- **Settings** (`/settings`): left-aligned page with tabs **Organization** (name, demo flag, create organization), **Members** (the current `MembersPanel`: member rows with role, "Add member" form, the segregation-of-duties note), and **Integrations** (the existing `/settings/integrations` page restyled: Gmail, Google Calendar, Google Drive, Slack as rows with state text LIVE / DEGRADED / NOT CONFIGURED / BLOCKED and a connect or test action). Reach it from the avatar menu.
- **Suppliers** (coordinator tab): a table of every supplier across missions with name, missions, last quote, verdict, and last screened. Rows open the supplier drawer. If the API has no cross-mission endpoint yet, show the suppliers for the current organization's missions only.
- **Analytics** (coordinator tab): a small set of figures computed from real data only (missions, quotes received, average replan time, approvals revoked, POs delivered) as plain number + label pairs. If a figure can't be computed from the API, leave it out. A simple "Coming soon" page is acceptable for the hackathon.
- **Privacy / Terms** (`legal-page.tsx`): a 680px reading column, 16px body, plain headings.
- **Mobile (under 768px):** the island collapses to a menu. Mission stage tabs scroll horizontally. The right rail moves under the main column, **with the Approval section first**. Tables become stacked rows. Drawers become full-screen sheets.
