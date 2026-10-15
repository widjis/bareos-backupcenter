---
version: alpha
colors:
  background: "#F3F6FA"
  surface: "#FFFFFF"
  text: "#172B4D"
  primary: "#2457D6"
  success: "#18794E"
  warning: "#9A6700"
  danger: "#C9372C"
  nav: "#14263F"
  navText: "#D2DDED"
  navMuted: "#A5B7CD"
  navActive: "#263E5E"
typography:
  sans:
    fontFamily: '"IBM Plex Sans", sans-serif'
  mono:
    fontFamily: '"IBM Plex Mono", monospace'
rounded:
  panel: "8px"
  control: "6px"
spacing:
  panel: "20px"
components:
  Panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
  SuccessBadge:
    textColor: "{colors.success}"
  WarningBadge:
    textColor: "{colors.warning}"
  DangerBadge:
    textColor: "{colors.danger}"
  Sidebar:
    backgroundColor: "{colors.nav}"
    textColor: "{colors.navText}"
  SidebarCaption:
    textColor: "{colors.navMuted}"
  SidebarActiveItem:
    backgroundColor: "{colors.navActive}"
---
# Design Context

## Audience and direction

Internal IT operators familiar with Veeam. The concept is a recovery control room focused on machines, required actions, and restoration. The protection timeline is the signature element.

## Proposed tokens

Background #F3F6FA; surface #FFFFFF; text #172B4D; primary #2457D6; success #18794E; warning #9A6700; danger #C9372C.
Use IBM Plex Sans for the UI and IBM Plex Mono for JobIds and logs.
Runtime tokens are implemented centrally in `src/app/globals.css`.

## Layout

A navy navigation rail, a compact environment header, a wide operations area, and dense operational tables. The overview includes protection summaries, required actions, a protection timeline, active sessions, storage, and upcoming schedules. Desktop supports full operations; mobile prioritizes monitoring.

## Behavior

Preserve filters and pagination during navigation. Keep loading layouts stable, provide concrete errors, and show synchronization timestamps for stale data. Pair colors with text or icons. Separate dangerous actions and require explicit restore overwrite choices. Show percentage progress only when the total is known. Target WCAG 2.2 AA for keyboard access, focus, and contrast. Display the timezone explicitly; use WITA when the environment uses Asia/Makassar.

## Status

Monitoring UI implemented in `src/components/backup-center.tsx`. Runtime CSS tokens are defined centrally in `src/app/globals.css`, mapped to the palette and typography below. Browser verification evidence is recorded in the implementation report.

## Approved navigation and workload browsing

Use Overview, Jobs, Backups, Infrastructure, History, and Settings as the primary navigation. Preserve the core palette and protection timeline; the enterprise redesign adds dedicated navy navigation tokens.

Infrastructure has VMware, Backup proxies, and Repositories sections. VMware combines a datacenter/folder tree with a searchable, paginated VM table. Show inventory freshness, protection status, and policy assignment separately. Advanced Bareos Pool, Volume, and FileSet details remain available without leading the normal workflow.

The Add to backup wizard uses these steps: Select VMs -> Policy -> Schedule and repository -> Review -> Apply and track. Preserve explicit selections across filtering and pagination, show a selection summary, and never interpret a page selection as selecting all matching VMs. Existing assignments require a deliberate change workflow.

An unavailable inventory is an error or stale state, not an empty successful result. An unsupported provisioning capability disables Add to backup with an explanation. A configured VM without a successful qualifying backup is labeled Pending first backup rather than Protected.

## Runtime mapping

Each palette role maps directly to its same-named CSS custom property in `src/app/globals.css`; text uses `--text`, body uses `--background`, and panels use `--surface`. Font roles map to `--sans` and `--mono` with locally bundled IBM Plex fonts. Light-only theme; 8px panel radius, 6px controls, flat borders, no decorative shadows. Semantic light backgrounds support badges while icons and labels preserve meaning.

## Enterprise console revision

The operator requested an enterprise-grade redesign. The visual system now separates navigation from operational content with a navy rail and white working surfaces. The overview uses a shared metric strip, side-by-side protection timeline and exceptions, then recent sessions and schedule details. At narrower widths, panels stack without constraining document scrolling. Table overflow remains local to the table.

The four navigation tokens map to `--nav`, `--nav-text`, `--nav-muted`, and `--nav-active`. Panel/control radii and the semantic palette remain unchanged. Utility labels are compact; primary evidence, VM identity, and actionable links have higher emphasis. No decorative charts, invented health scores, or unavailable controls are introduced.

## Inventory, identity and recovery surfaces

VMware uses the approved tree/table layout and the same table/search primitives. Its table owns a bounded 600px/65vh scroll area with a sticky header; sibling proxy/repository panels remain in natural document flow. Explicit selection and the review summary stay separate from backup evidence. Native select/date popups follow the maintained UX decision; application field styling uses the central surface, border and typography tokens. Identity login, account review, recovery inspection and onboarding preview reuse the palette and native modal semantics. Report coverage and unavailable apply/restore gates remain visible in text.


Direct VMware restore destination review extends the existing recovery dialog with the canonical two-column policy-fields layout (one column at narrow widths), auth-field inputs and shared discard confirmation. Preserve current typography/colors; no new visual tokens. Review and execution remain distinct product states.

The direct VMware review variant now has native live destination selectors, a nested confirmation and a per-recovery-point restore-test evidence section. Runtime colors/layout remain unchanged. Execution warnings, isolation proof and OS-boot proof are shown separately; source scope is visible.

Active existing-job policy uses the existing panel, policy-fields grid, auth-field inputs, native selectors/time input and confirmation styling. It appears separately from draft policy metadata. Manual Run level uses the same select owner; no new visual tokens are introduced.
