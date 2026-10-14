# Observed Alerts and Backup Reports

## Alert facts and lifecycle

History contains an in-app journal for failure/warning evidence from currently configured Backup jobs. Migration 007 persists a deduplicated alert keyed by connection and source JobId. Evaluation uses the latest observed terminal backup per job; a newer Running session does not resolve an earlier failure. Restore sessions are excluded. Source outages never resolve alerts. Current observed successful later JobIds resolve earlier Open/Acknowledged alerts.

Admin acknowledgement records review with an actor, revision and audit event. It changes no Director, backup or recovery state. Viewer/Backup Operator acknowledgement is rejected in this conservative release. Filters and table paging are shared primitives. Empty successful results, initial failure and stale cached results remain distinct.

Evaluation occurs when application snapshots are collected by UI/explicit reads; this is not an independent always-on notification collector. Rows and evaluation freshness are read after collection. No notification channel is configured or message sent. Mandatory-scope/RPO, maintenance, escalation and ownership routing require accepted policy assignments and remain pending. Draft policy targets are not evaluated as active protection.

Real PostgreSQL deduplication, acknowledgement, preservation during a running retry and resolution after later success were verified in an isolated rolled-back namespace. Browser acknowledgement used intercepted synthetic writes; no fabricated production alert was persisted.

## Reports and exports

History can query persisted application observations by backup start dates in Asia/Makassar. Date periods are inclusive locally and converted to explicit timezone-aware boundaries; maximum 366 days. Query and export are scoped to the configured connection. Up to 5,000 records are returned with total/truncation, environment, generation time, observation dates and incomplete historical coverage visible.

CSV excludes credentials and neutralizes spreadsheet-formula prefixes in user/source string cells. The print action prints the current report table page with period, scope, visible range and coverage; it does not imply all report pages were printed. Native browser/OS print and date popups are deliberate maintained variants. No export or archived observation is a restore guarantee, complete Catalog history or proven policy compliance.

Real report queries and CSV output were verified. Time boundaries, reversed/excessive periods and CSV formula prefixes have backend tests; browser checks cover invalid range/focus, accessible reports, CSV and print invocation. Physical print/PDF output acceptance is separate.
