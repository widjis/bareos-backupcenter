# Lifecycle local implementation checkpoint — 2026-10-16

## Delivered locally

Existing TRAE conversations were reused with observed GPT-5.4 responses for Disable/Enable backend, Jobs UI, Clone candidate, retirement candidate and independent review. No new TRAE conversation was created. Coordinator reviewed source and integrated the results; initial fail-open helper fallbacks and pre-commit clone dispatch were rejected and corrected.

Jobs now exposes Disable, Enable, Clone, Delete config and the existing exact-job Edit schedule. Enable is independent of the Director Job Enabled flag because lifecycle disable suppresses automatic delivery while preserving manual-run identity. Lifecycle review visibility is separate from the Run/Cancel allowlist; backend persisted managed identity remains authoritative. Clone carries an explicit target VM UUID and dedicated repository identifier. General name/VM/repository editing of an existing job remains unsupported.

Disable/Enable candidates use reviewed configuration revisions, durable operations and a native candidate helper with dependency rejection, POSIX locking, stored before-images, actor/intent binding, rollback and read-back. Worker success requires an Applied helper result; Failed and Unknown never become Completed. The helper requires root before native mutation. These fixture checks do not establish complete production ownership/runtime coverage.

Clone candidates generate dedicated disabled/manual resources without copied history or secrets. A committed dispatch claim precedes external execution; ambiguous delivery/final-store failure retains an unresolved claim and does not resend. Retirement candidates persist an identity/recovery record and before-image before removing only an exact owned job file. FileSet, Pool, Storage, Schedule, Catalog and backup data stay outside this action. Retired discovery preserves references without claiming verified media readability or restore success.

API review/apply/status routes are integrated into the main local application. Additional routes require Admin, confirmed same-origin requests, strict server-derived proof, fresh review digests and explicit installed/collector/store/executor readiness. Receipt status does not expose configuration or before-images. Unknown UI results retain their request key across dialog reopen; a contradictory ready response containing blockers cannot execute. Review references are collapsed to keep technical identifiers out of the primary decision area.

## Verification

- Full backend: **246 passed, 1 POSIX-only skipped**; existing AnyIO deprecation warning.
- Initial full browser run: **42 passed, 2 failed**. Both failures were investigated: old receipt fixture route and a hardcoded History session no longer on the visible page.
- After correction: **11 targeted browser tests passed**, including both failed cases, Clone target payload, contradictory readiness, Unknown close/reopen, keyboard/focus, accessibility and narrow layout. Do not describe the initial full run as entirely green.
- TypeScript passed; optimized Next production build passed. Build-generated development type references were restored.
- Strict premium audit has the known root DESIGN.md assumption; AGENTS.md explicitly requires canonical docs/DESIGN.md. No other finding.
- Global Prettier check reports 22 untouched existing files; touched-file formatting is checked separately. No unrelated mass formatting.
- Whitespace diff check passed, with existing LF/CRLF warnings.
- Local backend refreshed after database read-back confirmed zero unresolved operations. No dispatch flags changed.
- Authenticated real review checks: Clone and removal HTTP 200 / blocked / executionSupported=false. Disable/Enable HTTP 409 because persisted managed assignment identity is not registered for the selected existing job. This is an actual prerequisite gap, not accepted lifecycle execution.
- Correct current policy endpoint is GET /api/policies/active: HTTP 200, helperCompatible=true, applyEnabled=false. An initial smoke request incorrectly used /active/current and returned 404; no route change was needed.

## Still open

1. Reconcile authoritative managed job/VM/repository identities for existing live jobs, including the distinction between released onboarding assignments and retired jobs. Do not fabricate proof or revive retired ownership blindly.
2. Complete native resource/include/JobDefs ownership and inbound hook/runtime coverage; prove lifecycle and after-job dispatch locking suppresses all deferred/retry races.
3. Implement and accept production durable Clone/retirement store adapters, real collectors and native executors. Injected test adapters are not production persistence or transport.
4. Install an exact reviewed helper package and accept Disable/Enable plus Clone/removal on explicitly selected disposable targets, including retained recovery lookup/restore proof and rollback. None of these real operations was performed in this batch.
5. Ordinary 21:30 scheduled acceptance remains deferred until tonight (P07-049). No monitor or automation was created.

No server helper was replaced, no production job was disabled/enabled/cloned/removed, and no backup/restore/data deletion was dispatched in this batch. Local code/UI delivery and production acceptance remain separate.

### Final local runtime check

Touched-file Prettier check passed. After the final collapsed review-reference change, a browser check encountered a transient identity proxy reset; backend health stayed HTTP200. The scoped frontend process was refreshed after the production build, and the same keyboard/a11y/390px lifecycle case then passed (1 passed). Backend and frontend remain available on loopback. Per-job component keys prevent table sorting from reusing lifecycle state for another job. Final TypeScript and whitespace checks passed. No production acceptance gate was closed by this local runtime recovery.


## Batch 6 production metadata checkpoint — 2026-10-16

The earlier missing persisted managed identity prerequisite is resolved at the database layer. The reviewed migrations 010/011 were applied through scripts/apply_lifecycle_migrations.py with pinned SSH trust, existing administrator access and a migration ledger transaction guard. Repeated read-only checks verify unchanged checksums. scripts/reconcile_managed_registry.py defaults to read-only; explicit --apply changes application identity metadata only. Fresh collection resolved all seven VMware jobs, with authenticated loaded resources for all 12 Director jobs and current 41-VM inventory. Initial reconciliation returned Applied and the next fresh pass returned Replay; all seven revisions remain 1. The original Retired onboarding staging row remains unchanged.

Concrete PostgreSQL lifecycle adapters passed six tests against a uniquely owned isolated schema using real SQL and the application runtime role. Same-key concurrent claims dispatch once, external keys isolate across connections, Unknown retains target claims, retirement duplicate claims reject, Unknown terminal CAS remains unchanged, and the runtime role cannot delete operation receipts. Probe cleanup verified ownership before removing the test schema. No Bareos action was dispatched.

The application Store composition and Admin-only sanitized registry endpoint have four focused tests. The native package is not installed, production collectors are still under implementation, and broad lifecycle Apply remains unaccepted. An intermediate full regression excluding the in-progress native fixture file returned 269 passed, 5 failed, 1 skipped; failures concern transport assumptions and native dependency fixtures and are not hidden by this checkpoint. Do not treat production metadata readiness as accepted Disable/Enable, Clone or retirement execution. Ordinary21:30 scheduling acceptance remains pending.

Sanitized local evidence: .local/lifecycle-production-b6/coordinator-live-foundations.json and registry-reconciled-source.json. TRAE conversations are reused with GPT-5.4; no new conversation was created.
