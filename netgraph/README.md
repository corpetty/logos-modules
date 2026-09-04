# netgraph — moved to its own repository

The `netgraph` module (a live connection observer for Logos Basecamp) now lives
in its own repository, as the catalog convention requires (every module is a git
submodule under `submodules/`):

**https://github.com/corpetty/netgraph-module**

- `module/` — `netgraph_module`, the backend collector. M0 (Collector A: socket
  table + ancestry pid discovery) and Collector B (core_service attribution +
  connection_source provider bind) are built and unit-tested there.
- `ui/` — `netgraph_ui`, the QML graph view (later, M2).
- `DESIGN.md` — architecture, the openmetrics patterns copied, the process-tree
  attribution finding, and milestone status.

## Integrating into this catalog

When the module is ready to publish, add it as a submodule and generate its
release workflow with the helper:

```bash
./scripts/add-module.sh https://github.com/corpetty/netgraph-module
```

The pipeline builds one module per `metadata.json` directory, so a repo with
`module/` (and later `ui/`) is handled the same way `muster` is
(`submodules/muster/module` + `.../ui`).

This directory previously held a staging scaffold; it was migrated to the
repository above so there is a single source of truth.
