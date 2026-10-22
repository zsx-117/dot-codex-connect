# Self-hosting and source builds

Run the following code blocks from the repository root unless a command explicitly enters a subdirectory. Subdirectory commands use a subshell so later commands keep the same working directory. For Skill installation, see the [README](../README.md#install-as-a-codex-skill).

## Offline checks

Requires Node 24+ and Python 3.12+. The core uses built-in modules and does not run npm/pip installation scripts.

```sh
bash skills/dot-codex-connect/scripts/setup-mac.sh --check
bash skills/dot-codex-connect/scripts/setup-mac.sh --test
```

Set `DOT_NODE_BIN` / `DOT_PYTHON_BIN` if the interpreters are not on PATH. Tests use synthetic identities. OAuth test keys exist only in memory; they are not saved, and no real accounts are registered. Run the HTTP listener test separately with `(cd selfhost && node --test http.test.mjs)`. It uses only an ephemeral loopback port. The initial attempt was blocked by sandbox EPERM; one retry after explicit user approval passed, and the listener was closed.

## Build the local connector from source

```sh
python3 scripts/build-source.py --output ./connector-source.zip
python3 scripts/test_source_build.py
```

The archive contains 11 Python modules, the MIT license, run instructions, and file hashes. Timestamps, ordering, and file modes are fixed. Two builds from the same inputs produced identical hashes, and a subprocess self-check passed after extraction into a separate directory. This is not a macOS app and contains no compiled binaries, signing, or notarization. It runs with standard Python and requires no Gatekeeper or quarantine changes.

## Service: static or OAuth mode

For static mode, copy `selfhost/.env.example`; for OAuth mode, copy `selfhost/.env.oauth.example` to your private configuration. Keep configuration files out of Git. The examples contain no usable credentials. The operator supplies a device credential they control and, in static mode, a different MCP credential. OAuth mode forbids a static-token fallback. No real persistent credentials were created during this preparation.

```sh
(cd selfhost && node --env-file=.env server.mjs)
```

The service builds its local `.generated/` directory, initializes its own SQLite database, and binds to `127.0.0.1:8787`. Use a fresh state directory accessible only to the service user, with umask 077. Never point it at an existing paid-service database. Each process supports one operator and one database. The source has no payment/entitlement service calls or customer/transaction tables.

Use an HTTPS proxy you maintain to expose `/mcp` and `/agent`. OAuth mode also exposes `/.well-known/oauth-protected-resource/mcp`. Preserve authentication headers, limit traffic, and do not log request bodies or credentials. Browser POST requests carrying an Origin header are rejected; direct browser access is outside the validated scope. No domains, proxies, certificates, or deployments were created during this preparation.

See [OAuth and Dot](oauth.md) for login, exact configuration, and steps the user must perform. Static Bearer authentication is not OAuth.

## Explicit Mac binding and foreground operation

The Mac must already have a working Codex CLI and the user's own login environment. Set `DOT_CONNECT_SERVICE` to your HTTPS origin, `DOT_DEVICE_TOKEN` to the service's device credential, and `DOT_CONNECT_HOME` to a **fresh absolute path**.

```sh
python3 selfhost/configure_mac.py --home "$DOT_CONNECT_HOME" --approve-account-binding
python3 service/connector/src/connector.py run --home "$DOT_CONNECT_HOME"
```

The binding command reads the current account identity through the public AppServer interface, confirms a device heartbeat, then saves the fingerprint and configuration. It does not read account files or chats, send tasks, or create keys. It refuses to overwrite existing state. The second command runs in the foreground and does not install a launchd service. The source CLI no longer exposes the old purchase-pairing or commercial-installation commands. TLS verification continues to use system CAs. Fix CA/proxy configuration when certificate errors occur; do not disable verification.

Real account binding, device heartbeats, and task exchange were not performed during this preparation. If binding partially fails, preserve and inspect the private state; do not automatically replace the key or overwrite the directory.

## Layered validation, troubleshooting, and shutdown

Start with initialize/tools/list, then check access status and the device heartbeat. Only list/read/send after authorization for a specific disposable test conversation, using a stable requestId each time. Verify the target turn and actual reply, then independently verify webhook receipt and the application ACK. Stop the foreground process to stop the connector; state is retained. Deleting state or revoking credentials requires a separate explicit action.

Webhook destinations are resolved through system DNS, with public IP pinning and TLS verification. The source version removes the built-in external DNS fallback. If a VPN returns Fake-IP or private addresses, delivery is rejected. The operator must fix their DNS configuration; this preparation did not change the VPN or system DNS.
