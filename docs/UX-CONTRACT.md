# UX Contract

The application runs on loopback for one local operator. Fixed read routes provide monitoring; confirmed Run/Cancel dispatch is activated for the six configured VMware jobs. Local authentication and environment-wide roles are implemented. Remote hosting, restore, provisioning and per-resource/multi-site scoping remain outside the accepted release.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Table | DataTable in src/components/table-controls.tsx | This contract | jobs / history / workloads / infrastructure | Browser tests |
| Search | SearchField in src/components/table-controls.tsx | This contract | local snapshot / remote inventory filtering | Browser tests |
| Scrollbar | src/app/globals.css | DESIGN.md | table overflow | Browser tests |
| Navigation | BackupCenter | This contract | view query parameter | Browser tests |
| Feedback | ConnectionBanner | This contract | loading / offline / partial / stale | Browser tests |
| Dialog | Confirmation dialog in BackupCenter | This contract and OPERATIONS.md | run / cancel | operations.spec.ts keyboard + browser |
| Table Selection | VMwareInventory in src/components/vmware-inventory.tsx | INVENTORY.md | explicit UUID selections across server pages | inventory.spec.ts |
| Select/Listbox | NativeSelectField in src/components/form-controls.tsx | This contract | native role / shared-storage choice | auth.spec.ts / onboarding.spec.ts |
| Date | NativeDateField in src/components/form-controls.tsx | This contract | native report period | reports.spec.ts |
| Form | Shared fields and PasswordField in src/components/auth.tsx | This contract | login / account / password / report | auth.spec.ts / reports.spec.ts |
| CRUD | UserSettings and backend/auth.py | AUTHENTICATION.md | confirmed create / access edit; no hard-delete | auth.spec.ts / test_auth.py |



VMware owns explicit UUID-keyed selection; DataTable owns the server-pagination variant. AuthGate/PasswordField/UserSettings own identity forms and masked secrets. Account role selects deliberately use the native OS popup for three fixed choices; custom popup styling is not part of this contract. Native dialog owns confirmations with initial Go back focus and focus restoration. Date pickers and toast are not implemented.

## State and behavior

Committed view, query, and page are stored in the URL. Search filters the bounded snapshot locally; the UI states the retrieved limit. Pagination is client-side over that bounded snapshot, not the complete Catalog. Reset paging when search or view changes. Media table paging is independent and session-local; it resets when the view or query changes. Clear search returns focus to the input.

Keep the last snapshot on refresh failure and label it stale. A failed first load has a retry action. Individual source failure produces a partial snapshot with source-specific errors. Do not infer healthy or protected status from job definitions alone. Only completed backup sessions count as backup evidence; warnings remain distinct. VM names inferred from job configuration are not verified vCenter inventory identities.

Session details use a dedicated drawer with accessible focus handling. Escape and Close restore focus to the opener. Session log errors remain inline. Raw secret-bearing configuration is never returned to the browser.

All dates use explicit Asia/Makassar display conversion from server UTC. English copy and locale are used throughout. WCAG 2.2 AA is the target; automated checks do not establish full conformance.

For existing workloads with no qualifying session in the retrieved Catalog window, show No backup recorded. Do not infer that a first backup has never occurred; Catalog pruning may remove earlier evidence. Pending first backup is reserved for future onboarding with a known creation state.

## Table name sorting

DataTable owns optional first-column sorting through a header button with aria-sort. Sorting compares displayed object/job names using numeric-aware English collation and resets pagination. Sort direction is local to the mounted table; independent tables do not share sorting state. The default preserves the source order, including recent-session ordering. Dates are not sorted by their formatted display strings.

## Persistence state

Settings displays application database state and collector audit history. Audit pagination is independent and session-local. A PostgreSQL failure produces a visible persistence warning without changing live Bareos connectivity into healthy database status. Recovered snapshots retain their original synchronization timestamp and are stale until a live refresh succeeds. Saved session observations are not silently merged into live recovery evidence.

## Confirmed operation behavior

Run now and Cancel session always open the same confirmation primitive with explicit object/consequence copy and Go back as initial focus. Native dialog manages modal focus; Escape and Go back restore the opener. During submission closing is blocked and controls keep stable dimensions. Acceptance closes the confirmation and displays persistent operation feedback. Request state never replaces actual Director job state. Operation table pagination is independent and session-local.

Unknown outcomes are warning states and must never imply successful execution or offer automatic resend. Confirmation retries reuse the same request key. A stale connection, failed journal read, or failed snapshot persistence disables controls. Backend preflight/journal checks remain authoritative. The audit view shows action target/state for operation events and observation counts for collector events.

## Inventory and authentication variants

See [INVENTORY.md](INVENTORY.md) for remote search, URL filters, 25-row server pagination, transient selection, stale/error boundaries and identity associations. See [AUTHENTICATION.md](AUTHENTICATION.md) for form/role/session behavior. apiFetch owns 401 session-expiry feedback; AuthGate removes the authenticated subtree on expiry/logout. Account refresh checks roles every 30 seconds; Viewer role changes close an unsubmitted operation confirmation. Backend checks remain authoritative during this interval.

