# ReliefMesh Design Handoff

Everything needed to apply the new ReliefMesh UI to the existing frontend. Drop this `design/` folder at the repo root.

## Files
- `DESIGN_SYSTEM.md`: tokens, global rules, and shared components. Read this first.
- `PAGES.md`: every app screen, mapped to the code it replaces, plus specs for screens without a mockup.
- `LANDING.md`: the landing page, including its diagram and interactive failure demo.
- `BUILD_PLAN.md`: ground rules, e2e test impact, the eight build phases, and the prompts to give Claude Code.
- `mockups/`: the approved images.

## Mockups
| File | Screen |
|---|---|
| `01-mission-plan.png` | Mission · Plan tab after a replan |
| `01-mission-plan-explain-drawer.png` | Plan tab with the Explain changes drawer |
| `02-mission-evidence.png` | Mission · Suppliers & Evidence tab |
| `02-mission-evidence-ofac-drawer.png` | Evidence drawer for Pioneer's OFAC result |
| `03-mission-orders.png` | Mission · Orders tab |
| `03-mission-orders-confirm-send.png` | Confirm & send dialog |
| `04-dashboard.png` | Coordinator dashboard with map |
| `04-dashboard-new-mission.png` | New mission slide-over |
| `05-supplier-orders.png` | Supplier portal · Purchase Orders |
| `05-supplier-revise-quote.png` | Supplier portal · Revise quote slide-over |
| `06-supplier-quote-ai-draft.png` | RFQ quote form with AI draft |
| `06-supplier-quote-submitted.png` | Quote submitted |
| `07-system-status.png` | System Status |
| `07-system-status-nws-expanded.png` | System Status with a row expanded |
| `08-landing-hero.png` | Landing · hero |
| `08-landing-how-it-works.png` | Landing · tool diagram |
| `08-landing-supplier-fails.png` | Landing · failure scene with scrubber |
| `08-landing-closing-footer.png` | Landing · closing and footer |

## Important
- The mockups are images generated during design. Small text inside them may be garbled, and some demo values are illustrative. The specs hold the exact copy, data, and rules.
- Where a spec says a mockup is wrong (for example, fake history on the status page or the audit entry appearing too early on the landing page), follow the spec.
