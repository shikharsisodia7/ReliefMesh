# ReliefMesh Landing Page `/`

The expressive screen. Uses the marketing tokens (`--ink`, `--signal`, `--sand`, `--charcoal`) from `DESIGN_SYSTEM.md`. Replaces `frontend/src/app/page.tsx`.

**Section rhythm:** white hero → sand "How it works" → charcoal "When a supplier fails" → orange closing and footer.

---

## 1. Hero (white) · `08-landing-hero.png`

- Marketing island nav: ReliefMesh · How it works (scrolls to section 2) · System Status · Sign in · primary "Start a mission".
- Headline, centered, 72–80px/700: "Emergency procurement" / "**that rebuilds itself.**" (second line in `--signal`).
- Subhead, 20px gray: "When a supplier fails mid-disaster, ReliefMesh rebuilds the purchasing plan in seconds and asks a human to approve it again."
- Buttons: primary "Start a mission" (`/sign-up`), text link "Supplier portal →" (`/sign-up?role=supplier`).
- **Visual:** a product shot of the Plan v2 recovery screen in a browser frame, over a **dot-matrix map of California** where highlighted orange dots are **real NASA FIRMS detections from the last 48 h** (fetched through our API; if unavailable, show the map with no highlights and no caption claim).
  - Build the product shot as a real, scaled-down React render of the Plan tab with static demo data (preferred, crisp at any size), or as an exported screenshot.
  - Dot map: an SVG grid of dots clipped to the state outline. Detections are projected to the nearest dot.
- **Live strip** under the shot, one gray line: "Live: NASA FIRMS fire detections, last 48 h · 3 open NASA EONET events in California · 13 of 15 integrations operational · View status →". Every number comes from the API (`/v1/integrations/status` and the EONET endpoint). Hide any part that fails to load.

## 2. How it works (sand) · `08-landing-how-it-works.png`

A diagram canvas, built as **HTML and SVG**, not an image, so it's crisp and can animate.

- Sand background with a dot grid (1px dots, 24px apart, about 8% darker than the sand).
- Lane labels in small caps gray: DATA · FETCHED LIVE / RULES & MATH · DECIDE / HUMAN · APPROVES.
- Nodes are white cards (14px radius, `--sand-border`, soft shadow) with a 36px logo tile, a name, and a one-line role:
  - Sources stacked on the left: NASA EONET, NWS, NASA FIRMS, OpenFEMA, merging into **Apify** "Supplier discovery · ✓ 4 suppliers found".
  - **Evidence & screening** with five small logo tiles (OFAC, openFDA, USAspending, SAM.gov, CRS) and "✓ 20 checks · 1 needs review".
  - **Decision core** containing Rules ("deterministic policy") and Optimizer ("PuLP / CBC · ✓ Plan v2 in 1.8 s"), joined by "3 eligible".
  - **Human approval** with the JP avatar, "Independent approver", and a 1.5px `--signal` border.
  - **Purchase orders** branching to "Supplier email" and "Audit log · SHA-256".
- Edges are thin curves with port dots, labeled with real data: Wildfire · Oakland → 4 suppliers → 20 checks → 3 eligible → Plan v2 · $3,466 → Approved.
- The Optimizer → Human approval → Purchase orders path is solid `--signal` with a soft glow. It's the only colored path.
- AI lane below with dashed connectors pointing up: Gemini "drafts quotes" → Screening, Fetch.ai agent "answers questions" → Decision core, Explain changes "read-only" → Human approval. Caption: "AI assists. It never decides."
- Footer tiles: System of record · MongoDB; Every step · SHA-256 audit; Evidence purchases · Coinbase x402 · Solana devnet (test USDC).

**Logos:** use official SVG assets for companies (Apify, Google Gemini, Fetch.ai, MongoDB, Coinbase, Solana, CRS) in `public/logos/`. For federal agencies (NASA, NOAA/NWS, FEMA, Treasury/OFAC, FDA, USAspending, SAM.gov), **use text wordmarks in the logo tile instead of their seals or insignia**, because those agencies restrict use of their marks. Fill the empty icon tiles from the mockup (Rules, Optimizer, Explain changes, SHA-256) with lucide line icons.

