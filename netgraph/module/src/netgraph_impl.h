#pragma once

// netgraph — a universal (pure-C++) Logos module that observes, in real time,
// every network connection the running Logos process tree holds, grouped by the
// service that opened it and the network it belongs to. Scope is the whole
// process tree: DNS lookups, plain HTTPS to a bootstrap host, and RPC endpoints
// all appear. Nothing is hidden.
//
// It declares an interface dependency on `connection_source` (the
// collectConnections() contract, see interfaces/connection_source.h) rather than
// on any concrete module, and binds that interface to each operator-configured
// module name at runtime. This is what lets it ship before any module implements
// the other side (Collector B degrades to nothing).
//
// No Qt here. The collection sweep runs on a timer thread and performs
// inter-module IPC through the bound wrappers; the SDK's LogosAPIClient marshals
// that IPC onto the module's main/event-loop thread (see logos_thread_marshal.h),
// exactly as openmetrics' HTTP-thread scrape does. The impl header stays free of
// the generated logos_sdk.h — the generator parses it and expects plain C++.
//
// SKELETON. The collector is not wired here yet (see the private section and
// collector.h): the handoff's first step is to propose this skeleton and the
// connection_source header before writing the collector.

#include <cstdint>
#include <mutex>
#include <string>
#include <vector>

#include <logos_module_context.h>  // LogosModuleContext base (gives modules())

// The set of connection_source providers to enrich against, from setEnabled()
// config. Empty is valid: Collector A alone produces a real graph.
struct EnrichSource {
    std::string name;
};

class NetgraphImpl : public LogosModuleContext {
public:
    NetgraphImpl() = default;
    ~NetgraphImpl();

    // The explicit user switch. Collection is OFF until turned on — this module
    // sees the complete connection graph of the host, a surveillance surface, so
    // it collects nothing until enabled (handoff constraint: off by default,
    // behind an explicit switch, local only).
    //
    // Config JSON:
    //   { "enabled": true,
    //     "sweep_ms": 1000,                       // default 1000; min clamped
    //     "sources":  ["blockchain_module", ...], // connection_source providers
    //     "include_host": true }                  // include basecamp/ui-host sockets
    //
    // enabled=true starts the sweep timer; enabled=false stops it and drops the
    // cached snapshot (nothing retained while off). Returns 1 on a state change,
    // 0 on no-op or bad config.
    int64_t setEnabled(const std::string& configJson);

    // The direct-call snapshot: the last completed sweep's merged connection
    // array as JSON. The UI polls this and never opens a socket of its own
    // (openmetrics' scrape() analogue). Never blocks on a live sweep — it returns
    // the cached result under the lock.
    //   { "enabled": bool, "swept_at": <unix ms>,
    //     "connections": [ <record>, ... ] }
    // <record> is the handoff connection shape: id, pid, module, network,
    // transport, direction, local, remote, peer_id, state, opened_at, bytes.
    // module/network/peer_id are nullable BY DESIGN — an unlabelled row is shown.
    std::string snapshot();

    // Status: { enabled, sweeping, sweep_ms, sockets, attributed, derived,
    //           sources: [...] }.
    std::string getInfo();

private:
    // ---- wired at M0; skeleton only ----
    // The timer-thread sweep body: Collector A (socket table) is authority for
    // existence; Collector B (bound connection_source providers) supplies labels;
    // merge on (pid, local port, remote endpoint); publish the snapshot under the
    // lock. A module with no matching socket becomes a derived edge, marked.
    void sweepOnce();  // TODO(M0): implement over collector.h + bound sources.

    std::mutex  m_mutex;
    bool        m_enabled = false;
    int         m_sweepMs = 1000;
    bool        m_includeHost = true;
    std::vector<EnrichSource> m_sources;

    // Cache served by snapshot(). Empty, valid document until the first sweep.
    std::string m_snapshot = R"({"enabled":false,"swept_at":0,"connections":[]})";
    // TODO(M0): std::unique_ptr<netgraph::ISocketTable> m_sockets; + timer handle.
};