## Form ownership and native popup decisions

NativeSelectField deliberately uses the OS-owned popup for fixed roles and known storage choices. NativeDateField uses the browser/OS-owned date popup, including its platform locale; product-owned labels, report output and validation remain English/WITA. Popup geometry is not styled as an application-owned calendar/listbox. Shared fields have real labels, unambiguous accessible names, field error associations and first-invalid-field focus. UserSettings owns transient sensitive drafts; useUnsavedDraft and DiscardDraftDialog protect in-app navigation and browser page unload. Session expiry clears sensitive drafts instead of persisting passwords in client storage.

SessionReport owns a bounded persisted-observation query and CSV export, with the selected WITA period, last observation time, 5,000-row limit and incomplete historical coverage visible. Filters are form-local until Load report; report dates are not shared with the bounded live-session search. Reset results when date input changes.

RecoveryInspection owns the dependency/media/item inspection and nested isolated-export confirmation. Native dialog supplies top-layer modal behavior; Go back is initial confirmation focus. Same-key retry and journal feedback follow OPERATIONS.md. Live export is Admin-only and additionally gated by backend settings and an administrator-owned approved job scope on the integration server. Guest-file, original-VM and instant recovery are unavailable.

## Draft policies, observed alerts and print variant

PolicySettings owns draft create/edit with explicit freshness/schedule validation, revision conflict feedback and the shared multi-form dirty guard. NativeDateField's time variant owns the proposed WITA time input; no schedule is applied. OnboardingPreview binds a selected draft revision to disabled, no-schedule config review, then stages a durable dry-run apply operation from the same selected VM set. The dialog must clearly state that local temporary fixtures are generated for rehearsal only and that no Bareos reload occurs. It must also render explicit reviewed additions for the existing preparation and retention allowlists rather than hiding that dependency in a generic warning. Prepared assignments appear back in the VMware table as `Prepared assignment` with `Pending controlled apply`; they are not Protected or Pending first backup.

AlertJournal owns bounded observed-failure/warning state filtering, session review and Admin acknowledgement. It preserves unknown/stale evaluation and never equates acknowledgement with success. Shared fields/tables are used. Data rows load after snapshot evaluation; no always-on notifications are implemented.

SessionReport's native print action prints only the visible report table page. Range/page, environment, period, observation/generation dates and incomplete coverage remain visible; account forms/navigation are hidden in print media. This is not an all-pages export. CSV is the bounded full report export.

### Explicit operation-job scope

The Jobs table and session drawer use `capabilities.operationJobs` to disable actions outside the activated scope, with explanatory copy in the Jobs table. Backend scope validation remains authoritative before queueing and again before dispatch. Existing canonical confirmation, focus, role, idempotency, durable feedback and Unknown-state contracts apply unchanged. Live local acceptance is documented in OPERATIONS.md; production VM restore/provisioning remains unavailable.

### Controlled live onboarding pilot

The existing OnboardingPreview dialog owns both rehearsal and server-approved live review. The VM table uses `capabilities.onboardingUuids` for the Live Add button; backend/root checks remain authoritative. Review explicitly distinguishes applying resources from starting the first backup, states power preservation and dedicated repository impact, and preserves its request key on transport retry. Close/Escape are blocked during submission. History labels live entries Enable backup and uses Not applicable for the configuration operation JobId. Only a subsequent completed backup supplies backup evidence; live configuration never implies tested recovery.


## Direct VMware destination review

VMwareRestorePlan, nested in RecoveryInspection, owns the new-VM destination review variant. Existing auth-field inputs and policy-fields layout preserve the token system. All five destination names are transient form drafts; useUnsavedDraft and the shared DiscardDraftDialog protect navigation/close. Server validation focuses and labels the first invalid field. Editing cancels pending reads and invalidates the previous review; an old response must never replace a newer draft. Only Admin sees/uses this form. POST /api/recovery/vmware/plan is a same-origin authenticated read-only review; it performs typed upstream GETs only.

Power off, disconnected network and Never overwrite are fixed review invariants, not currently executed guarantees. Destination names are manually entered and explicitly unverified. Source UUID compatibility, live target topology/permissions/capacity, network enforcement, durable dispatch and independent boot acceptance remain required before execution. No direct-VM Start action is exposed. Review never invokes a console restore command, because console API mode can submit without a yes token. Review digests summarize source-chain/destination intent only; they are not signed approvals or live target attestations.


## Accepted direct VMware restore workflow

The earlier review-only slice is superseded for the seven root-approved managed VMware sources (actual restore/boot acceptance remains PNET-only). VMwareRestorePlan uses NativeSelectField for live dependent datacenter/folder/host/datastore choices; changing a parent clears dependent values and invalidates review. The real same-origin Admin APIs validate target topology, capacity, permission and collisions. Fixed off/no-NIC/Never policy is enforced by the root receipt/plugin at VM creation, not just displayed. Review enables a nested native confirmation with Go back initial focus. Same key/digest/destination survive uncertain delivery; no automatic resend. Submit/worker authorization remains authoritative. RecoveryInspection shows separately recorded execution/isolation/OS-boot proofs for that exact source point; app/guest-file validity is not inferred. Root source scope and single-datastore limitations are explicit. Shared typography/tokens/draft guard remain canonical.


