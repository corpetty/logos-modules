#include "netgraph_impl.h"

#include <cstdint>

#include <logos_json.h>  // LogosMap

// Generated at build time by logos-cpp-generator. Defines `LogosModules` with
// the `bind_connection_source(moduleName)` factory (because metadata.json
// declares an interface_dependency on `connection_source`). Included only in the
// .cpp so the impl header the generator parses stays free of codegen types.
//
// TODO(M0): #include "logos_sdk.h"  — enable when the sweep binds providers.

// SKELETON. setEnabled/getInfo manage state and config; snapshot() serves the
// cached document. sweepOnce() — the socket-table collector, the bound-source
// enrichment, and the merge — is the M0 work and is intentionally not here yet.
// See collector.h for the platform seam these methods will drive.

NetgraphImpl::~NetgraphImpl() {
    // TODO(M0): stop the sweep timer and join the collector thread.
}

int64_t NetgraphImpl::setEnabled(const std::string& configJson) {
    std::lock_guard<std::mutex> lock(m_mutex);

    LogosMap cfg;
    try {
        cfg = LogosMap::parse(configJson);
    } catch (...) {
        return 0;
    }

    const bool enable = cfg.value("enabled", false);

    int sweepMs = cfg.value("sweep_ms", m_sweepMs);
    if (sweepMs < 250) sweepMs = 250;  // never hammer the socket table
    m_sweepMs = sweepMs;

    m_includeHost = cfg.value("include_host", m_includeHost);

    m_sources.clear();
    if (cfg.contains("sources") && cfg["sources"].is_array()) {
        for (const auto& s : cfg["sources"]) {
            if (s.is_string() && !s.get<std::string>().empty()) {
                m_sources.push_back({s.get<std::string>()});
            }
        }
    }

    if (enable == m_enabled) return 0;  // no state change
    m_enabled = enable;

    if (!m_enabled) {
        // Off: retain nothing.
        m_snapshot = R"({"enabled":false,"swept_at":0,"connections":[]})";
        // TODO(M0): stop the sweep timer.
    } else {
        // TODO(M0): start the sweep timer at m_sweepMs; first sweepOnce() populates
        // the cache. Until the collector lands, the snapshot stays the empty doc.
        m_snapshot = R"({"enabled":true,"swept_at":0,"connections":[]})";
    }
    return 1;
}

std::string NetgraphImpl::snapshot() {
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_snapshot;  // last completed sweep; never blocks on a live one
}

std::string NetgraphImpl::getInfo() {
    std::lock_guard<std::mutex> lock(m_mutex);
    LogosMap info;
    info["enabled"] = m_enabled;
    info["sweeping"] = false;  // TODO(M0): true while a sweep timer is running
    info["sweep_ms"] = m_sweepMs;
    info["include_host"] = m_includeHost;
    info["sockets"] = 0;       // TODO(M0): last sweep socket count
    info["attributed"] = 0;    // TODO(M0): rows with a non-null module
    info["derived"] = 0;       // TODO(M0): derived edges (no matching socket)
    LogosMap sources = LogosMap::array();
    for (const auto& s : m_sources) sources.push_back(s.name);
    info["sources"] = std::move(sources);
    return info.dump();
}

void NetgraphImpl::sweepOnce() {
    // TODO(M0):
    //   auto rows = m_sockets->enumerate(pidsFromLogosStats(m_includeHost));
    //   for each source in m_sources:
    //       payload = modules().bind_connection_source(source.name).collectConnections();
    //       (empty/error payload => skipped, one bad provider never breaks a sweep)
    //   merge on (pid, local port, remote endpoint); unmatched module rows =>
    //     derived edges, marked; publish the merged document to m_snapshot.
}
