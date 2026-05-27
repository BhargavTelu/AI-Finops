# UI/UX Redesign Implementation Plan
## SpendOps AI — Analyst-Grade SaaS Platform

**Document version:** 1.2
**Based on brief:** `docs/ai_finops_ui_redesign_general_prompt.md`
**Target audience:** CTOs, CFOs, Finance & Engineering teams
**Design direction:** Stripe / Vercel / Vantage — minimal, data-first, enterprise credibility
**Tech stack:** Next.js 14 App Router · shadcn/ui · Tailwind CSS · Tremor · Recharts · lucide-react · Framer Motion
**Last updated:** 2026-05-27 (M-P5 + M-P6 added)

---

## Implementation Status

| Milestone | Status | Completed |
|-----------|--------|-----------|
| **M-DS** Design System Foundation | ✅ COMPLETE | 2026-05-27 |
| **M-CL** Component Library | ✅ COMPLETE | 2026-05-27 |
| **M-P1** Dashboard Redesign | ✅ COMPLETE | 2026-05-27 |
| **M-P2** Cost Explorer Redesign | ✅ COMPLETE | 2026-05-27 |
| **M-P3** API Key Management Redesign | ✅ COMPLETE | 2026-05-27 |
| **M-P4** Settings Redesign | ✅ COMPLETE | 2026-05-27 |
| **M-P5** Alerts & Anomalies Redesign | ✅ COMPLETE | 2026-05-27 |
| **M-P6** Recommendations Redesign | ✅ COMPLETE | 2026-05-27 |
| **M-P7** Budgets Redesign | ⏳ NOT STARTED | — |
| **M-QA** Polish & QA Pass | ⏳ NOT STARTED | — |

---

## M-DS Completion Notes

**Completed 2026-05-27. All tokens live in production build.**

Changes shipped:
- `apps/web/src/app/globals.css` — added `--info`, `--critical`, `--*-subtle` tokens for all status types; fixed dark mode `--border` visibility (`17%` → `22%` lightness); changed `--radius` from `0.625rem` to `0.5rem` (8px base); added `--shadow-card`, `--shadow-card-hover`, `--transition-fast`, `--transition-base` CSS custom properties; added `.text-mono` utility (monospace + tabular-nums)
- `apps/web/tailwind.config.ts` — added `info`, `critical` color tokens with `.subtle` sub-keys; added `fontFamily.mono` stack override; added `boxShadow.card` and `boxShadow.card-hover` mapped to CSS custom properties; corrected border radius comments for 8px base

Token reference (for page milestone work):
- Financial values: `className="text-mono"` — monospace + tabular-nums
- Success badges: `bg-success-subtle text-success`
- Warning badges: `bg-warning-subtle text-warning`
- Critical alerts: `bg-critical-subtle text-critical`
- Info/syncing: `bg-info-subtle text-info`
- Card shadow: `shadow-card` (resting), `shadow-card-hover` (hover)
- Transitions: `transition-colors duration-150` (fast), `duration-200` (base)

---

## M-CL Completion Notes

**Completed 2026-05-27. All shared components live in production build.**

**shadcn components installed** (added to `src/components/ui/`):
`badge` · `alert` · `tooltip` · `tabs` · `separator` · `toast` · `toaster` · `dropdown-menu` · `switch` · `textarea` · `progress` · `popover` · `avatar` · `calendar`

Note: `calendar` was installed after the initial M-CL pass (missed in original). Used `react-day-picker` v10 — required fixing the generated `calendar.tsx` to use `month_grid` instead of deprecated `table` classname. All 14 shadcn components now present.

**Existing components updated:**
- `button.tsx` — base class changed to `rounded-lg` (8px); `transition-colors duration-150` explicit; `sm`/`lg` size variants corrected to `rounded-md`/`rounded-lg`
- `dialog.tsx` — overlay changed to `bg-black/50 backdrop-blur-sm` (was `/80`); content changed to `max-w-md rounded-xl shadow-card` (was `max-w-lg rounded-lg shadow-lg`); close button uses `rounded-md` and `duration-150`; footer uses `gap-2` instead of `space-x-2`

**New shared components built:**

| File | Purpose |
|------|---------|
| `src/components/ui/status-badge.tsx` | Color + icon + text badge for 7 status types (active/inactive/error/syncing/warning/critical/info) |
| `src/components/empty-state.tsx` | Centered empty state with icon, title, description, optional CTA button/link |
| `src/components/error-state.tsx` | Error state with retry button; uses `bg-critical-subtle` icon container |
| `src/components/page-header.tsx` | Consistent H1 + description + right-aligned actions slot for every page |
| `src/components/confirm-dialog.tsx` | Reusable confirmation dialog for all destructive actions (delete/revoke/remove) |
| `src/components/data-table-skeleton.tsx` | Table-shaped loading skeleton (configurable rows/columns) |

**Layout changes:**
- `nav-links.tsx` — active links now use `font-medium` for stronger visual distinction
- `(dashboard)/layout.tsx` — main content wrapped in `max-w-7xl mx-auto px-6 py-8 lg:px-10` for comfortable wide-screen layout
- `app/layout.tsx` — `<Toaster />` added to root so `useToast()` works globally on all pages

**Usage patterns for page milestone work:**

```tsx
// Status badge
import { StatusBadge } from "@/components/ui/status-badge"
<StatusBadge status="active" />
<StatusBadge status="error" label="Auth failed" />

// Empty state
import { EmptyState } from "@/components/empty-state"
<EmptyState icon={KeyRound} title="No API keys" description="..." action={{ label: "Add key", href: "/settings/integrations" }} />

// Error state
import { ErrorState } from "@/components/error-state"
<ErrorState description="Failed to load data." onRetry={() => refetch()} />

// Page header
import { PageHeader } from "@/components/page-header"
<PageHeader title="Dashboard" description="LLM spend overview" actions={<Button>Export</Button>} />

// Confirm dialog
import { ConfirmDialog } from "@/components/confirm-dialog"
<ConfirmDialog open={open} onClose={close} onConfirm={handleDelete} title="Delete budget" description="..." variant="destructive" confirmLabel="Delete" />

// Table skeleton
import { DataTableSkeleton } from "@/components/data-table-skeleton"
if (isLoading) return <DataTableSkeleton rows={5} columns={6} />

// Toast
import { useToast } from "@/hooks/use-toast"
const { toast } = useToast()
toast({ title: "Saved", description: "Settings updated." })
```

---

## Scope Overview

| Route | Page | Priority |
|-------|------|----------|
| `/dashboard` | Main Dashboard | CRITICAL |
| `/cost-explorer` | Cost Explorer / Analysis | HIGH |
| `/settings/integrations` | API Key Management | HIGH |
| `/settings` | Settings Hub | MEDIUM |
| `/anomalies` | Alerts & Anomalies | MEDIUM |
| `/recommendations` | Recommendations | MEDIUM |
| `/budgets` | Budget Management | MEDIUM |
| `/settings/slack` | Slack Integration | LOW |
| `/settings/tags` | Tag Rules Engine | LOW |
| `/usage-events` | Usage Event Log | LOW |
| `(auth)` pages | Sign-in / Sign-up | LOW |

**Total routes in scope: 11 main + 4 settings sub-routes = 15 pages**

---

## Current-State Snapshot

### Foundation (M-DS + M-CL complete as of 2026-05-27)
- **19 shadcn/ui components** installed: Button, Dialog, Input, Label, Select, Skeleton + Badge, Alert, Tooltip, Tabs, Separator, Toast, Toaster, Dropdown Menu, Switch, Textarea, Progress, Popover, Avatar
- **6 new shared components**: StatusBadge, EmptyState, ErrorState, PageHeader, ConfirmDialog, DataTableSkeleton
- **Full design token system**: HSL CSS variables for all status types (success/warning/critical/info) with subtle tint variants; `--radius: 0.5rem`; `shadow-card`/`shadow-card-hover`; `.text-mono` utility
- **Layout**: `max-w-7xl` content wrapper, responsive padding (`px-6 lg:px-10`), Toaster in root
- Framer Motion helpers, Tremor + Recharts charts, lucide-react icons, TanStack Table — all unchanged

