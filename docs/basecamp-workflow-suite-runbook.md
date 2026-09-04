# Testing the workflow suite inside basecamp

A runbook for building `workflow_registry`, `workflow_engine`,
`workflow_scheduler` and `workflow_canvas` into a local
[logos-basecamp](https://github.com/logos-co/logos-basecamp) checkout and
verifying the whole stack together: palette discovery, node execution, and
(manually) deployment.

Every step here was run and verified while writing this doc — the commands
are not aspirational.

---

## Before you start

**Memory.** A basecamp build pulls in a lot of Nix derivations, and
`nix.conf`'s default `max-jobs = auto` launches as many parallel builds as
you have cores, each multi-threaded. On a 20-core / 31 GB machine that is
enough to exhaust RAM and the swap behind it and crash the session — this
happened once while developing this suite. Pass `--max-jobs 1 --cores 4` (or
similar) to every `nix build` below, especially the first one, which is
uncached. Once the Nix store is warm, later builds are much cheaper and the
limit matters less.

**A separate worktree, not your main basecamp checkout.** If you use
basecamp for other local experiments (a different module's local bake-in,
an in-progress upstream change), don't edit that checkout's `flake.nix`.
Local-only wiring like this is genuinely local — uncommitted, easy to lose
track of, and two different local experiments editing the same
`flake.nix`/`flake.lock` will fight each other. A `git worktree` gives you
an isolated copy that shares history with your main checkout but has its own
working tree:

```bash
cd /path/to/logos-basecamp
git worktree add ../logos-basecamp-workflow-suite origin/master
cd ../logos-basecamp-workflow-suite
```

Everything below assumes you're inside that worktree. Tear it down when
you're done:

```bash
cd /path/to/logos-basecamp
git worktree remove ../logos-basecamp-workflow-suite
```

**Local clones of the four modules.** This runbook wires basecamp to your
local checkouts via `git+file` inputs — no need to push anything first, and
edits to a module take effect on the next `nix build` without a round trip
through GitHub. Adjust the paths below to wherever you keep them; this
assumes the layout `corpetty/logos-workflow-{registry,engine,scheduler,canvas}`
next to each other.

---

## 1. Wire the four modules into basecamp

Open the worktree's `flake.nix`. Find the closing `};` of the `inputs`
block (search for `nix-bundle-macos-app`, the last input before it) and add:

```nix
    # LOCAL-ONLY workflow-stack bake-in — not for commit. `follows` so ONE
    # copy of each module is in the closure: the engine, scheduler and canvas
    # each declare the ones below them, and without this the canvas would
    # drag in a second registry/engine/scheduler from github.
    workflow_registry.url = "git+file:///path/to/logos-workflow-registry";
    workflow_engine = {
      url = "git+file:///path/to/logos-workflow-engine";
      inputs.logos-workflow-registry.follows = "workflow_registry";
    };
    workflow_scheduler = {
      url = "git+file:///path/to/logos-workflow-scheduler";
      inputs.logos-workflow-engine.follows = "workflow_engine";
    };
    # The canvas is a legacy in-process ui widget, not a ui_qml module, so it
    # keeps its own derivation and has no workflow-module inputs to follow —
    # it reaches the three modules at runtime through LogosAPI, not at build
    # time through generated wrappers.
    workflow_canvas.url = "git+file:///path/to/logos-workflow-canvas";
```

Find the `outputs = { self, nixpkgs, ... }:` line and add
`workflow_registry, workflow_engine, workflow_scheduler, workflow_canvas`
to the end of its parameter list, right before the closing `}:`.

Find where `installedDev` and `installedDistributed` are defined (search for
`installedDev = map installDev`) and, right after them, add:

```nix
          # LOCAL-ONLY workflow-stack bake-in. `.install` outputs are already
          # bundled module dirs (each module's own flake wires up the same
          # nix-bundle-logos-module-install bundler), so they go straight onto
          # installedModules the way a `.install` output does above, not
          # through installDev.
          workflowInstalls = [
            workflow_registry.packages.${system}.install
            workflow_engine.packages.${system}.install
            workflow_scheduler.packages.${system}.install
            workflow_canvas.packages.${system}.install
          ];
```

Then find the `app = import ./nix/app.nix { ... installedModules = installedDev; };`
block a few lines below and change `installedModules = installedDev;` to:

```nix
            installedModules = installedDev ++ workflowInstalls;
```

Lock and build:

```bash
nix flake lock
nix build --max-jobs 1 --cores 4 .# -L
```

The first build compiles all four modules plus QuickQanava (for the canvas)
from scratch — expect it to take a while, dominated by the canvas's Darwin
and Linux QuickQanava builds if you're also testing other platforms. On a
warm Nix store, subsequent builds of this same worktree are fast.

**Verify the layout** before launching:

```bash
ls result/modules/     # expect: workflow_registry workflow_engine workflow_scheduler (+ core infra)
ls result/plugins/     # expect: workflow_canvas (+ main_ui, package_manager_ui)
```

If either list is missing a module, the `installedModules` wiring above
didn't take — check the edit landed in the right spot and re-run
`nix build`.

---

## 2. Launch it

```bash
./result/bin/LogosBasecamp --user-dir /tmp/workflow-suite-test
```

`--user-dir` isolates this run's plugins/modules/logs from your normal
basecamp data directory, so you can blow away `/tmp/workflow-suite-test`
between runs without touching anything else.

For a headless run (no display, useful over SSH or for scripted checks),
set `QT_QPA_PLATFORM=offscreen` first. The app still starts an inspector
server on `localhost:3768` you can drive from a script (§5).

Check the log for the startup sequence:

```
Logos Core started successfully!
Module loaded: package_manager
Module loaded: package_downloader
```

The four workflow modules are **not** in this early log — they load lazily,
triggered by opening a UI plugin that declares them as a dependency (the
canvas). That's expected, not a problem.

---

## 3. Open the canvas and check the palette

In the sidebar, click **Workflow Canvas**. Watch the log:

```
Module loaded: workflow_registry
Module loaded: workflow_engine
Module loaded: workflow_scheduler
```

then a line per introspected module, e.g.:

```
[workflow_registry] package_manager live: 37 methods, 14 events
[workflow_registry] package_downloader live: 10 methods, 1 events
```

A module that's installed but not currently loaded (nothing else has
triggered it) shows up too, marked `installed, not live` rather than being
silently dropped — that's the registry's 1.5-second introspection deadline
doing its job, not a failure.

