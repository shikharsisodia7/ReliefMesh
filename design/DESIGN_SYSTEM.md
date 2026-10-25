# ReliefMesh Design System

The visual rules for every screen. Approved mockups live in `design/mockups/`. When a mockup and this file disagree, this file wins, because it includes fixes made after the mockups were drawn.

There are two layers that share one foundation:
- **Work screens** (mission tabs, dashboard, supplier portal, settings): calm, dense, quiet.
- **Expressive screens** (landing page, and lightly the dashboard map and status page): large type, dark and sand sections, signal orange, motion.

## 1. Tokens

Replace the `:root` block in `frontend/src/app/globals.css` and remove the unused `.dark` block. Keep the shadcn variable names so the `ui/` primitives keep working.

### App colors
| Token | Value | Use |
|---|---|---|
| `--background` | `#FFFFFF` | Page |
| `--foreground` | `#202124` | Primary text, primary button fill |
| `--muted-foreground` | `#5F6368` | Secondary text, labels, table headers |
| `--text-tertiary` | `#80868B` | Timestamps, disabled text |
| `--border` | `#DADCE0` | Dividers, inputs, outlined buttons |
| `--muted` | `#F8F9FA` | Hover rows only |
| `--ring` | `#315BD6` | Keyboard focus ring only (never links or fills) |
| `--ok` | `#18734B` | The word "Feasible", "Eligible", "Operational" when it needs emphasis |
| `--warn` | `#8A5700` | The words "Needs review", "Degraded" |
| `--critical` | `#B42318` | Real errors only: API unreachable, failed request, integration "Error" |

### Marketing colors (landing page only)
| Token | Value |
|---|---|
| `--ink` | `#15161A` near-black |
| `--signal` | `#F25C1F` signal orange |
| `--sand` | `#F5F2EC` warm canvas |
| `--sand-border` | `#E4DED4` |
| `--charcoal` | `#17181B` dark section |

### Type
Switch `layout.tsx` from Geist to **Inter** (`next/font/google`). Use tabular numerals for every number (`.tabular` utility already exists).

| Role | Size / weight |
|---|---|
| Page title | 28px / 600 |
| Key figure (one per screen, e.g. `$3,466`) | 36px / 600 |
| Section heading | 16px / 600 |
| Body, table cells, controls | 14px / 400–500 |
| Labels, table headers, timestamps | 12px / 500, `--muted-foreground` |
| Landing headline | 72–80px / 700, tight tracking |
| Landing section title | 40–56px / 700 |

### Shape and space
- Radius: controls 6px, drawers and dialogs 10px, island nav 14px, landing cards 14px.
- Spacing: 8px grid. 32px between sections. 48px gap between the main column and the right rail.
- Shadows only on the island nav, drawers, dialogs, popovers, and landing cards. Never on rows or sections.

## 2. Global rules (hard requirements)

1. **No decorative dots.** Status is text only ("Feasible", "Stale", "Needs review"). No colored circles before words.
2. **No pills, badges, or chips.** Provenance and labels are plain small text: `LIVE · 14:20`, `TEST suppliers`, `DEMO ORG`.
3. **No tinted backgrounds** on rows, banners, or regions in the app. Hover uses `--muted` only.
4. **No translucent, frosted, or pastel-filled controls.**
5. **Exactly three button styles:** primary (solid `--foreground`, white text), secondary (white, 1px border), and text (plain). At most one primary per view.
6. **Links are dark text.** An arrow (`→`) means **navigation only**. Actions ("Re-check now", "Add item", "Withdraw quote", "Replace document", "Clear finding", "Block supplier") never get arrows.
7. **Every fact appears once per screen.**
8. **Red is for real errors only.** Withdrawn, stale, revoked, and declined are gray text, not red.
9. **Color appears in at most three words per screen.**
10. **Destructive or irreversible actions confirm first:** Withdraw quote, Decline order, Cannot fulfill, Block supplier, Confirm & send. Use a small dialog with an optional or required reason field.
11. **AI output is always labeled** with a small sparkle icon and the text "AI", and is read-only unless a human confirms it.
12. **No fake data.** If the API doesn't provide a value (a sparkline history, a timestamp), show nothing or a dash. Never invent it.

