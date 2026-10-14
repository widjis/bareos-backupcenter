# Local Application Authentication

## Approved model

The operator selected local application accounts with Admin, Backup Operator and Viewer roles. All three roles cover the single configured environment; per-resource or multi-site authorization is not implemented.

| Action | Admin | Backup Operator | Viewer |
|---|---|---|---|
| Monitoring, inventory, session logs, operation history and audit | Yes | Yes | Yes |
| Confirmed Run/Cancel | Yes | Yes | No |
| Create accounts or change account role/enabled state | Yes | No | No |
| Draft policies / onboarding previews / observed-alert acknowledgement | Yes | No | No |
| Isolated disk export preparation | Gated; explicit server/test approval pending | No | No |
| Change own password / sign out | Yes | Yes | Yes |

The browser shows current account and role. Role presentation never replaces backend authorization. Viewer capability responses are derived after copying the shared monitoring cache, preventing permissions from leaking into another user's cached snapshot. A worker rechecks the request actor's current enabled state/operation role after preflight and inside the Dispatching claim transaction with a shared user-row lock. Logout does not cancel already confirmed jobs; account disable/role revocation prevents still-Prepared dispatch. Already dispatched jobs retain Director ownership.

## Passwords and sessions

Migration 004 adds application users and durable sessions. Passwords use per-user random 128-bit salts and PBKDF2-HMAC-SHA256 with 600,000 iterations. Comparisons use constant-time digest comparison. Raw session tokens are random and are stored only as SHA-256 hashes in the database. The browser receives an HttpOnly, SameSite=Strict cookie with an eight-hour absolute lifetime. Sessions are revoked on logout/password change/account disable. This loopback HTTP release sets Secure=false; remote HTTPS deployment requires Secure cookies and a separately accepted hosting configuration.

Five failed attempts pause an existing account for 15 minutes. Login errors are generic. This account-level control is not a production reverse-proxy rate limit. Identity database errors fail closed. Request validation errors exclude submitted input values, including passwords. Password fields are masked with accessible reveal controls; secrets are not placed in URLs or client storage.

All enabled POST routes require the approved application Origin and confirmation header. Account creation/access changes add a review dialog with Go back initially focused. Role changes are serialized and recheck the administrator in the same transaction. The final enabled Admin cannot be removed, and self-demotion/disable requires another administrator. No hard-delete or administrator password-reset endpoint is exposed.

The configured Bareos integration account remains the existing hermes-api Console/Profile. Application roles constrain typed routes above that shared integration; separate per-role Bareos profiles and resource ACL mapping are still pending. No raw console access is exposed.

## Initial account and operator steps

Run database bootstrap, then `.venv/bin/python -m scripts.bootstrap_admin`. The bootstrap creates `admin` once without overwriting an existing account. The generated initial credentials remain in the ignored owner-only `.env` under `BACKUPCENTER_ADMIN_USERNAME` and `BACKUPCENTER_ADMIN_PASSWORD`; values are never printed. Sign in with those settings, change the password in Settings, and create individual operator/viewer accounts. A password change invalidates existing sessions. The environment bootstrap password does not automatically change an existing database password.

Browser tests use that initial account to obtain a dedicated session stored in owner-only `.local/playwright-auth.json`. Logout tests acquire a separate session. After changing the initial password, update the local test-login setting if running live browser tests; do not put secrets in test source. Test operations remain intercepted and do not send real Run/Cancel requests.

## Acceptance boundary

Local login and role enforcement are implemented. Real login/logout, backend permission denial, worker revocation, password hashing, secret-safe validation, DB failure, and browser checks are recorded separately in the implementation report. Local loopback testing does not establish organizational authorization acceptance, remote hosting security, managed TLS, or production identity lifecycle readiness.
