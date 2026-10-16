# Native Scheduling Validation — 2026-10-16

## Scope

Existing runtime and lifecycle TRAE conversations were reused with GPT-5.4. No new conversation was created. This checkpoint validates isolated native behavior on Ubuntu 22.04 / Python 3.10.12 / Bareos 25.1.1; it does not install helpers, activate production drain units, or dispatch a real backup.

## Actual results

- Candidate sources compile with installed Python 3.10.
- `systemd-analyze verify` accepts the prepared service/timer with exit 0. Existing netplan permission and snapd RestartMode warnings are unrelated environment warnings.
- Installed `bareos-dir -t` accepts daily interval, monthly ordinal, weekly and after-job/retry candidates. Candidate configuration and captured daemon logs remain in private server-side directory `/tmp/backupcenter-director-check-vsfxg7ax`; secret-bearing resource text was never exported. Production configuration hashes remained unchanged. The [official configuration-test behavior](https://docs.bareos.org/bareos-22/IntroductionAndTutorial/GettingStartedWithBareos.html) includes Catalog checks; no scheduler or RunScript execution is accepted from this test.
- `check_after_job_native.py` passes eight scenarios using separate processes and real fcntl: identical and distinct-source concurrency, crash/no resend, old-date expiry, deferred delivery in-window, terminal receipt reconciliation, Unknown blocking and receipt permissions. SQL and console dispatch are injected fakes.
- `check_drain_systemd.py` executes that harness as bareos under the prepared hardening properties through a unique transient timer. It passes once, then again after timer restart. Final unit `backupcenter-native-validate-764f15add55a` was stopped/cleaned; production drain units were not activated. Director/SD/FD remained active after checks.

The coordinator fixed the harness dictionary-sort bug, added deterministic lock contention and distinct-source/window-delivery cases, and corrected test-driver directory permissions and transient timer lifetime before acceptance. Ambiguous acknowledgement deliberately remains Unknown; a missing acknowledgement cannot establish that submission was rejected. No automatic resend is allowed.

## Local evidence

Full backend suite: 206 passed, 1 skipped, existing AnyIO deprecation. Existing UI was unchanged; the previous 41-browser checkpoint was not rerun. Protected source hashes match the pre-task snapshot. `.local/reuse-batch4/evidence.json` records actual check scope, reused conversation/execution IDs and UTF-8 LF-normalized source digests. Linux staging source is retained under `/tmp/backupcenter-native-b4-qs5vodz6`.

## Remaining gates

Helper installation and production timer activation are not complete. Actual source `%i` substitution, installed console acknowledgement, real Catalog identity reconciliation and PNET-only scheduled-run acceptance still need controlled end-to-end verification. Apply remains blocked. Disable/Enable remains unimplemented; the new proof normalizer has no transport or execution route and cannot substitute for authoritative collectors.
