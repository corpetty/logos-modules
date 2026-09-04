# netgraph — skeleton proposal

Status: skeleton and interface, before the collector. This is the handoff's
first step — read `openmetrics-module` in full, then propose the `netgraph_module`
skeleton and the `connection_source` header. No collector, no classifier, no UI.

What was read: `logos-co/openmetrics-module` at `5dbca24` — README, `metadata.json`,
`interfaces/metrics_source.h`, `src/openmetrics_impl.{h,cpp}`, `src/openmetrics_format.*`,
`CMakeLists.txt`, `flake.nix`, and `doctests/openmetrics.test.yaml`. Also the two-part
(core + ui) packaging in `corpetty/muster` (`module/` and `ui/` `metadata.json`).

## Files in this proposal

```
netgraph/
  DESIGN.md                         this document
  module/                           netgraph_module (the observer)
    metadata.json                   interface: universal; interface_dependencies: connection_source
    CMakeLists.txt                  logos_module(NAME netgraph ...)
    flake.nix                       mkLogosModule, builder pinned 0.2.5
    interfaces/
      connection_source.h           the collectConnections() contract (M3), proposed now
    src/
      netgraph_impl.h               module surface: setEnabled / snapshot / getInfo
      netgraph_impl.cpp             surface + state; sweepOnce() is a marked stub
      collector.h                   the platform-split socket-table seam (ISocketTable)
```

Not here yet, by design: the socket-table bodies (`linux_socket_table.cpp`,
`macos_socket_table.cpp`, `fake_socket_table.cpp`), the classifier (M1), the QML
plugin `netgraph_ui` (M2), the CDDL schema and reference provider (M3).

## What is copied from openmetrics, and the netgraph mapping

| openmetrics | netgraph | why |
|---|---|---|
| `interface_dependencies: metrics_source`, bound at runtime to operator-named modules | `interface_dependencies: connection_source`, same binding | ships before any provider exists; Collector B degrades to nothing |
| convention method `collectMetrics()` | convention method `collectConnections()` | a module opts in with one method; missing/broken module is skipped |
| pure-C++ `universal` module, no Qt; `logos_sdk.h` only in the `.cpp` | same | the generator parses the impl header and expects plain C++ |
| worker thread → IPC marshaled to the owner thread by the SDK | timer (sweep) thread → same marshaling | our collector runs off the event loop; the handoff calls this out |
| `scrape()` direct-call method the UI/debug reads | `snapshot()` direct-call method the UI polls | the UI never needs a socket of its own |
| one bad module never breaks a scrape | one bad provider never breaks a sweep | same guarantee |
| literate doctest under `logoscore`: build providers inline, run, assert | M0 doctest: open a known connection, see it in `snapshot()` | end-to-end proof on the commit under test |

What is deliberately NOT copied: connections do not go into `collectMetrics()`.
Per-peer labels blow up Prometheus cardinality — that is the reason this is a
separate interface, not a metrics family. openmetrics is consumed instead as an
optional cross-check (below).

## Module surface, and where it differs from openmetrics

Three methods, all pure C++, all on `LogosModuleContext`:

- `setEnabled(configJson) -> int64` — the explicit user switch. openmetrics has
  no equivalent; netgraph needs one because it sees the host's complete
  connection graph, a surveillance surface inside a sovereignty app. Collection
  is off until turned on, and retains nothing while off. Config carries
  `sweep_ms`, the `sources` list (connection_source providers), and
  `include_host`.
- `snapshot() -> string` — the merged connection array, the last completed
  sweep, served from cache under the lock. Never blocks on a live sweep. This is
  the `scrape()` analogue.
- `getInfo() -> string` — `{enabled, sweeping, sweep_ms, sockets, attributed,
  derived, sources}`.

openmetrics' `start`/`stop` map onto `setEnabled` here: there is no HTTP server
to stand up, only a sweep timer to run, so one switch covers it.

## The two collectors and the merge (restated for the skeleton)

