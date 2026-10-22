# Licensing and attribution

The root MIT license names **zsx-117 and contributors**, using the public account identity authorized by the maintainer rather than adding a real name or email address. It covers the original connection core, adapter code, synthetic tests, and documentation in this package. It does not relicense third-party products, runtimes, or the old app.

## Source provenance and distribution scope

The connection core was extracted from service Git commit `e5fc9f80df007c703c014638f0dd08af2ebd22ec`. Git records show the MCP/agent/bridge code entering the project in `edc0d4c` (2026-10-06), the events library in `0c0d1594` (2026-10-07), and the distributed connector source in `551e2b77` (2026-10-10). These records establish version provenance; Git history alone is not independent proof of the copyright chain.

The original project also included Sites/React UI templates, build plugins, and many frontend dependencies. The discovered `sites-vite-plugin.LICENSE` is an OpenAI MIT license, but it cannot establish the license of every template. The second core package removed the entire website template, build plugins, frontend lockfiles, and dependencies. Their original files and licenses remain in private local backups. They are neither distributed nor loaded by this source build or runtime, so template attribution is no longer an unresolved dependency of the core package.

No source from `Fanch-hui/codex-bridge` was copied. Third-party evaluations are not used as evidence of this project's license or validation. Commercial checkout and analytics reference modules are also excluded from the core package.

## Runtimes and optional external systems

The package uses Node's built-in HTTP/crypto/SQLite modules and the Python standard library. It does not bundle Node, Python, SQLite, Codex CLI, CA certificate packages, npm/pip packages, or a signed app. Those systems retain their own licenses and trademark rights; the project's MIT license does not replace them.

Operators choose and host their own OAuth authorization server. Keycloak is mentioned only as a configuration option; its program and license text are not copied or distributed here. The authorization server, HTTPS proxy, and Codex remain subject to their respective licenses.

The old public installer's limited license and the old paid app do not establish a corresponding build of this MIT source. This release provides an inspectable source execution path; it does not relicense or relabel the old app.

The MIT text follows the [OSI MIT License](https://opensource.org/license/mit). Starring the repository is never a license condition.