### Remaining gaps (to be addressed in page milestones M-P1 through M-P7)
- Page-level layouts not yet redesigned (dashboard, cost explorer, integrations, settings, etc.)
- Table number alignment and `.text-mono` not yet applied to existing tables
- Empty/error/loading states not yet wired into existing pages
- PageHeader not yet used on any existing page
- Responsive layout not verified below 1024px on any existing page

---

## M-P1 Completion Notes

**Completed 2026-05-27.**

Changes shipped:
- `apps/web/src/app/(dashboard)/dashboard/period-selector.tsx` — **NEW** client component; segmented Tabs control (7d / 30d / 90d) that drives URL param `range`, triggering server re-fetch of timeseries + provider data
- `apps/web/src/components/dashboard-charts.tsx` — **Full redesign**: KPI numbers upgraded to `text-3xl font-bold text-mono`; `DeltaBadge` uses pill style (green/red rounded badge); sparklines preserved; `ProviderDonut` shows legend+tooltip; **NEW** `SpendTrendChart` and `TopModelsChart` (standalone chart components, cards rendered in page.tsx); **NEW** `RecentAlertsWidget` shows last 5 open anomalies with left-border color coding (severity: high=red, medium=amber, low=sky) + "View all alerts" link + EmptyState when clear
- `apps/web/src/app/(dashboard)/dashboard/page.tsx` — **Full redesign**: uses `PageHeader` + `PeriodSelector` in actions slot; fetches anomalies from `/anomalies`; layout is now 3-section: 4-card KPI grid → 2/3+1/3 (trend+donut) → 1/2+1/2 (models+alerts); `EmptyState` component used for no-data state; `shadow-card` / `shadow-card-hover` on all cards

---

## M-P2 Completion Notes

**Completed 2026-05-27.**

Changes shipped:
- `apps/web/src/app/(dashboard)/cost-explorer/export-button.tsx` — **NEW** client component; CSV export of current filtered/grouped data with proper quoting; button disabled when rows=0
- `apps/web/src/app/(dashboard)/cost-explorer/explore-controls.tsx` — **Redesigned**: `SlidersHorizontal` icon prefix; native selects styled with consistent `h-9 rounded-md` height; active dimension filter badges use `X` icon buttons; "Reset filters" button with active count badge only shown when filters are active
- `apps/web/src/app/(dashboard)/cost-explorer/explore-table.tsx` — **Redesigned**: all numeric columns right-aligned (`text-right`); cost/requests/tokens use `text-mono`; lucide sort icons (`ArrowUp`/`ArrowDown`/`ArrowUpDown`) replace text arrows; row hover `hover:bg-muted/40`; grand total footer uses `font-semibold`; table border changed to `rounded-xl border-border/60`; `scrollbar-thin` utility applied
- `apps/web/src/app/(dashboard)/cost-explorer/page.tsx` — **Redesigned**: `PageHeader` with `ExportButton` in actions; `PageMotion` wrapper; summary bar between controls and table (row count + range + grand total); `EmptyState` differentiated between "no data" vs "no filter results"; uses `EmptyState` component properly

---

## M-P3 Completion Notes

**Completed 2026-05-27.**

Changes shipped:
- `apps/web/src/components/integrations-page.tsx` — **Full redesign**: replaced bare-bones form+table with card-based layout; each integration renders as a `rounded-xl border bg-card shadow-card` card with provider avatar, masked key display + copy feedback, `StatusBadge` component, `DropdownMenu` for actions (Force sync, Revoke); "Add Integration" moved to a `Dialog` with shadcn `Select`/`Input`/`Label`; revoke opens `ConfirmDialog`; `EmptyState` used when no integrations; error state shows inline `AlertCircle` + `bg-critical-subtle` message; `PageHeader` replaced with section-level `h2` (settings layout now owns the top-level H1); `PageMotion` wrapper added
- `apps/web/src/app/(dashboard)/settings/integrations/loading.tsx` — **Redesigned**: skeleton now matches the new card layout (provider avatar + title + badge + actions + metrics row)

Design patterns applied:
- Provider cards use `shadow-card` resting / `shadow-card-hover` on hover
- Error cards get `border-critical/30` tint
- Revoked cards use `opacity-60`
- Copy button gives `Check` icon feedback for 1.5s (key never leaves server)
- Destructive revoke always gated by `ConfirmDialog`

---

## M-P4 Completion Notes

**Completed 2026-05-27.**

Changes shipped:
- `apps/web/src/app/(dashboard)/settings/settings-tabs.tsx` — **Full redesign**: horizontal underline tab bar replaced with a **left sidebar nav** (`SettingsSidebar`); two groups — "Connected Services" (API Integrations, Slack) and "Configuration" (Tag Rules) — with 10px uppercase tracking group labels; active state uses animated `bg-primary/10` highlight with `text-primary` icon; old `SettingsTabs` name re-exported as alias for any lingering imports
- `apps/web/src/app/(dashboard)/settings/layout.tsx` — **Updated**: `space-y-6` + horizontal tabs replaced with `PageHeader("Settings")` → `Separator` → flex row (sidebar + vertical divider + `flex-1` content panel); sidebar width `w-52`, vertical `Separator` visible on `lg+`
- `apps/web/src/app/(dashboard)/settings/tags/tags-client.tsx` — **Full redesign**: inline toggle forms replaced with `Dialog`-based Create Tag and Create Rule modals using shadcn `Select`/`Input`/`Label`; delete buttons replaced with `ConfirmDialog` (removes `alert()` calls); `EmptyState` added for both no-tags and no-rules states; tables use `rounded-xl border-border/60 bg-card` with `hover:bg-muted/30 transition-colors`; pattern preview kept inline in Create Rule dialog; `PageHeader` / `Badge` unused imports removed
- `apps/web/src/app/(dashboard)/settings/slack/slack-client.tsx` — **Full redesign**: inline heading replaced with section `h2`; Slack connected state becomes card with `StatusBadge`, workspace metadata, reconnect/disconnect buttons with `ConfirmDialog` on disconnect; mute toggle upgraded to shadcn `Switch` component; empty/not-connected state uses proper card + icon layout; feature list upgraded to icon-card rows with `Check` icons; `bg-success-subtle` / `bg-critical-subtle` flash messages with icons

Design patterns applied:
- Settings layout owns the top-level H1 (`PageHeader`); sub-pages use `h2` section headers
- All Create actions use Dialog modals (not inline toggle forms) for cleaner UX
- All Delete/Disconnect actions require `ConfirmDialog` — no `alert()` calls
- `EmptyState` component used consistently in all zero-data states
- shadcn `Switch` used for the Slack mute toggle (replaces custom Tailwind button)

---

## M-P5 Completion Notes

**Completed 2026-05-27.**