## Restore progress panel

RestoreProgress owns the shared submitted/active-restore and session-detail variants. Refresh starts immediately, repeats after 3 seconds, pauses hidden tabs and stops terminal sessions. Preserve final results; label retained data stale on errors and show last-received WITA time. Stage descriptions are derived from native job status/log evidence, not an asserted numeric completion ratio. Catalog counters are explicitly labeled and may update only at completion. No percentage or ETA appears without a verified total. Log tail is collapsed by default with the canonical scroll style. The panel reports native warnings without reclassifying them as success or failure.


Restore warning explanations preserve the native status. Only an explicit Warning log mentioning an existing MAC/UUID and generated replacement is classified as identity-change; other Warning entries remain unclassified and require review. Native text remains expandable. A generic terminal “with warnings” summary is not treated as an additional explanatory warning. History/drawer destination names come only from the exact restore JobId's journal record; unmapped jobs keep their native name. The drawer retains the underlying Bareos job name and search includes mapped destination names.


## Manual level and active policy variants

The canonical Run confirmation reuses NativeSelectField for Configured default/Full/Incremental. Initial focus is Go back. Editing level before submission retains the review key; after any send attempt selection is locked so explicit retry cannot mutate intent. Requested level is recorded separately from observed native level.

ActivePolicySettings owns existing-job current/review/confirmed-apply/status. NativeSelectField/NativeDateField and auth-field inputs/policy-fields grid remain canonical. Native checkbox labels select explicit job scope; no job is selected automatically. The form must hydrate its editable time/automatic/retention/volume inputs from the current active-policy response rather than from hard-coded defaults, and Reset to current must restore that live baseline while clearing selected jobs/review state. The shared dirty guard covers all edited fields and clears only after confirmed/reconciled Applied. Native confirmation initially focuses Go back, blocks closing during delivery and retains unknown request identity. Known rejection allows correction; unknown delivery exposes status reconciliation instead of automatic resend. Live application is distinct from draft policy metadata and remains subject to the root helper's complete-chain retention invariants and source digest.

## Settings subpages — 2026-10-16

Settings navigation is owned by BackupCenter and addressed by view=settings&section=connections|users|permissions|notifications|audit|policies. Connections is the default and invalid-section fallback. Native links expose aria-current; each subpage mounts only its relevant controls. Subpage changes use the shared draft-discard guard, including keeping the intended destination. Audit loads only on its subpage. Permissions summarizes existing roles/capabilities; editing roles remains in Users. Notifications explicitly states delivery is not implemented. Policies retains existing active and draft policy controls and Admin checks.

## Per-job calendar variant

ActivePolicySettings remains the canonical current/review/confirmed-apply/status owner and accepts an exact jobName variant from BackupCenter's job-schedule URL view. The Jobs row Edit schedule action is Admin-only for managed jobs. The variant loads only that job, preselects it, hydrates its actual schedule and protects all scheduling fields with the shared draft guard. NativeSelectField owns start method, calendar mode, Full pattern, ordinal selection, dependency behavior and retry-related choices; native checkbox labels own weekday selection. Month-date text fields preserve raw editing text until typed server validation. Review explicitly names the job, selected run days/dates or dependency source, Full cadence, interval/window behavior, retry settings, time, retention and volume limit. Interval calendars must show an end time, and after-job mode must force Automatic schedule enabled. Helper text must describe after-job window end as a start gate rather than a hard job finish promise. The existing Apply confirmation and same-key unknown-outcome reconciliation remain unchanged. Unknown/manual schedule drift fails closed. Legacy Settings bulk policy cannot overwrite a custom per-job schedule; those jobs link conceptually back to Jobs editing.

## Scheduling helper compatibility gate — 2026-10-16

The server-owned live policy capability requires both the configured feature flag and recognized deployed helper fields. An older or unverified helper returns applyEnabled=false plus a visible blocker. A local-only preview is explicitly targetVerified=false and cannot enable Apply, even when an earlier capability response enabled it. The Apply endpoint rechecks deployed compatibility under its operation lock before any mutation transport. This is a compatibility gate, not evidence of live schedule acceptance or a claim that all advanced execution modes are supported.

## Disable schedule review

Jobs exposes Admin-only `Review disable` for managed Backup jobs. DisablePreview reuses the existing native modal / restore-confirm / account-confirm styling and focus-restoration contract. Review POST accepts only a job name; server owns scope, identity and evidence. Loading, timeout, retry and explicit missing-proof states do not enable execution. Close/Escape restores focus to the trigger; no Disable confirmation or mutation is offered. Existing backups are preserved. Evidence: tests/disable-preview.spec.ts and backend/tests/test_disable_preview_api.py.
