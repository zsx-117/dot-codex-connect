# Verifiable development history and lessons learned

Evidence levels: **reproduced here** means synthetic tests against this candidate; **historical report** means an independent acceptance document that was actually reviewed; **source evidence** establishes only what the code implements; **unknown** must not be described as fixed. Private conversations, original requests, and real events have not been exported.

## Reviewed historical evidence

| Version/evidence | Finding, response, and evidence limits |
|---|---|
| Independent r3 report, 2026-10-10; service `1e09b5669c3bc662fa5ae217f91c1ca09f363f50`, MCP 0.2.9 / Mac 0.2.4 | Records bounded retests passing for the original P1 unrelated-turn overwrite and P2 wait cancellation/deadline issues. Fifty concurrent requests with a stable requestId produced one job. This does not establish safety under every production interleaving. |
| The same r3 report | After a lost start response, a complete turn/completed event containing items could leave status completed but messages empty, with the terminal cache preventing recovery. One of seven boundary cases failed; the original assertion was retained. |
| Independent r4 report, 2026-10-10; `eaff596487b6cc95f92a9857bb766fe06bd26c3a`, MCP 0.2.10 / Mac 0.2.5 | Both original F3 harnesses passed without changing assertions. Replies were extracted from exactly matching completed-turn items, deduplicated, and kept in order; error markers and unrelated threads did not supply reply bodies. The selected six tests/nine scenarios passed. The pass did not rerun every regression or test a real network outage. |
| r3 catch-up priority tests | Newly completed, input-needed, and approval results took priority over old backlog. Batches were limited to six entries and an eight-second budget; failures were not recorded as successes. The 153-second backlog was a simulated RPC example, not an observed real network outage. |
| Reports of `turnId` versus `turn.id` conflicts in 0.2.11 | An author-reported fix and newer source were available, but there was insufficient independent evidence of a full regression run for that version. r4 covered one class of top-level/nested conflict; that cannot be generalized to every 0.2.11 interleaving. |
| Exported service source `e5fc9f80df007c703c014638f0dd08af2ebd22ec` (2026-10-13) | The source contains an MCP 0.3.2 marker and a connector-entry 0.3.1 marker. The differing internal versions are a recorded fact, not grounds for inventing a unified release number. |

The reports can be checked against paths and SHA-256 hashes in the private local review manifest. Public documentation excludes machine-specific absolute paths and original business messages. A separate evaluation of `Codex Bridge 2.0.1` is third-party research, not evidence of this project's validation, source ownership, or license. Its source was not copied into this candidate.

## Design lessons supported by the code

1. Stable IDs and immutable payloads address duplicate requests. Merely labeling a tool idempotent does not prevent duplicate turn/start calls after a disconnect.
2. Persist startIntent before writing, and use read-only recovery when the response is unknown. A queue's accepted response does not mean the conversation received the request.
3. Correlate thread, turn, and userMessage markers together. Do not take a reply from an arbitrary most recently completed turn.
4. A wait deadline must also bound database and authorization queries. Cancelling a wait does not cancel the original task.
5. Persist webhook receipt, ACK, and execution replies separately. A late failure must not undo a delivered or acknowledged result.
6. Pause on account changes instead of silently rebuilding the binding. Recheck executable paths after CLI upgrades rather than reusing an obsolete app path.

Corresponding synthetic assertions are in `service/tests/`. Whether the current code holds these guarantees across every real CLI/desktop version remains unknown.

## Findings from open-source preparation, not historical product incidents

- Original service authentication and paid entitlements depended on the hosted platform. Replacing a license file alone did not make it self-hostable. An independent single-user entry point was added, reusing the actual libraries with a SQLite adapter for the D1 interface. Tests with external fetch forbidden passed.
- The first test runner lacked `if __name__ == '__main__'`. Mac multiprocessing spawn recursively ran the runner and failed. Adding the entry-point guard allowed both Python source copies to pass 47 tests each.
- The first source allowlist excluded a checkout integration module, causing test imports to fail. Only that source module was restored at that stage; production snapshots and operational analytics scripts stayed excluded.
- Email redaction changed literal identities but missed dynamically constructed fixture addresses, causing five historical commercial tests to fail. Synthetic identity mapping was made consistent while preserving assertions and business branches. This was a redaction-tool issue, not evidence of a product incident.
- The old installer had a license limited to installation files, not MIT. The new entry point removes the old Skill's purchase gate, prebuilt downloads, and restriction on explaining private implementation details. The old app's signing, complete correspondence to source, and reproducible build remain unverified.

Early design motivations, undiscovered implementation details, actual incident frequency, attribution of every contributor, and production/customer circumstances remain unknown. No stories are invented to fill those gaps.

## Second preparation pass (2026-10-22)

- Payment modules, analytics, platform website templates, and frontend dependencies were moved into private local backups. The independent access module and core SQL no longer contain entitlement queries, paid pairing, or customer tables. All six cloud regression groups still passed.
- Original open-source work is attributed to the public account `zsx-117`. Template attribution concerns were resolved by excluding and not loading those templates, not by treating one plugin's MIT license as covering every starter file.
- OAuth resource metadata and audience/identity/client/scope/time/signature validation were added. Eight self-hosting and OAuth synthetic tests passed. These include new tests from this preparation, not fixes for previously observed real login incidents.
- Deterministic connector source packaging was added. Two builds had identical contents and archive hashes. A self-check subprocess passed after extraction, without reading a real account. Source versions carry `+oss.1`; they are not claimed to reproduce the old signed app.
- The first real loopback HTTP attempt at listen(127.0.0.1, 0) was denied with sandbox EPERM. After explicit user approval, one retry through the supported approval process passed the synthetic HTTP test and closed the listener. No firewall, proxy, or production configuration was changed. This does not establish real Dot/HTTPS/Mac/ACK end-to-end validation.

## Historical report hashes

These SHA-256 hashes identify the independent reports actually reviewed. The originals contain local paths and are not distributed. The public account contains only findings and evidence limits, without original conversations or requests.

- `independent-acceptance-final.md`: `a4a6cbf28087cc66c0858cd91d834aceab8c6cad805fa151ff0a6c6fe91f7526`
- `independent-acceptance-f3.md`: `73e3fef904621899a696e3c0920d5a7554431d77c3635dc25d074d0f51a3b679`

A final dependency review found that the old webhook code automatically queried a fixed external DNS service in Fake-IP environments. The core now uses only the operator's system DNS and rejects non-public addresses. A new synthetic test verifies that it does not automatically query an external resolver. The Python test count is now 48.