**Motion:** when the section scrolls into view, the edges draw left to right (stroke-dashoffset, 1.2s total), each node's check fades in as its edge arrives, and the orange path draws last. Plays once. Respect reduced motion.

## 3. When a supplier fails (charcoal) · `08-landing-supplier-fails.png`

- Charcoal background with a low-contrast dot-matrix map of California. A few dots near the Bay Area glow `--signal`.
- Headline, white, left-aligned: "When a supplier fails, the plan rebuilds itself."
- **The scene:** four real product fragments layered and overlapping at different depths:
  1. Supplier notice (back left, rotated −2°): "Bayside Relief Supply Co · Quote withdrawn · 14:32:08".
  2. Plan card (center, largest): ~~$3,271~~ → **$3,466** (+$195), the three quantity changes, "Approval revoked · new approval required".
  3. Approval request (front right, `--signal` 1.5px border): JP · "Jordan Park · Approve plan v2 · $3,466", a primary "Approve" with "Demo only".
  4. Audit entry (small, bottom right): "#14 plan.approved · 7b92…e14c".
  - Two callouts with thin white leader lines: at the `60 → 0` row, "Bayside's 60 blankets, reassigned."; at +$195, "Still $1,534 under budget."
- **Timeline scrubber** under the scene: 14:32:08 Quote withdrawn · 14:32:08 Approval revoked · 14:32:10 Plan v2 ready · 14:40 Approved. The track fills `--signal` up to a white handle. A "Simulate failure" play button on the left.

**Interaction (this is the landing page's live demo; everything client-side with static demo data, no API calls):**
- The section's initial state is **before the failure**: plan card shows Plan v1 ($3,271, Bayside 60, Golden Gate 40), no supplier notice, no approval card.
- Pressing play (or dragging the handle) steps through the four moments over about 4 seconds: the supplier notice slides in → the plan card's rows animate to the new quantities and the total counts to $3,466 → "Approval revoked" appears → the approval card slides in → at 14:40 the Approve button shows "Approved" and the audit entry appears.
- **Fix from the mockup:** the audit entry must only appear at the 14:40 moment, since the approval hasn't happened yet at 14:32:10.
- "Approve" in this demo only advances the scrubber to 14:40. It never calls the API.
- Remove the stray orange dots near the headline; the glowing dots belong to the map's Bay Area only.

Proof line beneath, gray: "20 evidence checks per plan · 0 approvals carried over · every step on a SHA-256 hash chain."

## 4. Closing and footer (orange) · `08-landing-closing-footer.png`

- Full-bleed `--signal` block. All text and the button in `--ink`.
- Top left: "AI explains. It never approves." (56px/700) with "Rules decide eligibility. Math allocates. People authorize spending." (20px). Top right: primary "Start a mission" (ink fill, white text).
- Four link columns: **Product** (How it works, System Status, Supplier portal), **Project** (GitHub, Devpost, Fetch.ai agent on Agentverse; use the real URLs from the README), **Data** (NASA EONET, NWS, NASA FIRMS, OpenFEMA, OFAC, openFDA, USAspending, SAM.gov, each linking to the source), **Sponsors** (Fetch.ai, CRS, Apify, Coinbase x402, Solana).
- Bottom: a giant dot-built "ReliefMesh" wordmark across the full width, cropped by the bottom edge, as an SVG of dots. "Built at Cal Hacks 13.0" sits above the wordmark's right end (not overlapping it, as in the mockup).
- Privacy and Terms links in small text at the very bottom.

## 5. Mobile

Headline drops to 44px. The product shot scales to fit. The diagram becomes a vertical flow (stacked nodes with connectors running down) with the AI lane as a list underneath. The failure scene stacks its fragments vertically, with the scrubber below. The footer columns become two columns, then one.
