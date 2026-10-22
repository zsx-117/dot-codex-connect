# Source preview validation

Date: 2026-10-22. Local environment: macOS, Node 24.19.0, Python 3.12.14. All data is synthetic; no real customer, transaction, or conversation data is used. OAuth test signing keys exist only in process memory.

| Check | Result | Coverage |
|---|---|---|
| `(cd selfhost && node --test test.mjs oauth.test.mjs oauth-route.test.mjs)` | 8 passed | Actual MCP/agent routes, stable requests/monotonic synchronization, static-auth separation, OAuth metadata/signatures/claims/fail-closed behavior |
| `python3 scripts/test_python.py` | 48 passed | Synthetic regressions against the actual connector source: recovery locks, writer/queue/steering, probes, catch-up, and related behavior |
| `(cd service && node tests/cloud.mjs)` | 6 groups passed | Deduplication, owner isolation, transactions, events, subscriptions, receipts/ACK |
| `(cd service && node --test tests/task-state.mjs tests/communication.mjs)` | 9 passed | Wait deadlines, cancellation, reply state, and communication boundaries |
| `python3 scripts/test_source_build.py` | Passed | Identical hashes from two source builds; separate extraction, self-check, and subprocess startup; no account reads |
| Skill format and setup helper | Passed | Format, full-source entry point, and offline workflow |
| `(cd selfhost && node --test http.test.mjs)` | 1 passed | One approved retry; ephemeral 127.0.0.1 listener, in-memory SQLite, synthetic credentials; listener closed |

The current core excludes commercial modules. The first preparation pass's 18/46 entitlement/commercial tests are not counted as current core tests; their source and old results remain only in private local backups. The duplicate sets of 47 device/connector tests from that pass are not counted as additional scenarios either.

OAuth synthetic tests fully mock JWKS retrieval. Static core round-trip tests forbid fetch. The Python runner uses temporary source and state, blocking network access and real Codex launches. This is not an OS-sandbox security audit of malicious code.

The first HTTP test could not start because of sandbox EPERM. One retry after explicit user approval through the supported approval process passed. This establishes only local synthetic HTTP behavior. No real user credentials, OAuth login, HTTPS deployment, Mac account, or business conversation was used.

Repository CI reruns core/OAuth, Python, state/queue, source-build, and ephemeral loopback HTTP tests on macOS/Linux. Refer to the GitHub Actions result for the specific commit. CI does not establish real Dot end-to-end compatibility.

Still unverified: an actual HTTPS proxy, real authorization-server import/login, Dot client registration and OAuth callbacks, real Mac account binding and selected-conversation send/read, real webhook/ACK, end-to-end recovery after network loss/restart, compatibility with newer CLI versions, and a signed/notarized app. See [OAuth and Dot](oauth.md) for explicit steps and minimum permissions. The original paid app is not evidence of a build from this source.
