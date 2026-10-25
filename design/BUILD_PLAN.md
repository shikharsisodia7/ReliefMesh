# ReliefMesh UI Overhaul: Build Plan for Claude Code

## Ground rules for every phase

1. **Don't move logic.** All requests stay in `src/lib/api.ts`, data loading stays in TanStack Query, and forms stay on React Hook Form + Zod. Authorization, prices, and policy stay on the backend. This is a visual and structural change only.
2. **Keep every capability.** Every action that exists today must still exist after the change (Seed TEST suppliers, Discover leads, Send RFQ, Clear finding, Block supplier, Buy signed dossier, Run optimization, Approve plan, Generate POs, Confirm & send, disruptions, lifecycle controls, deliveries, payments, audit verification).
3. **Truth rules stay.** Provenance labels on all evidence, `stale` plans never approvable, the segregation-of-duties message, Generate POs separate from Confirm & send, demo tooling only when the API says `demo_mode`, and no invented data (see the status page and landing notes).
4. **Keep it simple.** Prefer plain components and CSS over new libraries. No animation library is needed; CSS transitions and a small `useCountUp` hook are enough. Add a dependency only if a spec can't be met without one (a map tile library for the dashboard is the one likely exception), and say why in the commit.
5. **Short, plain code comments only.** No banner comments.
6. **After every phase, run:** `npm run lint`, `npm test`, `npm run build`, and the Playwright suite (`npm run test:e2e` with the API running in demo mode, see the README). Don't start the next phase until they pass.
7. **Commit at the end of each phase** with a clear message. Work on a branch such as `design/ui-overhaul`, cut from the latest `main`.

## The e2e tests will need updates

The Playwright specs find elements by their visible text. The new design changes some of that text on purpose. In the **same commit** as each visual change, update the affected tests so they check the same behavior with the new wording. Where text is no longer a stable hook, add a `data-testid` and test against it. Never delete a check to make a test pass.

Text the new design changes:

| Test looks for | New design shows | Suggested approach |
|---|---|---|
| `NEEDS REVIEW` | `Needs review` | match case-insensitively |
| `OFAC POTENTIAL_MATCH`, `OFAC NO_MATCH` | `OFAC · Potential match`, `OFAC · No match` | match the new text, or keep the raw code in a `data-result` attribute |
| `OLD PLAN`, `NEW PLAN`, `INVALIDATED` | "Previous plan", "Stale", "Approval revoked" | test the new words on the Plan tab and in the compare view |
| `DISRUPT SUPPLY CHAIN` | "Disrupt supply chain" | case-insensitive match |
| `+$195.00`, `Total $3,271.00` | `+$195`, `$3,271` | keep cents in the compare view and the Approval tab, or update the regexes |
| `sent`, `supplier_accepted`, `completed`, `approved` (raw status codes) | "Sent", "Accepted", "Delivered", "Approved" | map codes to words in one helper and test the words |
| "Revise price or inventory", "Save revision" | "Revise quote", "Save changes" | update the test |
| Elements on one long page | Elements on different tabs | click the tab first (`getByRole("tab", { name: "Plan" })`) |
| "Add member" on the dashboard | moves to Settings → Members | navigate to Settings first |

Labels that **stay exactly the same**: every form field label listed in the tests ("Mission name", "Budget (USD)", "Clear finding reason", "Supplier email", and so on), and the buttons "Run optimization", "Approve plan", "Generate POs", "Confirm & send", "Seed TEST suppliers", "Clear finding", "Send RFQ", "Create mission", "Create organization", "Accept", "Mark delivered", "Pre-fill with Gemini", "Submit binding quote", "Withdraw quote", "Apply disruption", "Close evidence". The "Approve plan v2" button text is fine because `getByRole` matches "Approve plan" as a substring.

## Phases

### Phase 1: Tokens, fonts, primitives
Replace the `:root` palette in `globals.css` with the tokens in `DESIGN_SYSTEM.md`, switch Geist to Inter, and restyle `components/ui/` (button, input, label, table, textarea). Replace `ProvenanceBadge`, `PolicyBadge`, `PlanStatusBadge`, and `StatusDot` with text-only `StatusText` and `Provenance`. Add the Drawer, SlideOver, and Dialog shells. The app will look half-converted after this phase, and that's expected.

### Phase 2: Island nav and page layout
Rebuild `app-header.tsx` as the island with the three tab sets and the avatar menu. Add the shared page header. Move Members and organization creation into a new `/settings` page with tabs (Organization, Members, Integrations), folding in the existing `/settings/integrations`.

### Phase 3: Mission workspace
The biggest phase. Split `mission-workspace.tsx` into the six stage tabs with `?tab=`, then rebuild each tab per `PAGES.md` section 1: Plan (with the rail, Explain drawer, compare view), Suppliers & Evidence (rows, evidence drawer, dialogs), Orders (progress line, confirm dialog, notifications), Approval, Audit, Context. Do it one tab per commit. Run the judge scenario e2e after each tab.

### Phase 4: Dashboard
Mission rows, the map, the New mission slide-over, and the empty state.

### Phase 5: Supplier side
The supplier portal tabs, the Revise quote slide-over and confirm dialogs, and the RFQ quote form with the AI-draft labels and review checkbox.

### Phase 6: Status, auth, legal, Suppliers, Analytics
Per `PAGES.md` sections 5 and 7.

### Phase 7: Landing page
Per `LANDING.md`. Build the diagram and the failure scene as real HTML/SVG with the described motion. Put logo assets in `public/logos/`.

### Phase 8: Mobile and polish pass
Check every screen at 390px and 1440px, keyboard focus on all controls, reduced motion, and contrast (WCAG AA). Compare each screen side by side with its mockup and fix drift.

## Prompts to give Claude Code

Open the repo in VS Code with Claude Code, on the new branch. Start every session with the first prompt, then one phase prompt at a time.

**Session start**
> Read `design/README.md`, `design/DESIGN_SYSTEM.md`, `design/PAGES.md`, `design/LANDING.md`, and `design/BUILD_PLAN.md`, and look at the images in `design/mockups/`. This is a visual and structural redesign of the existing Next.js frontend in `frontend/`. Follow the ground rules in `BUILD_PLAN.md` exactly: no logic moves out of `lib/api.ts`, every existing capability stays, truth rules stay, keep code simple with short plain comments, and update e2e tests in the same commit as any wording change. Don't write code yet; summarize the plan for Phase 1 and list any conflicts you see between the specs and the current code.

**Each phase**
> Do Phase N from `design/BUILD_PLAN.md`, following `DESIGN_SYSTEM.md` and the matching sections of `PAGES.md` (or `LANDING.md`). Compare your result with the listed mockups and apply the "Fixes on top of the mockup" notes. When you're done, run lint, unit tests, build, and the Playwright suite, fix anything that fails, then commit with a clear message and tell me what changed and anything you couldn't match.

**When something looks off**
> On the [screen] at [width], [describe the problem]. Fix it to match `design/mockups/[file]` and the rules in `DESIGN_SYSTEM.md`, without changing behavior.