Changes shipped:
- `apps/web/src/app/(dashboard)/anomalies/anomalies-client.tsx` — **Full redesign**: replaced dense table with alert card list; each card has a 4px left color strip (amber for low/medium severity, red for high/critical); `StatusBadge` component used for severity (warning/critical); relative timestamps ("2h ago") with absolute datetime in `Tooltip` on hover; `PageHeader` with "Acknowledge all" button (only shown when open alerts exist); critical summary banner (`bg-critical-subtle`) shown when high-severity alerts are present; severity filter dropdown (All / Low / Medium / Critical) using shadcn `Select`; individual "Acknowledge" + "Dismiss" ghost buttons per card; "View in Cost Explorer" link on every card; `EmptyState` shared component used with context-aware messages (check-circle icon for "all clear" open state); error banner for action failures
- `apps/web/src/app/(dashboard)/anomalies/page.tsx` — **Updated**: removed inline h1/p header (now owned by client component); passes `initialAnomalies` + `status` to client
- `apps/web/src/app/(dashboard)/anomalies/loading.tsx` — **Redesigned**: replaced table skeleton with 4 card-shaped skeletons matching new card layout (strip + header row + title + description + link)

Design patterns applied:
- `shadow-card` / `shadow-card-hover` on alert cards
- Left strip: `bg-warning` (amber-500) for low/medium, `bg-critical` (red) for high
- `border-critical/30 bg-critical-subtle` for the critical summary banner
- "Acknowledge all" uses `Promise.all` for parallel API calls
- Severity filter is client-side (no server re-fetch); status tabs navigate via URL for server re-fetch
- Empty states: `CheckCircle2` icon for "all clear" (open + no alerts), `Bell` icon for acked/dismissed

---

## M-P6 Completion Notes

**Completed 2026-05-27.**

Changes shipped:
- `apps/web/src/app/(dashboard)/recommendations/recommendations-client.tsx` — **Full redesign**: introduced **effort badge** (Easy/Medium/Hard derived from recommendation type: model_swap=Easy green, caching/batch=Medium amber, other=Hard gray); savings amount promoted to dominant visual (`text-2xl font-bold text-success text-mono`); new two-column card layout (left column: badges + savings/resolved state; right column: title + description; footer: confidence bar + action buttons); `PageHeader` added; summary bar shows total estimated savings in `text-success text-mono` when on "new" tab with data; `StaggerGrid` + `StaggerItem` entrance animation for card list; `EmptyState` shared component used with status-aware messages and CTA to `/cost-explorer` when no new recommendations; `RecommendationsLoading` skeleton updated to match new 2-column card layout; applied/dismissed states show check/X icon with date instead of large savings number
- `apps/web/src/app/(dashboard)/recommendations/page.tsx` — **Updated**: removed inline h1/p header (now owned by client component); delegates to `RecommendationsClient`
- `apps/web/src/app/(dashboard)/recommendations/loading.tsx` — **No change required**: already delegates to `RecommendationsLoading` exported from client

Design patterns applied:
- Effort badge before TypeBadge — signals implementation effort at a glance
- `text-2xl font-bold text-success text-mono` for savings — visually dominant per spec
- Footer `border-t border-border/60` separates confidence + actions from card content
- `StaggerGrid` wraps the card list for staggered entrance animation (0.07s delay per item)
- Optimistic removal on apply/dismiss with full `initialRecs` revert on API error
- `CircleDollarSign` icon for applied/dismissed empty states, `Lightbulb` for new

---

## Milestone Roadmap

```
M-DS  Design System Foundation         ← Do first; everything else depends on this
 └── M-CL  Component Library           ← Shared UI components all pages use
      ├── M-P1  Dashboard              ← Highest visibility; ship early
      ├── M-P2  Cost Explorer          ← Core workflow
      ├── M-P3  API Key Management     ← Frequently used
      ├── M-P4  Settings               ← High-traffic config
      ├── M-P5  Alerts & Anomalies     ← Time-sensitive content
      ├── M-P6  Recommendations        ← Decision-support content
      ├── M-P7  Budgets                ← Financial controls
      └── M-QA  Polish & QA            ← Cross-cutting finish pass
```

---

---

## M-DS: Design System Foundation

**Purpose:** Establish the single source of truth for all visual tokens before any page work begins. Every subsequent milestone pulls from this system.

### Objectives
- Define a complete, named color palette with exact hex/HSL values
- Codify typography scale, line-heights, and weight assignments
- Lock spacing scale based on 8px grid
- Define border-radius, shadow, and transition standards
- Validate tokens across light and dark modes

### Deliverables

#### 1. Color Palette (update `globals.css` + `tailwind.config.ts`)

**Light mode tokens to define or verify:**

| Token | Role | Current | Target |
|-------|------|---------|--------|
| `--background` | Page bg | `210 20% 98%` | Keep (near-white) |
| `--card` | Card surface | white | Keep |
| `--primary` | CTA, links | `221 83% 53%` (blue-600) | Keep |
| `--success` | Positive, savings | `142 71% 45%` (emerald-600) | Keep |
| `--warning` | Budget alerts | `38 92% 50%` (amber-500) | Keep |
| `--destructive` | Errors, overages | red-family | Verify sufficient contrast |
| `--muted` | Secondary bg, hover | `214 32% 91%` | Keep |
| `--border` | Dividers, card borders | light gray | Verify — must be subtle, not heavy |
| `--foreground` | Primary text | near-black | Must be ≥ 4.5:1 contrast on `--background` |
| `--muted-foreground` | Secondary text | dark gray | Must be ≥ 3:1 on card |

**New semantic tokens to add:**
```css
--info: <blue-100 tint>;         /* for informational badges */
--info-foreground: <blue-700>;
--success-subtle: <emerald-50>;  /* success badge background */
--warning-subtle: <amber-50>;    /* warning badge background */
--critical-subtle: <red-50>;     /* critical alert background */
```

**Max 5–6 active colors at any one time.** Never introduce new hues; extend existing palette only.

#### 2. Typography (verify in `globals.css` + layout)

| Level | Element | Weight | Size | Line Height | Usage |
|-------|---------|--------|------|-------------|-------|
| H1 | Page title | 700 | 30px (1.875rem) | 1.3 | Dashboard hero numbers |
| H2 | Section title | 600 | 22px (1.375rem) | 1.35 | Card/section headers |
| H3 | Sub-section | 600 | 18px (1.125rem) | 1.4 | Card sub-headers |
| Body | Default text | 400 | 14–15px | 1.6 | All reading text |
| Small | Labels, meta | 400–500 | 12px | 1.5 | Helper text, timestamps |
| Mono | Data values | 400 | Match body | 1.5 | $ amounts, API keys, IDs |

**Action:** Add utility class `.text-mono` → `font-mono tabular-nums` in `globals.css`.
**Action:** Confirm Inter is loaded via `next/font` (already done) and no system-font fallbacks sneak in.

#### 3. Spacing Scale (8px grid)

All spacing should use Tailwind's default scale (already 4px base × 2 = 8px step pattern). Define named conventions:

| Name | Value | Tailwind | Usage |
|------|-------|----------|-------|
| micro | 4px | `gap-1` | Inline label gaps, icon-text pairs |
| small | 8px | `gap-2` | Tight element groups |
| default | 16px | `gap-4` | Default between elements |
| medium | 24px | `gap-6` | Card internal padding, form fields |
| section | 32px | `gap-8` | Between dashboard sections |
| page | 40px | `px-10` | Page horizontal padding (desktop) |

**Card padding rule:** `p-6` (24px) always.
**Page padding rule:** `px-6 lg:px-10` (responsive).

#### 4. Border Radius, Shadows, Transitions

| Property | Value | Token |
|----------|-------|-------|
| Card radius | `0.625rem` (10px) | `rounded-xl` |
| Button radius | `0.5rem` (8px) | `rounded-lg` |
| Input radius | `0.375rem` (6px) | `rounded-md` |
| Badge radius | `9999px` | `rounded-full` |
| Card shadow | `0 1px 3px rgba(0,0,0,0.07)` | `shadow-sm` |
| Hover shadow | `0 4px 12px rgba(0,0,0,0.1)` | `shadow-md` |
| Transition | `150ms ease-in-out` | Tailwind `transition-colors duration-150` |
| Focus ring | `2px offset, primary color` | `focus-visible:ring-2 focus-visible:ring-primary` |

