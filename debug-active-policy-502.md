# Debug Session: active-policy-502
- **Status**: [OPEN]
- **Issue**: `GET /api/policies/active` returns 502 locally, so the Settings panel cannot hydrate the active policy baseline or render managed job choices.
- **Debug Server**: Pending startup
- **Log File**: .dbg/trae-debug-log-active-policy-502.ndjson

## Reproduction Steps
1. Start the local backend and frontend.
2. Sign in as the local Admin user.
3. Open `Settings`.
4. Observe the `Active backup schedule and retention` panel.
5. The panel shows `Active policy unavailable. No settings changed.` and `/api/policies/active` returns 502.

## Hypotheses & Verification
| ID | Hypothesis | Likelihood | Effort | Evidence |
|----|------------|------------|--------|----------|
| A | The local `/api/policies/active` route fails before transport because platform-specific gating rejects the current macOS environment. | High | Low | Confirmed |
| B | The route reaches `backend.policy_target.invoke`, but local environment values such as host, credentials, or required executable path make the transport fail immediately. | High | Low | Rejected for host/credential mismatch; invoke is reached, but platform gate fails first. |
| C | The local route catches a meaningful transport error but collapses it into a generic 502, hiding the actual cause from the panel. | Medium | Low | Confirmed |
| D | The current active-policy transport is unnecessarily coupled to live apply transport, so read-only `current` calls fail even though local data is available. | Medium | Medium | Confirmed |

## Log Evidence
- `backend/app.py:active_policy_current` logged entry on `posix`, then failure `ValueError: Managed policy transport is configured for this Windows environment.`
- `backend/policy_target.py:invoke` logged `action=current`, `platform=posix`, `host=10.60.10.77`, then rejected the current platform before any subprocess transport.
- After the fix, authenticated local probes returned `200` for `/api/policies/active` with managed jobs and `200` for `/api/policies/active/preview` with a review digest on macOS.

## Verification Conclusion
Root cause: read-only `current` and `preview` were routed through the Windows-only policy transport. On macOS local development that transport correctly rejects the platform, but the route converted the useful error into a generic 502. The fix keeps live apply/status transport unchanged while adding local fallback generation for `current` and `preview`.
