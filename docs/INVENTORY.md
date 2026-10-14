# VMware Inventory

## Implemented connection

The FastAPI backend uses VMware pyVmomi 8.0.3.0.1 to read vCenter directly. Credentials are resolved from the local backend-only `VMWARE_VCSERVER`, `VMWARE_VCUSER`, `VMWARE_VCPASS`, and `VMWARE_VCTHUMBPRINT` settings. No VMware login, session cookie, or raw plugin configuration reaches the browser.

TLS uses the configured certificate fingerprint. `Connect` avoids SmartConnect's version-discovery request; the SDK checks the fingerprint on every new HTTPS socket before SOAP/login. The SSL context relies on fingerprint trust instead of CA/hostname validation. This is deliberate certificate pinning, not an accept-any-certificate fallback. A missing/malformed pin blocks login. A real wrong-pin test was rejected. SHA-1 compatibility is retained for the existing configured fingerprint; managed PKI or SHA-256 pinning remains preferable for production.

The account's privileges have not been changed or certified as least privilege. The implementation invokes only inventory/session/view/property-collector operations, and the UI labels visibility as objects available to the configured account. A dedicated read-only VMware account is still an operational prerequisite for production.

## Identity and persistence

VM identifiers use connection-scoped instance UUIDs; MoRefs, BIOS UUIDs, names, datacenters, folder paths, host/compute metadata, power, CPU, memory, template state, and committed storage bytes are distinct fields. Missing UUIDs have explicit MoRef-only quality and cannot be selected for enrollment. Duplicate instance identifiers fail collection. A changed vCenter instance identity retains the old snapshot as stale and requires review.

Additive migrations 002 and 003 store snapshots and VM identity observations in the application database. Removed or inaccessible objects become no longer visible; this is not proof of deletion. Historical rows are retained. A reused MoRef can identify a different instance without overwriting its earlier UUID history. Runtime privileges remain SELECT/INSERT/UPDATE; the runtime role cannot create tables or delete history.

Current name/folder/datacenter associations with existing Bareos FileSets are provisional Candidate match entries. Duplicate matches are Ambiguous match. Explicit plugin instance UUID references can show Identity match. Candidate matches never become persisted assignments or proof of protection automatically.

## Browsing contract

`GET /api/inventory` accepts bounded search, folder, page and name-sort filters. PropertyCollector retrieves 250 objects per source page with a 50,000-object/60-second collection limit. Browser pages contain 25 VMs. API filtering covers all visible collected VMs rather than only the displayed page. Results are cached for 60 seconds; Refresh inventory requests a new collection.

The Infrastructure browser owns the VMware folder navigator, shared server-page DataTable variant, explicit UUID-keyed checkboxes, and selected-VM summary. Committed state uses `invq`, `invfolder`, `invpage`, and `invsort` in the URL. Search is IME-aware, debounced 300 ms, aborts superseded browser requests, and clears immediately with focus restoration. Selections remain across filters/pages for the mounted inventory view. There is no implicit select-all-matching behavior; leaving the view clears transient selection.

Unavailable inventory, successful empty inventory, no matches, stale cached evidence, and failed persistence remain distinct. Templates, missing UUIDs and stale data cannot be selected for onboarding. Add to backup remains unavailable until the controlled provisioning service is implemented.

## Evidence

Read-only access to the actual vCenter reported version 8.0.3, 40 visible VMs and 11 collected hierarchy folders on 2026-10-14. Certificate mismatch rejection, real database persistence/reload, real browser pagination/search/selection, desktop/mobile and automated accessibility checks succeeded. Tests cover rename/move identity, duplicate name associations, scoped IDs, missing UUID, authentication failure, stale recovery, replaced vCenter, and secret-safe errors. Operator acceptance is separate from these checks.

Installed Bareos source uses `FindByUuid(..., True, True)`, confirming instance-UUID backup lookup. VDDK 8.0.3 is installed. No existing FileSet, VM, schedule, media or backup job was changed.

Primary references: [VMware SDK source](https://github.com/vmware/pyvmomi), [Bareos VMware plugin documentation](https://docs.bareos.org/bareos-22/TasksAndConcepts/Plugins.html).
