# Draft Policies and Onboarding Previews

## Draft policy model

Settings supports Admin create/edit of reusable draft policies. Definitions store name, creator/owner, shared Storage reference, explicit backup freshness target, proposed volume retention, maximum volume count, Manual/Daily schedule proposal and WITA time. The owner is informational; current authorization is environment-wide role enforcement. Daily proposals require a freshness target of at least 24 hours. This validation is not proof that a future job meets that target.

Migration 006 stores revisions and audit events in the application database. Update requires the current revision and Draft state; conflicts preserve entered values. Server-side ownership/role checks accompany the save transaction. New-name uniqueness handles ambiguous retries without creating duplicate definitions. The runtime role has no delete grants. Admin edits remain drafts and create no Bareos configuration or cleanup/schedule execution.

Shared native select/date/time/number fields provide application validation, error associations and first-invalid focus. Settings drafts use the common discard guard; one clean form cannot clear another form's dirty state. Password drafts never enter client storage. Saving returns to the same Settings form/list with explicit Draft feedback.

## VMware preview

Select up to 25 explicit unassigned VMs in Infrastructure, choose a draft policy revision or the baseline proposal, and Generate preview. The backend requires fresh persisted inventory and current Bareos configuration. Templates, absent UUIDs, candidate/ambiguous existing associations, vanished IDs, policy revision changes and storage mismatches are rejected.

The preview creates deterministic UUID-based Job/FileSet/Pool names, references the installed VMware plugin by instance UUID and the existing server credential file, and reuses the existing enabled SMBFile Storage. It contains no credential values and creates no new physical repository or daemon device. Draft retention/volume limits propagate into the preview. Generated jobs remain Enabled=no without a schedule or first Run. Original preparation and retention allowlists are not silently expanded.

Generated resources passed the actual Bareos configuration test in a private temporary include file, run as the bareos service account for Catalog peer authentication. Original filenames were quoted. The temporary resources were removed and never applied or reloaded; live Director inspection still showed 11 jobs with no BC resources loaded.

## Durable rehearsal staging

Migration 008 adds configuration revisions and protection assignments. `POST /api/provisioning/apply` accepts the same typed VM/policy/storage selection as preview plus an idempotency key. The backend revalidates fresh persisted inventory, current Bareos configuration, policy revision and generated resource names before it stages the request.

Each accepted request creates one configuration revision payload, one prepared assignment per VM, and a `provision` operation journal row in a single transaction. Existing prepared assignments block duplicate selection across tabs/retries; failed or retired assignments remain separately reviewable. The operation worker then runs a dry-run rehearsal using temporary local fixtures only and records a Validated/Failed revision outcome. No Bareos configuration file is modified, loaded or reloaded by this path.

Prepared assignments overlay the VMware inventory as `Prepared assignment` with `Pending controlled apply`. This prevents silent duplicate onboarding while remaining honest that no Director resources have been loaded and no first backup has occurred.

The preview/apply payload also includes a `scriptReview` section. It lists the currently observed VMware workload jobs as the review baseline and emits one reviewed addition per generated job for `prepare-vm-backup` and `chain-retention`. This keeps the existing six-VM dependency explicit during rehearsal instead of hiding it behind a generic blocker string. The payload is advisory evidence only; Backup Center does not edit those server scripts.

## Remaining apply work

The controlled configuration apply service with explicit server permissions, coordinated live revision/apply/load/recovery, managed preparation/retention mapping, reviewed schedule UTC conversion and accepted assignment outcomes are still pending. Policy, preview and dry-run rehearsal availability do not establish Add to backup completion. An operator-selected unassigned test VM is required before live provisioning acceptance. First backup and restore verification remain separate actions/outcomes.
