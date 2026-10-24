# ReliefMesh frontend handoff

The frontend is a Next.js App Router client in `frontend/`. Business state is intentionally kept behind `src/lib/api.ts`; visual work should change components and Tailwind classes without moving authorization, price calculation, or procurement rules to the browser.

## Routes and ownership

| Route | Purpose | Primary component |
| --- | --- | --- |
| `/` | Product landing page | `src/app/page.tsx` |
| `/sign-in`, `/sign-up` | Authentication entry points | `src/components/auth-form.tsx` |
| `/dashboard` | Coordinator organization and mission creation | `src/app/dashboard/page.tsx` |
| `/missions/[missionId]` | RFQs, quote comparison, planning, approvals, POs | `src/components/mission-workspace.tsx` |
| `/invitations/[token]` | Supplier RFQ acceptance and quote submission | `src/components/invitation-client.tsx` |
| `/supplier` | Supplier quote revisions/withdrawals and PO inbox | `src/app/supplier/page.tsx` |

## Design integration boundaries

- Use the generated shadcn primitives in `src/components/ui/` for new visual primitives. They are already used by all workflow screens.
- Keep all remote calls in `src/lib/api.ts`; use TanStack Query in page/workspace components for data refresh and mutation invalidation.
- Keep forms on React Hook Form + Zod. The key flow forms are isolated in `organization-form.tsx`, `mission-form.tsx`, and `quote-form.tsx`.
- `useSession()` provides client session state. Do not infer permission from a hidden button: the FastAPI backend enforces role and organization access.
- A plan card must visibly distinguish `feasible`, `approved`, `stale`, and `infeasible`. `stale` means approval is invalid and must not look actionable.
- Preserve the explicit `Confirm & send` PO action. Generating a draft PO is deliberately separate from emailing it.

## API expectations that affect UI

- The API base URL comes from `NEXT_PUBLIC_API_BASE_URL`.
- Quote and plan lists poll every two seconds in a mission workspace so a submitted quote or replan becomes visible without a frontend-only event simulation.
- Development can expose an invitation link only with `RELIEFMESH_EXPOSE_INVITATION_LINKS=true`; production must keep it `false` and relies on actual email delivery.
- API error messages are safe to show in the current inline error panels. Preserve retry/error/empty states when restyling.
