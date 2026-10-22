# Security, privacy, and release boundaries

Use only the isolated, reviewed text-source package for publication. Do not include other Git repositories, backup archives, runtime directories, account files, or private review materials.

Preparation scanned blobs reachable through `--all` in four related Git repositories: the service, the earlier service, commercial checkout, and the installer. Rules covered common provider tokens, private keys, JWTs, URL credentials, credential literals, UUIDs, email addresses, local paths, and transaction markers. Results recorded only file/object locations and rule names, never original values. Regex checks cannot prove that a package contains no secrets. Binaries, untracked state, unreachable objects, reflogs, external archives, and restricted conversations were not comprehensively examined and are excluded from publication.

Excluded content includes original `.git` directories, `.openai`, runtime databases, real jobs/events/deliveries, private conversations, account and device bindings, logs, production analytics snapshots, customer/order data, and old binaries. A fixed personal notification route was identified and removed. Example identities use `.invalid`; original UUIDs were replaced with consistent synthetic fixtures to avoid disclosing real conversation identifiers.

The self-hosted state database stores requests and replies. Only the operator should be able to read it; apply access controls and define backup and deletion policies. Never commit the database to Git. Keep MCP and device credentials separate. Startup rejects example credentials, and request/reply bodies must never be logged. Webhooks can still target third parties, so real subscriptions require authorization for their destinations. No subscriptions or external messages were created during this preparation.

Do not modify quarantine/Gatekeeper, take over other writers, or change an existing Codex installation, launchd configuration, account, or service. Recover an uncertain execution outcome by querying the original request; never automatically resend it.

## Release review requirements

1. Rescan the final archive and manually review source text and examples; an independent scanner is recommended. The current tooling does not provide comprehensive high-entropy detection or static analysis of malicious payloads.
2. The package is attributed to zsx-117. Git author records are not treated as proof of the copyright chain. The old website templates and dependencies have been removed from the core; old lockfiles and third-party runtimes are not distributed. Preserve the licenses of any external code added later.
3. Validate HTTPS, OAuth if the client requires it, the Mac source connector, and authorized conversation readback on a fresh machine with a separate test account you control. These fixtures cannot replace that validation.
4. Publish a clean history while retaining the original private repository history; do not make an original repository public. If a real key is later confirmed to have leaked, coordinate revocation/rotation separately rather than doing it without authorization during this task.

Public issues should include the version, redacted error codes, and a minimal synthetic reproduction. Never paste tokens, device IDs, complete request bodies, customer/transaction data, or private conversations.

The second preparation pass added an OAuth resource verifier that fetches public verification keys only from explicitly configured HTTPS JWKS on the issuer's origin. It ignores remote key addresses supplied inside JWTs. Test signing keys and tokens are created and used only in memory: no files, printed secrets, or real OAuth registrations. `.gitignore` explicitly preserves `.env.example` and `.env.oauth.example` while ignoring other .env files.
