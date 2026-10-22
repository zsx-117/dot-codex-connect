---
name: dot-codex-connect
description: Prepare and troubleshoot the source-based, self-hosted Dot Codex Connect MCP service and Mac connector; explain architecture and evidence-backed limitations.
---

# Dot Codex Connect — from source

Use the full source repository: this Skill alone is not the server. The new source
is MIT-licensed with third-party notices; no purchase or Star is required.
Do not download or describe the old paid preview app as this open-source build.

1. Resolve the complete checkout with `bash scripts/setup-mac.sh --root`.
   The documented installation links this Skill to a full checkout. If a Skill
   manager copied only this folder, clone `https://github.com/zsx-117/dot-codex-connect.git`
   into a new directory and set `DOT_CODEX_SOURCE` to that absolute path. Never
   overwrite an existing checkout. Resolve the documentation links below against
   the original `skills/dot-codex-connect/` in that checkout.
   Read [self-host setup](../../docs/self-hosting.md). Run
   `bash scripts/setup-mac.sh --check` from this Skill directory. It only checks
   interpreter versions and source presence; it does not inspect accounts.
2. Run `bash scripts/setup-mac.sh --test` for isolated synthetic tests. Report
   failures as they occur. Passing fixtures does not prove a real Dot connection.
3. Configure the operator's own HTTPS host, separate MCP/device credentials and
   private state directories using `selfhost/.env.example`. The template is inert.
   Never copy keys or account bindings from an existing commercial installation.
   Starting the local server needs no paid entitlement service. Do not change a
   hosted service, billing or existing connector while preparing this checkout.
4. For an explicitly requested real connection, follow the account-binding step
   in the setup document, then run the source connector in the foreground.
   Enrollment reads the signed-in account through AppServer, not auth files.
   Keep local state isolated; never replace an existing binding automatically.
5. Configure the supported client authentication mode. Static Bearer mode and
   OAuth resource validation are separate. For OAuth read [OAuth setup](../../docs/oauth.md):
   the operator supplies their own issuer, approved client and exact callback;
   resource discovery and JWT verification are implemented, but real Dot login
   remains unverified. Do not register clients, grant extra scopes or invent URLs
   merely to complete preparation.
6. Verify service health, device heartbeat and account binding separately. Do not
   read chats or send a test task unless the user's request authorizes that action.
   For unknown send outcomes, query the original request ID; never auto-resend.

When explaining implementation, read [architecture and protocol](../../docs/architecture.md).
For failures, read [verified development record](../../docs/development-history.md)
and [security and release boundaries](../../docs/security.md). Distinguish newly
reproduced tests, historical reports, and unknown production behavior. Never
invent development stories or publish private request bodies to illustrate them.