In the canvas UI itself:

- The top-right badge should read **CONNECTED**, not OFFLINE.
- The **Node Palette** on the left should be populated — one entry per
  introspected method (colored by source module), plus the built-in
  Utility/Flow/Transform/Trigger nodes.
- Double-click a palette entry to drop it on the canvas; drag from an output
  port to an input port to wire two nodes together.

If the badge reads OFFLINE and the palette is empty, `workflow_registry`
either isn't loaded or its palette build failed — check the log for a
`[workflow_registry]` line with an error, and confirm `result/modules/`
actually contains it (§1).

---

## 4. Run a workflow

Build a small graph (e.g. a `String` utility node feeding a `Display` node,
or a real module-method node from the palette), then click **▶ Run**. The
result panel at the bottom should populate with the engine's JSON response:

```json
{"executionId":"exec_1_...","success":true,"steps":N,"skipped":0,"errors":[],"nodeResults":{...}}
```

`success: true` with your node's output in `nodeResults` confirms the full
chain: canvas → `workflow_engine.executeWorkflow` → back to the canvas,
which paints the result onto the graph.

**Save/Load**: type a name in the toolbar field and click **💾 Save**; use
`listSavedWorkflows`/`loadWorkflow` (or just reopen the canvas and check the
saved-workflows list) to confirm it persisted under the host's
`AppDataLocation`.

**Deploy**: deploying to the scheduler isn't wired to a canvas button today
— it's called via `CanvasWidget::deployWorkflow(id, json)`, reachable from a
script (§5) or by extending the toolbar. Once deployed:

```bash
# List what's deployed
curl -s http://localhost:8081/webhooks/  # scheduler's webhook listener, if the workflow has a webhook trigger
```

or watch the log for `[workflow_scheduler] deployed workflow: <id>` and,
for an interval/cron trigger, for it firing on schedule.

---

## 5. Scripted checks (optional)

Basecamp ships a Qt object inspector (`logos-qt-mcp`) for driving the UI
from a script — useful for repeatable smoke checks without clicking through
the app by hand every time.

Build it once (or reuse an already-built one — check
`nix path-info .#logos-qt-mcp 2>/dev/null` in any basecamp checkout that's
built it before; it's a plain Nix store path, portable across worktrees of
the same repo):

```bash
nix build --max-jobs 1 --cores 4 .#logos-qt-mcp -o result-mcp
```

Minimal smoke test — save as `smoke-test.mjs`:

```js
import { resolve } from "node:path";
const qtMcpRoot = process.env.LOGOS_QT_MCP || resolve(process.cwd(), "result-mcp");
const { test, run } = await import(resolve(qtMcpRoot, "test-framework/framework.mjs"));

test("workflow canvas loads and talks to the registry", async (app) => {
  await new Promise((r) => setTimeout(r, 3000));
  await app.click("Workflow Canvas", { exact: true, type: "SidebarAppDelegate" });
  await app.waitFor(
    async () => { await app.expectTexts(["LOGOS LEGOS"]); },
    { timeout: 30000, interval: 1000, description: "canvas UI to load" }
  );

  const status = await app.getPropertyByType("CanvasWidget", "connectionStatus");
  if (status !== "connected") throw new Error(`connectionStatus: ${status}`);

  const before = await app.getPropertyByType("CanvasWidget", "lastExecutionResult");
  await app.click("▶ Run", { exact: true });
  await new Promise((r) => setTimeout(r, 4000));
  const after = await app.getPropertyByType("CanvasWidget", "lastExecutionResult");
  if (after === before) throw new Error("Run did not produce a new execution result");

  console.log("execution result:", after);
});
await run();
```

