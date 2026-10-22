# OAuth resource server and Dot compatibility

## Implemented and tested

The service exposes `/.well-known/oauth-protected-resource/mcp` (also available at the root well-known path) and a 401 `WWW-Authenticate: Bearer resource_metadata=...` challenge. Metadata points to the operator-configured issuer. The resource server accepts only RS256 and validates the signature, audience, issuer, operator sub, authorized client, scope, and time bounds. It rejects ID tokens, embedded JWKs/external key URLs, and static-token fallback. The authorization server handles login, authorization codes, and PKCE; this service does not issue tokens. See the [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization).

Positive and negative tests use in-memory RSA keys, synthetic JWTs, and mocked JWKS responses, including access checks through the actual MCP route. Real Dot browser login and OAuth client registration have not been tested. This does not establish full OAuth/MCP authentication interoperability.

## Self-hosted configuration

You can use your own Keycloak instance or another authorization server that meets the requirements below. Keycloak documents OIDC discovery and public certificate endpoints in its [official documentation](https://www.keycloak.org/securing-apps/oidc-layers). This is a deployment guide, not a report of an already configured instance.

1. Configure Authorization Code + PKCE S256 in an isolated test realm/issuer. Disable password grants and implicit flow. Do not use a production realm.
2. Allowlist the exact callback address shown by the actual Dot interface. Do not guess URLs, use wildcards, or enable automatic dynamic registration. Dot's current callback address and client-registration capabilities were not established during this work.
3. Preconfigure a dedicated client and the `codex:bridge` scope. The access-token audience must include your exact `https://HOST/mcp` resource, and only one operator sub is allowed. Configure a dedicated audience mapper and issue RS256 access tokens with `azp` or `client_id`, `iat`, `exp`, and `scope`. The verifier accepts RFC-style `typ=at+jwt`, or a Keycloak-style `JWT` header type with a `Bearer` payload type.
4. Set issuer/JWKS URI/resource/client ID/operator sub using the corresponding fields in `.env.oauth.example`. The JWKS URI must share the issuer's origin. The maximum access-token lifetime is one hour; a few minutes is recommended in the authorization-server configuration. Do not set `DOT_MCP_TOKEN`.
5. The resource server verifies tokens against public JWKS and does not forward them to other business services. JWKS is cached for at most five minutes; an unknown kid can trigger a refresh at most once per minute. Key rotation may briefly cause new keys to be rejected. There is no real-time introspection or revocation: a previously issued token may remain usable until it expires. Use short-lived access tokens.

The reviewable example is `selfhost/keycloak-realm.example.json`. Its realm and client are disabled by default; it has no users, passwords, or client secret, and its callback and audience use `.invalid`. It has not been imported or registered. Import compatibility with actual Keycloak versions and Dot's support for public/pre-registered clients remain untested. Supply and review the client's real callback before enabling the configuration in an isolated test instance. Do not infer a callback from the example.

## Minimum user decisions and actions

| Action | Purpose and minimum permission | Status for this preview |
|---|---|---|
| Allow an isolated loopback listener | Ephemeral local port, synthetic data only; no public exposure or credential creation | Approved; one retry passed and the temporary listener was closed |
| Provide a test HTTPS service and issuer you control | Separate test domain, certificates, and authorization server; no changes to production | Not provided/deployed |
| Register a test OAuth client | Exact Dot callback, only `codex:bridge`, and PKCE; no additional scopes by default | Explicitly outside this preparation's authorization; not performed |
| Log in and grant consent personally | Approve the stated scope in your own issuer/Dot interface | Not performed |
| Supply an existing test device credential, or explicitly authorize creating one | Only this test connector's access to the test service; no persistent credentials created here | Not supplied/generated |
| Authorize binding your Mac in a fresh state directory | Public AppServer account/read; no reading other conversations or changing the production bridge | Not performed |
| Choose a disposable test conversation and authorize one send | Read only that conversation, send a synthetic marker, and query the same requestId | Not performed |
| Explicitly authorize webhook/ACK validation for that test result | Use the actual Dot test receiver; do not guess or broaden recipients | Not performed |

Offline tests cannot replace these steps. If Dot does not support pre-registered client parameters, verify its supported registration mechanism against your authorization server's capabilities. Do not reuse the old private platform's OAuth identity or automatically enable unreviewed dynamic registration for compatibility.

## Remaining limitations

This is a single-user resource server. It does not implement multi-tenancy, an OAuth authorization server, SSE push, or a full MCP conformance suite. Scope-related authentication challenges return 401; per-tool step-up authorization is not implemented. The events interface is an extension from the original product, and real Dot support remains unverified. Server POST requests with an Origin header are rejected; the current target is server-side MCP clients. Self-hosting does not require purchasing the original service, but users must control their own identity system and deployment environment.