## 3. Components

Build these once in `frontend/src/components/` (new `layout/` and `patterns/` folders are fine) and use them everywhere.

### Island nav (`app-header.tsx`)
- Floating, centered, max-width about 1100px, 16px from the top. Solid white, 1px `--border`, soft shadow, 14px radius. **No blur.**
- Left: "ReliefMesh" wordmark. Center: tabs. Right: avatar circle with initials, which opens a menu (name, email, role, organization switcher, Settings, Sign out).
- Tab sets: **Coordinator:** Missions · Suppliers · Analytics · System Status. **Supplier:** RFQs · My Quotes · Purchase Orders. **Marketing:** How it works · System Status · Sign in · solid "Start a mission".
- Active tab: dark text with a 2px underline that slides between tabs (CSS transform, 200ms).
- Never put status text, health dots, or search here.
- Mobile: collapses to wordmark plus a menu button that opens a sheet.

### Page header
Breadcrumb (12px gray) → title (28px) → one meta line (14px gray, e.g. "Bay Area Emergency Logistics · DEMO ORG") → optional actions on the right (text actions, a "⋯" menu, at most one primary).

### Stage tabs (mission workspace)
Plain text tabs with an underline, spanning the full content width: Context · Suppliers & Evidence · Plan · Approval · Orders · Audit. A tab may show a short gray suffix when it needs attention ("Plan · needs approval"). **No numbered circles or connecting lines.**

### Right rail
A 30% column of label/value pairs separated by thin dividers. Sections are plain headings, not cards.

### Data row and table
Open rows with 1px bottom dividers, no zebra striping, no header fill. Numbers right-aligned. A muted row (withdrawn, stale) uses `--text-tertiary` for all its text, with the reason as small text under the name.

### Status text
`<StatusText tone="ok|warn|neutral|critical">Feasible</StatusText>`. Text only. Replace `PlanStatusBadge`, `PolicyBadge`, and `StatusDot` in `status-badges.tsx` with this.

### Provenance label
`<Provenance value="LIVE" at="14:20" />` renders `LIVE · 14:20` in 12px gray caps. Replace `ProvenanceBadge`. Values stay exactly as the API sends them: `LIVE`, `CACHED`, `SANDBOX`, `TEST`, `SYNTHETIC`, `USER_SUBMITTED`, `NOT_CONFIGURED`.

### Drawer
Right side, 420px, white, 10px left radius, light scrim over the page, close on Esc and scrim click, focus trapped. Header: title, then a small gray subtitle (e.g. "AI · read-only"). Used for Explain changes, evidence records, and supplier details. The evidence drawer keeps the accessible name "Evidence detail".

### Slide-over form
Same shell as the drawer, 480px, with a sticky footer: plain "Cancel" plus one primary. Used for New mission and Revise quote.

### Dialog
Centered, 520px, for confirmations. Title, the facts being confirmed, one plain sentence about the consequence ("This emails the purchase order to the supplier. It can't be unsent."), then Cancel plus a primary.

### Progress line
Text steps joined by `→`, current step dark, others gray: `Draft → Sent → Accepted → Shipped → Delivered`.

### Approval chain
Thin gray line icons (a check in a circle, an empty circle) joined by a 1px line: "✓ Requested by Maya Chen · 2:20 PM" → "○ Your approval".

### Sparkline (status page)
60×16px, 1px neutral gray line, no fill, no axes. Render only when the API returns history.

### Empty, loading, error
- Empty: one gray sentence plus one action, e.g. "No quotes yet. Send RFQ".
- Loading: gray skeleton lines in place of the content, no spinners in rows.
- Error: one line of `--critical` text with a "Retry" text action. Keep the existing API error messages.

### Motion
- Drawers and slide-overs slide in at 200ms ease-out. The scrim fades.
- When a plan total changes, count from the old value to the new one over 600ms.
- New rows fade in at 150ms. New events trigger a quiet toast at the bottom center that auto-dismisses after 4s.
- Respect `prefers-reduced-motion`.