- Collector A, socket table (`collector.h`) — authority for a connection's
  existence. Platform-split behind `ISocketTable`, two real impls + a fake. Pids
  come from liblogos process stats, never from process-name matching. No
  `lsof`/`ss`/`netstat`.
- Collector B, module labels — the bound `connection_source` providers. Labels
  only; never creates a row.
- Merge key `(pid, local port, remote endpoint)`. A module row with no matching
  socket is kept as a derived edge and marked, not merged into a socket row.

Every row is shown even when `module`/`network`/`peer_id` are null — the
unlabelled rows are the point.

## Open questions — recommendations

1. **Sweep interval; push vs poll.** Module sweeps on its own timer and caches
   the latest snapshot; the UI polls `snapshot()` at ~1 Hz. This keeps the
   module free of UI coupling and mirrors openmetrics (the reader pulls a cached
   document). Default `sweep_ms` 1000, floor 250. Deltas are a later
   optimization, not M0. Rationale: the constraint "never block the module event
   loop on a sweep" is satisfied by a timer thread + a cached publish, and a poll
   needs no subscription machinery to land M0.

2. **Include the Basecamp host and `ui-host` sockets?** Include, marked as host
   (`include_host: true` default; rows tagged so the UI can filter). Consistent
   with "nothing is hidden." Making it a config flag lets an operator narrow to
   module subprocesses when the host noise gets in the way.

3. **Retention.** Snapshot-only through M0–M2. The M2 churn handling (hold a
   node a few seconds after its last socket closes, animate the decay) lives in
   the UI, not as module history. A bounded, opt-in rolling ring buffer for a
   timeline view is a later add and stays within the local-only constraint. Start
   with no history so there is less state to get wrong and less to retain on a
   surveillance surface.

## Handoff points to confirm before the collector

1. **Unconnected UDP breaks the merge key.** `/proc/net/udp` (and libproc) report
   no remote for a socket that never called `connect()` — some DNS resolvers work
   this way. Such a row has `(pid, local port, —)` and cannot key on a remote
   endpoint. Proposal: show it as a socket with a null remote (still a row), and
   never let it match a Collector B label by remote. QUIC over a connected UDP
   socket is fine. Confirm this is the intended handling.

2. **`id` is ephemeral, not persistent.** "stable hash of pid + local port +
   remote endpoint" is stable within a run, but pids recycle and ports are reused
   across runs, so the same `id` can name a different connection after a restart.
   Fine for a live view; flagging so nothing downstream treats `id` as durable.

3. **openmetrics cross-check is an optional, declared dependency.** Comparing a
   module's reported peer count against its socket count needs openmetrics
   running and configured. Under `--access-policy enforce` that is a concrete
   dependency netgraph must declare; it should be optional (absent openmetrics =
   no cross-check, not a failure). Confirm whether the cross-check is in scope for
   an early milestone or deferred.

4. **Access policy entries.** `netgraph_module` binds `connection_source`
   providers (declared via `interface_dependencies`, so allowed under enforce).
   `netgraph_ui -> netgraph_module` needs an explicit policy entry because
   `ui_qml` plugins are not tracked as dependents. Test under `enforce` from M0.

## Packaging / integration

This directory is a staging scaffold. The catalog builds each module from a git
submodule under `submodules/` (`release-all.yml` discovers `path = submodules/*`
in `.gitmodules`), so netgraph enters the pipeline by living in its own repo
(e.g. `corpetty/netgraph`, `module/` + later `ui/`, mirroring muster) and being
added with `scripts/add-module.sh`. A plain directory at the catalog root is not
picked up by CI — intentional while this is a pre-collector skeleton.

Build once extracted: `nix build .#lgx`; install with
`lgpm install --file` or Basecamp's Package Manager. Develop against a second
instance: `LogosBasecamp --user-dir /tmp/basecamp-ng`.

## Next step (M0)

Implement `collector.h` — the Linux `/proc` and macOS libproc socket tables and
the fake — wire `sweepOnce()` over it, take the pid list from liblogos process
stats, and prove it with a `logoscore` doctest: open a known connection, see it
appear in `snapshot()`. No UI. That milestone alone answers the original
question.
