# Acceleration Browser Verification

Date: 2026-10-16

## Scope

Owned files only:

- `tests/job-schedule.spec.ts`
- `tests/restore-progress.spec.ts`
- `tests/scheduling-fixtures.ts`
- `docs/ACCELERATION-BROWSER.md`

No product source, backend code, `.env`, services, schedules, backups, restores, cleanup jobs, or deployed helpers were changed.

## What was stabilized

- `restore-progress.spec.ts` now uses intercepted snapshot, operations, session log, and progress responses so it no longer depends on a live paginated restore-history row being visible.
- The restore-history assertion still preserves the exact journal destination mapping requirement:
  - history search and row label use the intercepted mapped destination VM name
  - the drawer still asserts the mapped destination heading and the underlying Bareos job name
- `job-schedule.spec.ts` now intercepts every tested scheduling mutation:
  - `POST /api/policies/active/preview`
  - `POST /api/policies/active/apply`
- The scheduling coverage now exercises:
  - exact-job entry from Jobs
  - existing calendar hydration
  - interval review payloads
  - ordinal edit/reset behavior
  - rejected preview staying local
  - confirmation focus and no implicit Apply
  - draft guard with keyboard Escape
  - narrow viewport overflow check
  - exact-job after-job dependency behavior

## Commands run

1. Initial baseline before edits:

```powershell
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE='C:\Program Files\Google\Chrome\Application\chrome.exe'
$env:PATH='C:\Users\widji.santoso\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
npx playwright test tests/restore-progress.spec.ts tests/job-schedule.spec.ts
```

Result:

- `3 passed`
- `2 failed`
- Failures:
  - `tests/restore-progress.spec.ts`: relied on a live history row/button that was not present
  - `tests/job-schedule.spec.ts`: exact-job after-job dependency option was missing

2. Final verification after owned-file test changes:

```powershell
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE='C:\Program Files\Google\Chrome\Application\chrome.exe'
$env:PATH='C:\Users\widji.santoso\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
npx playwright test tests/restore-progress.spec.ts tests/job-schedule.spec.ts
```

Result:

- `4 passed`
- `1 failed`
- Passing:
  - `tests/restore-progress.spec.ts` both tests
  - `tests/job-schedule.spec.ts` interval/no-implicit-apply/draft-guard test
  - `tests/job-schedule.spec.ts` hydration/ordinal/rejected-preview test
- Remaining failure:
  - `tests/job-schedule.spec.ts` after-job exact-job dependency test

## Remaining source bug in unowned code

The remaining failure is a real UI regression in `src/components/active-policy.tsx`, not a flaky test.

Observed behavior:

- In exact-job mode (`jobName` set), the active policy load filters `x.jobs` down to only the selected job.
- The after-job dependency select then builds its options from `rows.filter((row) => row.job !== jobName)`.
- Because `rows` already contains only the selected job, the dependency select renders zero options.

Effect:

- The exact-job schedule editor cannot review or submit after-job dependency payloads even when another managed job exists in the intercepted active-policy response.

Browser failure recorded by the final run:

```text
Expected option text: VMware-MTIMRWKF01
Received: []
```

## Limitations

- This task intentionally did not modify unowned product source, so the after-job regression remains open for the coordinator.
- Tests were run only for the targeted browser specs above, not the full Playwright suite.
- The Playwright global setup still uses the existing project login flow; no credentials were read manually during this task.