**Constraint:** No `rounded-2xl` or larger on cards (per brief: >8px looks juvenile for financial software).

#### 5. Files to Modify

- `apps/web/src/app/globals.css` — add new semantic tokens, `.text-mono` utility
- `apps/web/tailwind.config.ts` — verify/add new color mappings, add `fontFamily.mono` entry
- `apps/web/components.json` — no change required (already CSS variables mode)

### Success Criteria
- [ ] Color palette documented with all hex/HSL values
- [ ] All semantic tokens named and consistent in light + dark mode
- [ ] Typography scale applied and verified in browser
- [ ] Spacing conventions written and followed
- [ ] Border radius, shadow, and transition values standardized

---

---

## M-CL: Component Library

**Purpose:** Build or update every shared UI primitive so all pages pull from one consistent source. No page-level styling divergence.

### Objectives
- Install missing shadcn components required by pages
- Standardize existing 6 components to the new design tokens
- Build shared composite components: StatusBadge, EmptyState, ErrorState, ConfirmDialog, PageHeader
- Verify all interactive states: hover, focus, disabled, loading

### Deliverables

#### 1. Install Missing shadcn Components

Run these installs before page work begins:

```bash
# From apps/web
npx shadcn-ui@latest add badge
npx shadcn-ui@latest add alert
npx shadcn-ui@latest add tooltip
npx shadcn-ui@latest add tabs
npx shadcn-ui@latest add separator
npx shadcn-ui@latest add toast
npx shadcn-ui@latest add dropdown-menu
npx shadcn-ui@latest add avatar
npx shadcn-ui@latest add switch
npx shadcn-ui@latest add textarea
npx shadcn-ui@latest add progress
npx shadcn-ui@latest add popover
npx shadcn-ui@latest add calendar
```

#### 2. Update Existing Components

**`components/ui/button.tsx`**
- Verify `rounded-lg` (not xl) on all variants
- Ensure height `h-10` (40px) on all size variants
- Confirm `transition-colors duration-150` on all variants
- Add `cursor-not-allowed opacity-50` for disabled (not just opacity)
- Add `gap-2` between icon and text when both present

**`components/ui/input.tsx`**
- Height: `h-10` consistent with buttons
- Focus state: `focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1`
- Border: `border-input` token (not hardcoded gray)
- Placeholder: `placeholder:text-muted-foreground`

**`components/ui/select.tsx`**
- Same height as input (`h-10`)
- Same focus ring treatment

**`components/ui/skeleton.tsx`**
- Verify uses `bg-muted` (not hardcoded color) so it adapts to dark mode

**`components/ui/dialog.tsx`**
- Max width: `max-w-md` for small dialogs, `max-w-lg` for larger
- Overlay: `bg-black/50 backdrop-blur-sm`
- Content: `rounded-xl p-6` with proper shadow

#### 3. New Shared Components to Build

**`components/ui/status-badge.tsx`**
```
Props: status: 'active' | 'inactive' | 'syncing' | 'error' | 'warning' | 'critical'
Renders: colored pill with icon + text label
Colors: active=success-subtle/success, error=critical-subtle/destructive,
        syncing=info-subtle/info, warning=warning-subtle/warning,
        inactive=muted/muted-foreground
```

**`components/empty-state.tsx`**
```
Props: icon?, title, description, action?: { label, href? | onClick? }
Layout: centered, icon (large, muted), title (H3), description (small, muted), CTA button
Usage: All pages when data arrays are empty — enforced pattern, never blank screen
```

**`components/error-state.tsx`**
```
Props: title?, description?, retry?: () => void
Layout: similar to empty state but with destructive icon color
Shows retry button if onRetry passed
```

**`components/page-header.tsx`**
```
Props: title, description?, actions?: ReactNode
Layout: flex row, title+description left, action buttons right
Spacing: mb-6 below header before content
Used on every page for consistent page-level header
```

**`components/confirm-dialog.tsx`**
```
Props: open, onClose, onConfirm, title, description, confirmLabel?, variant?: 'destructive' | 'default'
Wraps shadcn Dialog
Safer option (Cancel) is the visually prominent button
Destructive confirm styled with destructive color
Used for: key revoke, key delete, member remove, budget delete
```

**`components/data-table-skeleton.tsx`**
```
Props: rows?: number (default 5), columns?: number (default 4)
Renders: table-shaped skeleton with pulsing rows
Used as loading placeholder for all data tables
```

#### 4. Update Navigation (`components/nav-links.tsx`)

- Increase active indicator contrast (not just color — also bold text)
- Ensure hover state on non-active items has subtle bg (`hover:bg-muted`)
- Ensure `cursor-pointer` on all nav items
- Verify `transition-colors duration-150` on hover
- Mobile: confirm hamburger/collapse works if sidebar is responsive

#### 5. Update Layout (`app/(dashboard)/layout.tsx`)

- Sidebar: `w-56` fixed, `bg-card border-r border-border`
- Top header: `h-14 border-b border-border bg-background/95 backdrop-blur`
- Main content: `flex-1 overflow-auto px-6 lg:px-10 py-8`
- Max content width: `max-w-7xl mx-auto`

#### 6. Update Motion Wrapper (`components/motion-wrapper.tsx`)

- Verify `PageMotion` is only applied at route level (not nested sections)
- `StaggerGrid` used only for card grids, NOT for table rows
- No motion on lists with >10 items (enforced via count check or just by convention)

### Component Checklist (verify for every component)
- [ ] Hover state defined and smooth (150–200ms)
- [ ] Focus-visible ring visible and uses primary color
- [ ] Disabled state grayed out with `cursor-not-allowed`
- [ ] Dark mode appearance verified
- [ ] No hardcoded colors (use CSS variable tokens only)
- [ ] Consistent border radius per component type

### Success Criteria
- [ ] All missing shadcn components installed
- [ ] 6 existing components updated to token system
- [ ] 5 new shared components built (StatusBadge, EmptyState, ErrorState, PageHeader, ConfirmDialog)
- [ ] DataTableSkeleton built and usable
- [ ] Navigation hover/active states polished
- [ ] Layout max-width and padding standardized

---

---

## M-P1: Dashboard Redesign

**Priority: CRITICAL**
**Route:** `/dashboard`
**Files:** `app/(dashboard)/dashboard/page.tsx`, `components/dashboard-charts.tsx`

### Objectives
- Non-technical CTO understands total spend and status in <5 seconds
- CFO can screenshot for board presentation
- All critical info above the fold (no scroll for KPIs)
- Color-coded health status at a glance

### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  PageHeader: "Dashboard"   [Period selector: 7d | 30d | MTD]│
├─────────────────────────────────────────────────────────────┤
│  KPI Cards Row (4 cards, full-width grid)                   │
│  [Total Spend] [Budget Status] [Active Anomalies] [YTD Est] │
├─────────────────────────────────────────────────────────────┤
│  [Spend Trend Chart — AreaChart 30d]  [Provider Split Donut]│
│   (2/3 width)                          (1/3 width)          │
├─────────────────────────────────────────────────────────────┤
│  [Top Models BarChart]                [Recent Alerts list]  │
│   (1/2 width)                          (1/2 width)          │
└─────────────────────────────────────────────────────────────┘
```

### Features / Components

**KPI Stat Cards (update `DashboardStatCards`)**
- Number: `text-3xl font-bold font-mono tabular-nums` (largest, boldest)
- Label: `text-sm text-muted-foreground font-medium` (below number)
- Context line: `text-xs text-muted-foreground` (e.g., "Last 30 days")
- Delta badge: ↑↓ % with color (green = improvement, red = increase for cost)
- Card uses `hover:shadow-md transition-shadow` (cards are non-clickable but should feel polished)
- Period selector updates all 4 cards simultaneously

**Period Selector**
- Segmented control (not dropdown): `7d | 30d | MTD | Custom`
- Uses shadcn Tabs component in pill/toggle variant
- Positioned top-right of PageHeader actions slot
- Updates charts and KPI cards via state

**Spend Trend Chart (update `DashboardCharts`)**
- Tremor AreaChart
- Y-axis: formatted as `$0.00` with short suffixes (`$12.4K`)
- X-axis: dates, abbreviated
- Tooltip: show exact value on hover
- Legend: model/provider breakdown (stacked or multi-line)

**Provider Split Donut (update `ProviderDonut`)**
- Recharts PieChart
- Center label: total spend
- Segments: OpenAI/Anthropic/Gemini with correct semantic colors
- Legend below chart with exact amounts

**Recent Alerts Widget (new component)**
- Show last 5 alerts (anomalies + budget warnings)
- Color-coded left border: amber = warning, red = critical
- Each row: alert type, message, timestamp
- "View all alerts →" link at bottom
- Uses `EmptyState` if no alerts

**Information Hierarchy Applied**
- Total spend number: largest text, highest contrast (`text-3xl font-bold`)
- Supporting labels: `text-sm text-muted-foreground`
- Timestamps and meta: `text-xs text-muted-foreground`
- Trend indicators: `text-sm font-medium` with semantic color

### States

| State | Implementation |
|-------|---------------|
| Loading | Skeleton cards (4 card-shaped), chart skeleton bars |
| Error | `ErrorState` component with retry button |
| No data | `EmptyState` with "Connect your first API key" CTA |
| Partial data | Show what exists, gray out unavailable metrics |

### Success Criteria
- [ ] KPI cards render above the fold on 1280px viewport
- [ ] Period selector changes data in all widgets
- [ ] All numbers use monospace tabular-nums
- [ ] Delta badges color-coded correctly (cost increase = red, decrease = green)
- [ ] Loading skeleton matches final card shapes
- [ ] Empty state has clear CTA to add API key

---

---

## M-P2: Cost Explorer Redesign

**Priority: HIGH**
**Route:** `/cost-explorer`
**Files:** `app/(dashboard)/cost-explorer/page.tsx`, `explore-controls.tsx`, `explore-table.tsx`

### Objectives
- Analysts can pivot/filter spend data intuitively
- Numbers scannable (right-aligned, monospace)
- Multi-dimension grouping works clearly
- Export to CSV accessible

### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  PageHeader: "Cost Explorer"              [Export CSV btn]  │
├─────────────────────────────────────────────────────────────┤
│  Filter Bar (horizontal, collapsible):                      │
│  [Group by: dropdown] [Date range picker] [Cost ≥: input]  │
│  [Provider filter] [Model filter] [Reset filters link]      │
├─────────────────────────────────────────────────────────────┤
│  Summary row: "Showing X rows · Total: $XX,XXX"             │
├─────────────────────────────────────────────────────────────┤
│  TanStack Data Table:                                       │
│  Dimension | Cost | % of Total | vs. Prev Period | Tokens  │
│  (sortable columns, row hover, number right-align)          │
├─────────────────────────────────────────────────────────────┤
│  Footer: Grand Total row (sticky bottom of table)           │
└─────────────────────────────────────────────────────────────┘
```

### Features / Components

**Filter Bar (update `ExploreControls`)**
- Single horizontal row on desktop, stack on mobile
- "Group by" multi-select dropdown (model, provider, customer, team, feature)
- Date range: shadcn Popover + Calendar or simple preset buttons (7d/30d/MTD)
- Cost floor input: `$` prefix, numeric input
- Provider multi-select checkboxes in dropdown
- Reset button: clears all filters, styled as tertiary/text button
- Filter count badge: shows number of active filters ("3 filters active")

**Data Table (update `ExploreTable`)**
- Columns: Dimension Name · Total Cost · % of Total · Period-over-Period · Token Count · Avg Cost/1K tokens
- Number alignment: **all numbers right-aligned** (`text-right`)
- Font: cost and token values use `font-mono tabular-nums`
- Column headers: sortable (click to toggle asc/desc, show sort icon)
- Row hover: `hover:bg-muted/50 transition-colors`
- Alternating rows: optional `even:bg-muted/20` (subtle striping)
- Grand total: sticky footer row, bold, slightly elevated bg
- Trend indicator: `↑ 12%` in small colored text next to cost

**Summary Bar**
- Between filter bar and table
- `text-sm text-muted-foreground`
- "Showing 24 rows · Total spend: $42,830 · Period: Jun 1–30"

**Export Button**
- Secondary button in PageHeader actions
- `lucide-react Download` icon + "Export CSV"
- Triggers CSV download of current filtered/grouped view

**Drill-Down**
- Click row → slide-in panel (shadcn Sheet or route to filtered dashboard view)
- V1: filter dashboard by that dimension value
- Shows sub-breakdown of clicked dimension

### Column Spec

| Column | Alignment | Format | Notes |
|--------|-----------|--------|-------|
| Dimension | Left | Plain text, bold | Model name / provider / tag |
| Total Cost | Right | `$X,XXX.XX` mono | Primary cost column |
| % of Total | Right | `XX.X%` | Visual bar optional |
| vs. Prior | Right | `↑ XX%` colored | Period comparison |
| Tokens | Right | `X.XM` abbreviated | Token count |
| Avg/1K | Right | `$X.XXXX` mono | 4 decimal places for sub-cent |

### States

| State | Implementation |
|-------|---------------|
| Loading | `DataTableSkeleton` (5 rows × 6 cols) |
| Empty filters | `EmptyState` "No results match your filters" + Reset button |
| No data at all | `EmptyState` "No cost data yet" + Connect API key CTA |
| Error | `ErrorState` with retry |

### Success Criteria
- [ ] Filter bar resets cleanly with one click
- [ ] All numeric columns right-aligned with monospace font
- [ ] Sort works on all columns
- [ ] Grand total row always visible at table bottom
- [ ] CSV export downloads correct data
- [ ] Mobile: table scrolls horizontally, filter bar stacks vertically

---

---

## M-P3: API Key Management Redesign

**Priority: HIGH**
**Route:** `/settings/integrations`
**Files:** `app/(dashboard)/settings/integrations/page.tsx`, `components/integrations-page.tsx`

### Objectives
- Status of every key visible at a glance
- Masked key display with copy button
- Last sync timestamp shows data freshness
- Destructive actions require confirmation

### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  PageHeader: "API Integrations"       [+ Add Integration]   │
├─────────────────────────────────────────────────────────────┤
│  Provider Section: OpenAI                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ [Provider Logo]  sk-proj-••••••••••••••••Xk9a          │ │
│  │ [Status Badge: Active ●]   Last synced: 2 min ago      │ │
│  │ ─────────────────────────────────────────────────────  │ │
│  │ $8,420/mo   1.2M calls   Rate: 72%            [···]   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Provider Section: Anthropic                                │
│  [Similar card layout]                                      │
│                                                             │
│  + Add another key (inline button at bottom)               │
└─────────────────────────────────────────────────────────────┘
```

### Features / Components

**Integration Card**
- Card layout: `rounded-xl border bg-card p-6`
- Header row: provider logo (20px) + masked key + status badge + copy icon
- Key masking: `sk-proj-` + `••••••••••••` + last 4 chars (e.g., `Xk9a`)
- Copy button: `lucide-react Copy` (16px), click copies full key from server, show `Check` for 1.5s
- Status badge: uses `StatusBadge` component (active/error/syncing/inactive)
- Last sync: `text-xs text-muted-foreground` — "Synced 2 minutes ago"
- Divider: `<Separator>` between header and metrics

**Inline Metrics Row**
- Monthly spend, API call count, rate limit %
- Values: `font-mono` for numbers
- Rate limit: color-coded — green <50%, amber 50–80%, red >80%
- `text-sm` labels, `text-base font-semibold` values

**Action Menu (3-dot `...` Dropdown)**
- `lucide-react MoreHorizontal` button → `DropdownMenu`
- Items: View Details · Edit · Force Sync · Rotate Key · Disable · Revoke
- Dangerous items (Disable, Revoke) use `text-destructive`
- Revoke opens `ConfirmDialog` before executing

**Add Integration Button / Flow**
- Primary button: `+ Add Integration` in PageHeader
- Opens `Dialog` with form: Provider select → API key input → Test & Save
- Test connection call shows spinner + success/error feedback
- On success: new card animates in via `SlideIn` from `motion-wrapper.tsx`

**Disabled Key State**
- Card: `opacity-60`
- Status badge: gray "Disabled"
- Actions: Re-enable option prominent in dropdown

**Error Key State**
- Card: subtle red border `border-destructive/30`
- Status badge: red "Error"
- Error message inline: "Authentication failed — check key permissions"
- Action: "Reconnect" primary action (not just in dropdown)

### States

| State | Implementation |
|-------|---------------|
| No keys added | `EmptyState` with prominent "Add your first integration" CTA + provider logos |
| Syncing | StatusBadge shows "Syncing" with spinner icon |
| Sync error | Error badge + inline error message + Reconnect CTA |
| Loading page | 2–3 card-shaped skeletons |

### Success Criteria
- [ ] Key masked correctly (first 8 chars + dots + last 4)
- [ ] Copy button works and shows confirmation tick
- [ ] Status badge immediately obvious (color + icon + text, not color alone)
- [ ] Destructive actions require `ConfirmDialog`
- [ ] Empty state has clear CTA with provider logos for familiarity
- [ ] Rate limit percentage color-codes at 50% and 80% thresholds

---

---

## M-P4: Settings Redesign

**Priority: MEDIUM**
**Routes:** `/settings`, `/settings/slack`, `/settings/tags`
**Files:** `settings/page.tsx`, `settings/settings-tabs.tsx`, `settings/layout.tsx`

### Objectives
- Clear section navigation (sidebar pattern)
- Forms follow consistent conventions
- Dangerous actions require confirmation
- Each section loads independently

### Layout Structure

```
┌──────────────────────────────────────────────────────────────┐
│  PageHeader: "Settings"                                      │
├─────────────────┬────────────────────────────────────────────┤
│  Left Sidebar   │  Right Content Panel                       │
│  (200px fixed)  │  (flex-1)                                  │
│                 │                                            │
│  Organization   │  [Section Title]                           │
│  Team Members   │  [Description text]                        │
│  Billing        │                                            │
│  Notifications  │  [Form fields / content]                   │
│  > Integrations │                                            │
│  > Slack        │  [Save] [Cancel]                          │
│  > Tags         │                                            │
│  Security       │                                            │
└─────────────────┴────────────────────────────────────────────┘
```

### Features / Components

**Settings Sidebar**
- Vertical nav list using same pattern as main sidebar
- Current section: `bg-muted text-foreground font-medium`
- Non-active: `text-muted-foreground hover:bg-muted hover:text-foreground`
- Group labels: `text-xs font-semibold uppercase tracking-wider text-muted-foreground` (like "Integrations")
- Integrations, Slack, Tags listed as sub-items with indentation

**Organization Section**
- Fields: Org name, Contact email, Timezone
- Save button: primary, bottom of form
- Changes saved via API call + toast notification on success/error

**Team Members Section**
- Table: Name · Email · Role · Joined date · Actions
- Invite member: form in-page (not modal) — email input + role select + Send Invite
- Role dropdown: Admin, Member, Viewer
- Remove member: `ConfirmDialog`
- Pending invites shown in separate subsection

**Billing Section**
- Current plan: plan name + price + renewal date
- Usage meter: current API calls vs. limit (shadcn Progress component)
- Payment method: last 4 digits + card brand + update button
- Upgrade/downgrade: button opens Stripe hosted billing or modal

**Notifications Section**
- Email alerts: toggle switches per alert type (Budget warning, Anomaly, Weekly report)
- Slack: status of Slack integration + connect/disconnect
- Alert thresholds: budget % warning threshold (input)

**Tag Rules Section (`/settings/tags`)**
- Table of rules: Pattern · Tag · Created · Actions
- Add rule: form with regex pattern input + tag name
- Delete rule: ConfirmDialog

**Slack Section (`/settings/slack`)**
- Connection status card (StatusBadge)
- Channel selector (after OAuth)
- Notification type toggles
- Disconnect button (with ConfirmDialog)

### Form Conventions (applied everywhere in Settings)
- Label above input (never placeholder-only)
- `h-10` inputs, `rounded-md`
- Error messages: `text-sm text-destructive` below the field
- Save row: `flex items-center gap-3 justify-end` at form bottom
- Cancel button: secondary/ghost, no destructive color

### States

| State | Implementation |
|-------|---------------|
| Form saving | Button shows spinner + "Saving…" disabled state |
| Save success | Toast: "Settings saved" (success color) |
| Save error | Toast: "Failed to save — try again" (error color) |
| Loading section | Skeleton form fields |

### Success Criteria
- [ ] Sidebar clearly shows current section (active state)
- [ ] All forms: label above input, consistent height
- [ ] Cancel never triggers any action
- [ ] Dangerous actions (remove member, disconnect) use ConfirmDialog
- [ ] Toast notifications appear for save/error
- [ ] Billing section shows plan and usage clearly

---

---

## M-P5: Alerts & Anomalies Redesign

**Priority: MEDIUM**
**Route:** `/anomalies`
**Files:** `app/(dashboard)/anomalies/page.tsx`, `anomalies-client.tsx`

### Objectives
- Severity immediately obvious via color + icon
- Most recent alerts first
- Acknowledge/dismiss workflow clear
- Link back to related data (cost explorer, budget)

### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  PageHeader: "Alerts & Anomalies"     [Filter: All | Unack] │
├─────────────────────────────────────────────────────────────┤
│  Filter row: [Type: All/Budget/Anomaly/Rate] [Severity: All]│
├─────────────────────────────────────────────────────────────┤
│  Alert List (most recent first):                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ [●] Budget Warning                    2 hours ago [✓] │ │
│  │     OpenAI spend reached 80% of $10,000 monthly budget │ │
│  │     [View in Cost Explorer →]                          │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ [●] Anomaly — Cost Spike             Yesterday  [✓]   │ │
│  │     gpt-4o spend ↑ 340% vs. 7-day avg ($847 vs $249)  │ │
│  │     [View Details →]                                   │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Features / Components

**Alert Card**
- Left color strip: `4px wide, rounded-l-xl` — amber (warning) or red (critical)
- Severity indicator: colored dot + `StatusBadge` (Warning / Critical)
- Title: `font-semibold text-base`
- Description: `text-sm text-muted-foreground` — detail of what happened
- Timestamp: `text-xs text-muted-foreground` — relative time ("2 hours ago")
- Acknowledge button: `Check` icon, tertiary style — marks alert as read
- Link: "View in Cost Explorer" or "View Details" — `text-primary text-sm font-medium`
- Acknowledged state: card `opacity-60`, icon changes to filled check

**Filter Controls**
- Alert type: segmented control or button group (All / Budget / Anomaly / Rate Limit)
- Severity: dropdown (All / Warning / Critical)
- Status: toggle "Show acknowledged" (off by default)
- Compact, above the list

**Bulk Actions**
- "Acknowledge all" button when unacknowledged alerts exist
- Secondary button style, top-right of list

**Alert Summary Banner** (if >0 critical alerts)
- Top of page, above filter row
- Red background `bg-critical-subtle border border-destructive/30`
- "X critical alerts need attention"
- Only shows when there are critical unacknowledged items

### States

| State | Implementation |
|-------|---------------|
| No alerts | `EmptyState` with check-circle icon: "All clear — no alerts" |
| All acknowledged | `EmptyState` with success tone: "Nothing outstanding" |
| Loading | 3–4 card-shaped skeletons |
| Error loading | `ErrorState` with retry |

### Success Criteria
- [ ] Color + icon + text conveys severity (not color alone)
- [ ] Timestamps are relative ("2 hours ago") with absolute on hover tooltip
- [ ] Acknowledge marks as read without page reload
- [ ] Critical summary banner visible at top when critical alerts exist
- [ ] Empty state shows positive "all clear" message (not just blank)

---

---

## M-P6: Recommendations Redesign

**Priority: MEDIUM**
**Route:** `/recommendations`
**Files:** `app/(dashboard)/recommendations/page.tsx`, `recommendations-client.tsx`

### Objectives
- Savings amount is the first thing users notice
- Effort level is clear (easy/medium/hard)
- Applied/dismissed tracking functional
- No dark patterns — easy to dismiss

### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  PageHeader: "Recommendations"   [Filter: Effort | Status]  │
├─────────────────────────────────────────────────────────────┤
│  Summary bar: "X recommendations · Est. $X,XXX/mo savings" │
├─────────────────────────────────────────────────────────────┤
│  Recommendation Cards (stacked, full-width):                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ [Effort: Easy]  Switch gpt-4o → gpt-4o-mini for...    │ │
│  │                                                        │ │
│  │ Save $1,240/mo  Current: gpt-4o ($0.03/1K) →          │ │
│  │                 Proposed: gpt-4o-mini ($0.002/1K)      │ │
│  │                                                        │ │
│  │ [Apply →] [Learn More] [Dismiss]                      │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Features / Components

**Recommendation Card**
- Effort badge: top-left — `Easy` (green), `Medium` (amber), `Hard` (gray/blue)
- Savings: `text-2xl font-bold text-success` — the biggest text on the card
- "Save $X/mo" label below in `text-sm text-muted-foreground`
- Title: `text-base font-semibold`
- Description: current state → proposed change, `text-sm`
- Action row: `[Apply →]` (primary) · `[Learn More]` (secondary) · `[Dismiss]` (ghost/text)
- Applied state: gray card, "Applied ✓" badge, no action buttons
- Dismissed state: hidden (or shown in "Show dismissed" toggle)

**Summary Bar**
- Shows total potential savings across visible recommendations
- `text-success font-semibold` for the savings number
- Filters: effort level (Easy/Medium/Hard) + status (Active/Applied/Dismissed)

**Filter Controls**
- Effort multi-select pills: filter cards by difficulty
- Status toggle: show applied and dismissed (collapsed by default)

**Empty State**
- If no recommendations: `EmptyState` with lightbulb icon — "No recommendations right now. Check back after more data is collected."

### States

| State | Implementation |
|-------|---------------|
| No recommendations | `EmptyState` with lightbulb icon |
| All applied/dismissed | `EmptyState` "All caught up!" with option to reset dismissed |
| Loading | 2–3 card-shaped skeletons |
| Applying | Button spinner, card dims |

### Success Criteria
- [ ] Savings amount is visually dominant on each card
- [ ] Effort level clear via badge (Easy/Medium/Hard with color)
- [ ] Dismiss is easy to find but not destructively styled
- [ ] Applied recommendations clearly marked (not just removed)
- [ ] Summary bar shows total potential savings

---

---

## M-P7: Budgets Redesign

**Priority: MEDIUM**
**Route:** `/budgets`
**Files:** `app/(dashboard)/budgets/page.tsx`, `budgets-client.tsx`

### Objectives
- Budget utilization visible at a glance
- Danger zone (>80%) immediately obvious
- Create/edit budget form is clear
- Alert thresholds configurable inline

### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  PageHeader: "Budgets"                     [+ New Budget]   │
├─────────────────────────────────────────────────────────────┤
│  Budget Cards (grid: 2 cols desktop, 1 col mobile):         │
│  ┌─────────────────────┐  ┌─────────────────────┐          │
│  │ OpenAI Monthly       │  │ All Providers — Dev  │          │
│  │ $7,823 / $10,000     │  │ $2,100 / $3,000      │          │
│  │ ████████░░ 78%       │  │ ██████████ 70%       │          │
│  │ [●] On Track         │  │ [●] Caution          │          │
│  │ $2,177 remaining     │  │ $900 remaining       │          │
│  │ 8 days left in month │  │ 8 days left          │          │
│  │ [Edit] [Delete]     │  │ [Edit] [Delete]     │          │
│  └─────────────────────┘  └─────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### Features / Components

**Budget Card**
- Budget name: `text-base font-semibold`
- Spend vs. limit: `font-mono` — "$7,823 / $10,000"
- Progress bar: shadcn `Progress` component
  - Color: green <50%, amber 50–80%, red >80%
  - Percentage label right-aligned: `text-sm font-medium`
- Status badge: On Track / Caution / Over Budget
- Remaining + days left: `text-sm text-muted-foreground`
- Edit button: ghost/secondary in card footer
- Delete: ConfirmDialog

**Create / Edit Budget Dialog**
- Fields: Budget name · Provider/Tag scope · Monthly limit ($) · Warning threshold (%) · Alert channels (email/Slack)
- Validation: limit must be positive, threshold 1–99%
- Save triggers toast on success

**No Budgets State**
- `EmptyState` with wallet icon — "No budgets yet. Set spending limits to stay in control."
- CTA: "Create first budget"

### Success Criteria
- [ ] Progress bar color changes at 50% and 80% thresholds
- [ ] Over-budget state uses red with strong visual emphasis
- [ ] Days remaining shows urgency near month-end
- [ ] ConfirmDialog on delete
- [ ] Create/edit form validates before save

---

---

## M-QA: Polish & QA Pass

**Priority: Must-complete before marking redesign done**
**Scope:** All pages cross-cutting

### Objectives
- Every interactive element has correct hover state
- Every page has loading, error, and empty states
- Responsive behavior verified at 3 breakpoints
- No alignment or spacing inconsistencies
- Accessibility baseline met

### Deliverables

#### 1. Interactive State Audit (all pages)

Go through every interactive element and verify:

| Element | Hover | Focus | Disabled | Transition |
|---------|-------|-------|----------|------------|
| Primary button | Darker bg | Ring visible | Grayed, cursor-not-allowed | 150ms |
| Secondary button | Filled bg | Ring visible | Same | 150ms |
| Ghost/text button | Light bg | Ring visible | Same | 150ms |
| Form inputs | Border highlight | Ring + border | Muted bg | 150ms |
| Table rows | `bg-muted/50` | — | — | 150ms |
| Nav items | `bg-muted` | Ring | — | 150ms |
| Cards (interactive) | `shadow-md` | — | — | 200ms |
| Dropdown items | `bg-muted` | Ring | — | 100ms |

#### 2. Empty State Audit

Every page must have an empty state. Verify:

| Page | Empty State Message | CTA |
|------|---------------------|-----|
| Dashboard | "Connect your first API key to see spend data" | Link to integrations |
| Cost Explorer | "No data matches your filters" | Reset filters |
| Integrations | "No API keys connected" | Add integration button |
| Anomalies | "All clear — no alerts" | None (positive state) |
| Recommendations | "No recommendations yet" | Informational |
| Budgets | "No budgets set" | Create budget |

#### 3. Loading Skeleton Audit

Every data-dependent section must show skeletons (not spinner). Verify:

| Page | Skeleton |
|------|---------|
| Dashboard KPI cards | 4 card-shaped skeletons |
| Dashboard charts | Chart-area rectangles |
| Cost Explorer table | `DataTableSkeleton` (5 rows) |
| Integrations | 2–3 card skeletons |
| Anomalies | 3–4 row skeletons |
| Recommendations | 2 card skeletons |
| Budgets | 2 card skeletons |

#### 4. Responsive Breakpoints

Test at these widths:

| Breakpoint | Target | Layout Changes |
|------------|--------|----------------|
| 1280px+ | Primary desktop | Full layout, all columns |
| 1024px | Laptop | Sidebar may collapse or narrow |
| 768px | Tablet | Sidebar hidden (hamburger), 1-col cards |
| 375px | Mobile | Stacked, full-width, tables scroll horizontally |

Mobile-critical pages: Dashboard, Integrations, Alerts.
Lower priority for mobile: Cost Explorer (pivot tables inherently require width).

#### 5. Accessibility Checklist

- [ ] All images and icons have `aria-label` or `alt` text
- [ ] Color is never the sole indicator of meaning (always paired with icon or text)
- [ ] All form inputs have associated `<label>` (via shadcn Label + `htmlFor`)
- [ ] Keyboard navigation reaches all interactive elements
- [ ] Focus indicator always visible (`focus-visible` not `focus`)
- [ ] Contrast ratio: body text ≥ 4.5:1, large text ≥ 3:1
- [ ] Tooltips accessible via keyboard (`aria-describedby`)
- [ ] Modal traps focus when open, restores on close
- [ ] Destructive confirm dialogs: Cancel is keyboard-default

#### 6. Visual Consistency Final Check

- [ ] All primary buttons identical (color, height, radius)
- [ ] All form inputs identical (height, border, focus ring)
- [ ] All cards identical (bg, border, padding, radius)
- [ ] All status badges use `StatusBadge` component
- [ ] All page headers use `PageHeader` component
- [ ] All empty states use `EmptyState` component
- [ ] All error states use `ErrorState` component
- [ ] All confirm dialogs use `ConfirmDialog` component
- [ ] Icon sizes consistent (16px inline, 20px labels, 24px section)
- [ ] Spacing follows 8px grid (no arbitrary px values)

#### 7. Dark Mode Verification

- [ ] All pages look professional in dark mode
- [ ] No hardcoded `#colors` — only CSS variable tokens
- [ ] Charts readable in dark mode (Tremor/Recharts dark adaptation)
- [ ] Status colors readable in both modes
- [ ] Skeleton animations visible in dark mode

