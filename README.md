# Dot Codex Connect

Connect an MCP client to Codex conversations on your own Mac: discover threads, read them with permission, send tasks, retrieve actual replies, and track execution separately from delivery receipts.

**MIT-licensed source preview, maintained by zsx-117.** Run the core on your own Node/SQLite service without a purchase gate, payment service, website analytics, or private hosting dependency. Real Dot login and end-to-end operation have not been validated. This is not a production-ready, plug-and-play release.

## Start from source

Requires Node 24+ and Python 3.12+. No npm or pip packages need to be installed. Clone the full repository first:

```sh
git clone https://github.com/zsx-117/dot-codex-connect.git
cd dot-codex-connect
```

Run these commands from the repository root:

```sh
bash skills/dot-codex-connect/scripts/setup-mac.sh --check
bash skills/dot-codex-connect/scripts/setup-mac.sh --test
python3 scripts/build-source.py --output ./connector-source.zip
```

The last command builds an inspectable, reproducible Python source archive, not the old prebuilt app. See the [self-hosting guide](docs/self-hosting.md) for service startup, Mac account binding, and identity configuration. The [installation Skill](skills/dot-codex-connect/SKILL.md) requires the full checkout.

## Install as a Codex Skill

Run this from the repository root you cloned above. A symbolic link keeps the Skill connected to the full server, connector, and documentation sources:

```sh
skill_dir="${CODEX_HOME:-$HOME/.codex}/skills/dot-codex-connect"
mkdir -p "$(dirname "$skill_dir")"
if [ -e "$skill_dir" ] || [ -L "$skill_dir" ]; then
  echo "Target already exists; installation stopped. Inspect the existing Skill first." >&2
else
  ln -s "$PWD/skills/dot-codex-connect" "$skill_dir" &&
    bash "$skill_dir/scripts/setup-mac.sh" --check
fi
```

Invoke `$dot-codex-connect` in a new Codex session. Keep the linked checkout in place. Installation does not replace the old `dot-codex-install` Skill or start a service. If another Skill manager copies only the Skill folder, clone the full repository separately and set `DOT_CODEX_SOURCE` to its absolute path. The Skill is not a standalone server binary.

## Repository contents

| Path | Contents |
|---|---|
| `selfhost/` | Node/SQLite service, static-token or OAuth resource-server validation, configuration, and tests |
| `service/app/{mcp,agent}`, `service/lib` | MCP routes, task queue, events, receipts, and single-user access control |
| `service/connector/src` | Python connector, durable recovery, local AppServer RPC, and official queue support |
| `service/drizzle` | Core schema for an empty database; no payment/customer tables or data |
| `service/tests`, `scripts` | Synthetic tests, deterministic source packaging, and build verification |
| `skills`, `docs` | Installation, architecture, protocol, licensing, development evidence, and limitations |

The core excludes commercial payment/analytics modules, the old website template and its dependencies, runtime state, production configuration, old app packages, and original Git history. None is required to run the core. Private local backups have been preserved.

## OAuth and supported scope

The service supports single-user static Bearer authentication and RS256 access tokens issued by an independent OAuth authorization server. OAuth mode provides MCP resource discovery and validates issuer, audience, subject, client, scope, token lifetime, and signature. It does not provide a paid identity service or automatically register clients. You can use a self-hosted authorization server; see [OAuth setup and Dot validation](docs/oauth.md).

Source-level protocol and synthetic route tests pass. Real Dot callbacks, client registration, and login have not been verified. Support is limited to a single user, outbound connections from a Mac, and headless capabilities. Desktop computer-control capabilities and approval permissions are not inherited.

Request acceptance, queue acceptance, target receipt, execution completion, webhook receipt, and client ACK are separate states. If a send outcome is unknown, query the original requestId instead of automatically resending. See [architecture](docs/architecture.md), [development history](docs/development-history.md), and [validation status](docs/validation.md).

## Contributing and licensing

Original code and documentation are licensed under [MIT](LICENSE), using the public contributor identity `zsx-117`. [Third-party notices](THIRD_PARTY_NOTICES.md) describe source provenance and components that are not bundled.

Contributions of reproducible issues, tests, and documentation are welcome. Do not submit real conversations, keys, device identifiers, or transaction data. If this project helps you, a Star can help others find it. Starring is never required to use or contribute to the project.