Run it against an already-running instance:

```bash
QT_QPA_PLATFORM=offscreen ./result/bin/LogosBasecamp --user-dir /tmp/workflow-suite-test &
sleep 18   # give it time to reach the inspector's listening state
node smoke-test.mjs
```

or let the harness launch and tear down the app itself:

```bash
node smoke-test.mjs --ci ./result/bin/LogosBasecamp
```

**Known limitation, not a bug in these four modules**: the inspector's
`evaluate` command always runs against the *first* `QQuickWidget`'s QML
engine regardless of which `objectId` you pass it (each UI plugin gets its
own sandboxed engine, and `evaluate`'s engine lookup doesn't account for
that) — so it can't reach the canvas's own QML context properties (like
`graph`) once more than one plugin is open. `callMethod`, used above,
resolves the target object directly and doesn't have this problem, but it
can only invoke zero-argument methods — its argument marshalling
(`Q_ARG(QVariant, ...)`) doesn't match a method's real declared parameter
type, so a call with any argument (even a plain `QString`) fails with
`"Failed to invoke '<method>'"`. That rules out driving `insertWorkflowNode`
or `loadFromJson` from a script; building and running a graph with actual
nodes needs the interactive UI (§3–4) for now.

---

## Troubleshooting

**Canvas click does nothing — module dependencies load, then silence, no
error.** Almost always the plugin failed to `dlopen`. Check:

- `nm -D --defined-only result/bin/.LogosBasecamp | wc -l` — if this is
  non-zero for your basecamp build, the host now exports symbols and the
  canvas's explicit host-runtime linking (`CMakeLists.txt`, search
  `Linking host runtime soname`) may need revisiting; if it's zero as
  expected, the plugin must declare `liblogos_qt_host`/`liblogos_protocol`
  as `NEEDED` itself.
- `ldd result/plugins/workflow_canvas/workflow_canvas.so 2>&1 | grep "not found"`
  — anything listed here (most often `libQuickQanava.so`) means the
  plugin's RPATH doesn't reach its own bundled copy; confirm
  `result/plugins/workflow_canvas/` actually contains `libQuickQanava.so`
  and a `QuickQanava/` directory beside `workflow_canvas.so`.

**Palette stays empty / badge stuck OFFLINE, but no error in the log.**
Check for a `RemoteTransportConnection: no listener at "local:logos_<mod>_..."
will block up to Nms and then fail` line — that's the registry hitting an
installed-but-unloaded module. It should resolve in ~1.5s per such module
and continue; if the app looks hung for much longer than that, something
downstream of the registry (not this discovery path) is blocking.

**`nix build` OOMs or the machine becomes unresponsive.** See "Memory"
above — you're almost certainly running with the default `max-jobs`. Kill
the build, add `--max-jobs 1 --cores 4`, retry.

**A `.lgx` release build fails with `cp: cannot stat '.../liblogos_qt_host.so':
Too many levels of symbolic links`.** This exact failure happened once
during this suite's release and is now fixed
(`logos-workflow-canvas@adab00a`) — if you see it again after modifying
the canvas's linking, run `nix-store -q --references` on the built
`workflow_canvas` derivation and confirm `logos-liblogos` isn't in it. If
it is, something is linking against an absolute Nix store path to one of
the host-provided libraries again instead of using the `-l:<soname>` +
link-only `-L` pattern in `CMakeLists.txt` — that absolute-path link is
exactly what pulls `logos-liblogos` into the plugin's own closure, which a
portable `.lgx` then has to bundle whole, colliding with a second copy of
the same libraries already elsewhere in that closure.

---

## What's verified by this runbook, and what isn't

Confirmed working, by running exactly the steps above in a clean worktree:

- All four modules build and stage into `result/modules/` /
  `result/plugins/` correctly.
- The canvas loads, connects (`connectionStatus: "connected"`), and its
  palette populates from live module introspection.
- **Run** round-trips a workflow through `workflow_engine` and paints a
  real result back onto the canvas.

Not yet exercised by anything here — worth doing by hand if you're
validating a change to that path specifically:

- Inserting a *specific* node type and wiring it into a multi-node graph
  before running (§5's scripted-check limitation) — do this by hand in the
  UI.
- The scheduler's cron/interval/webhook triggers actually firing on
  schedule.
- Deploying from the canvas UI itself — there's no toolbar button for it
  yet; `deployWorkflow` is reachable only from `CanvasWidget`'s API.