### Success Criteria
- [ ] All interactive elements have hover/focus states
- [ ] No page shows a blank screen in any data state
- [ ] Skeletons visible on slow network (Chrome DevTools: Slow 3G test)
- [ ] 768px layout works without horizontal scroll (except tables)
- [ ] WCAG AA contrast on all primary text
- [ ] Dark mode toggle shows no jarring hardcoded colors

---

---

## Implementation Priority Order

Execute milestones in this sequence to maximize shared foundations:

```
Week 1:
  Day 1–2:  M-DS  Design System Foundation
  Day 3–5:  M-CL  Component Library

Week 2:
  Day 1–3:  M-P1  Dashboard (highest visibility)
  Day 4–5:  M-P2  Cost Explorer

Week 3:
  Day 1–2:  M-P3  API Key Management
  Day 3–5:  M-P4  Settings (all sub-pages)

Week 4:
  Day 1–2:  M-P5  Alerts & Anomalies
  Day 3:    M-P6  Recommendations
  Day 4:    M-P7  Budgets
  Day 5:    M-QA  Begin polish pass

Week 5:
  Day 1–3:  M-QA  Complete polish, accessibility, responsive
  Day 4–5:  Final visual review + sign-off
```

---

## Success Criteria Summary

```
CLARITY:
  ✅ Non-technical CTO understands spend and status in <5 seconds
  ✅ Data visualization enables quick decision-making
  ✅ No confusion about page purpose or available actions

PROFESSIONALISM:
  ✅ Design quality matches Stripe/Vercel/Vantage
  ✅ CFO would share Dashboard screenshot in board meeting
  ✅ Visual consistency enforced via shared component system

USABILITY:
  ✅ Analysts navigate without help
  ✅ Cost data filterable and pivotable intuitively
  ✅ API key status clear at a glance
  ✅ Forms follow standard conventions throughout

POLISH:
  ✅ Hover states smooth (150–200ms ease-in-out)
  ✅ Skeleton loaders (no spinners) for all data sections
  ✅ Empty states with clear CTAs (never a blank page)
  ✅ Error states with retry actions
  ✅ Confirmation dialogs for all destructive actions
  ✅ No alignment issues or spacing inconsistencies

CREDIBILITY:
  ✅ All numbers: right-aligned, monospace tabular-nums
  ✅ Status indicators: color + icon + text (not color alone)
  ✅ Professional typography hierarchy throughout
  ✅ Generous whitespace (not cramped)
  ✅ Max 5–6 colors used consistently
```

---

## Appendix: File Change Map

| File | Milestone | Change Type |
|------|-----------|-------------|
| `apps/web/src/app/globals.css` | M-DS | Update tokens, add utilities |
| `apps/web/tailwind.config.ts` | M-DS | Add semantic color mappings |
| `apps/web/src/components/ui/button.tsx` | M-CL | Update radius, height, transitions |
| `apps/web/src/components/ui/input.tsx` | M-CL | Standardize height, focus ring |
| `apps/web/src/components/ui/select.tsx` | M-CL | Standardize height |
| `apps/web/src/components/ui/skeleton.tsx` | M-CL | Verify token usage |
| `apps/web/src/components/ui/badge.tsx` | M-CL | New (install shadcn) |
| `apps/web/src/components/ui/status-badge.tsx` | M-CL | New custom component |
| `apps/web/src/components/empty-state.tsx` | M-CL | New shared component |
| `apps/web/src/components/error-state.tsx` | M-CL | New shared component |
| `apps/web/src/components/page-header.tsx` | M-CL | New shared component |
| `apps/web/src/components/confirm-dialog.tsx` | M-CL | New shared component |
| `apps/web/src/components/data-table-skeleton.tsx` | M-CL | New shared component |
| `apps/web/src/components/nav-links.tsx` | M-CL | Hover/active state polish |
| `apps/web/src/app/(dashboard)/layout.tsx` | M-CL | Sidebar, header, max-width |
| `apps/web/src/components/dashboard-charts.tsx` | M-P1 | Full redesign |
| `apps/web/src/app/(dashboard)/dashboard/page.tsx` | M-P1 | Layout + period selector |
| `apps/web/src/app/(dashboard)/cost-explorer/explore-controls.tsx` | M-P2 | Filter bar redesign |
| `apps/web/src/app/(dashboard)/cost-explorer/explore-table.tsx` | M-P2 | Column alignment, total row |
| `apps/web/src/components/integrations-page.tsx` | M-P3 | Full card redesign |
| `apps/web/src/app/(dashboard)/settings/settings-tabs.tsx` | M-P4 | Sidebar nav pattern |
| `apps/web/src/app/(dashboard)/anomalies/anomalies-client.tsx` | M-P5 | Alert card redesign |
| `apps/web/src/app/(dashboard)/recommendations/recommendations-client.tsx` | M-P6 | Card redesign |
| `apps/web/src/app/(dashboard)/budgets/budgets-client.tsx` | M-P7 | Progress bar + status |

---

*Last updated: 2026-05-27 · Version 1.0 · Based on UI/UX Redesign Brief v1.0*
