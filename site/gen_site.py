#!/usr/bin/env python3
"""Generate modules.hackyguru.com — static catalog page for this repo.

Reads the catalog's index.json (as published in the `index` release) and
logos-repo.json, and emits a single self-contained index.html. Run by the
deploy-site workflow after every index rebuild; runnable locally too:

    curl -fsSL $(python3 -c "import json;print(json.load(open('logos-repo.json'))['indexUrl'])") -o /tmp/index.json
    python3 site/gen_site.py --index /tmp/index.json --out _site
"""
import argparse, base64, glob, html, json, os

REPO_GH = "https://github.com/hackyguru/logos-modules"
SOURCE_GH = "https://github.com/hackyguru/logos-workshop"


def prettify(name: str) -> str:
    return " ".join(w.capitalize() for w in name.replace("_ui", "").split("_"))


def latest(pkg: dict) -> dict:
    return max(pkg["versions"], key=lambda v: v.get("releasedAt", ""))


def platforms(manifest: dict) -> list:
    plats = sorted(k.split("/", 1)[1] for k in manifest.get("hashes", {}) if k.startswith("variants/"))
    return plats or sorted(manifest.get("main", {}).keys())


def find_icon(icon_name: str):
    """Base64 data-URI for a module icon, searched in the checked-out submodules."""
    if not icon_name:
        return None
    base = os.path.basename(icon_name)
    for p in glob.glob(f"submodules/**/{base}", recursive=True):
        try:
            b = open(p, "rb").read()
        except OSError:
            continue
        if len(b) > 300_000:
            continue
        mime = "image/svg+xml" if p.endswith(".svg") else "image/png"
        return f"data:{mime};base64," + base64.b64encode(b).decode()
    return None


def group_apps(packages: list) -> list:
    """Merge `<x>` + `<x>_ui` into one app card; standalone packages get their own."""
    by_name = {p["name"]: p for p in packages}
    apps, used = [], set()
    for name, pkg in by_name.items():
        if name in used or name.endswith("_ui"):
            continue
        members = [pkg]
        used.add(name)
        ui = by_name.get(name + "_ui")
        if ui:
            members.append(ui)
            used.add(ui["name"])
        apps.append(members)
    for name, pkg in by_name.items():  # ui packages with no core sibling
        if name not in used:
            apps.append([pkg])
            used.add(name)
    return apps


def render_app(members: list) -> str:
    vers = [latest(p) for p in members]
    manifests = [v["manifest"] for v in vers]
    ui = next((m for m in manifests if m.get("type") == "ui_qml"), None)
    core = next((m for m in manifests if m.get("type") != "ui_qml"), manifests[0])
    title = prettify(core["name"])
    desc = (ui or core).get("description", "")
    category = core.get("category", "")
    version = core.get("version", "")
    released = max(v.get("releasedAt", "") for v in vers)[:10]
    size = sum(v.get("size", 0) for v in vers)
    size_h = f"{size/1e6:.1f} MB" if size > 1e6 else f"{size/1e3:.0f} KB"
    own = {m["name"] for m in manifests}
    deps = sorted({d for m in manifests for d in m.get("dependencies", []) if d not in own})
    plats = sorted({p for m in manifests for p in platforms(m)})
    signed = all(v.get("signature") for v in vers)
    icon = next((find_icon(m.get("icon")) for m in manifests if m.get("icon")), None)

    icon_html = (
        f'<img class="icon" src="{icon}" alt="">' if icon
        else f'<div class="icon icon-fallback">{html.escape(title[0])}</div>'
    )
    pkgs_html = "".join(
        f'<span class="chip mono">{html.escape(m["name"])}'
        f'<span class="chip-type">{html.escape(m.get("type", ""))}</span></span>'
        for m in manifests
    )
    deps_html = (
        '<div class="row"><span class="label">requires</span>'
        + "".join(f'<span class="chip mono">{html.escape(d)}</span>' for d in deps)
        + "</div>"
    ) if deps else ""
    plats_html = "".join(f'<span class="plat mono">{html.escape(p)}</span>' for p in plats)

    return f"""
    <article class="card">
      <div class="card-head">
        {icon_html}
        <div>
          <h3>{html.escape(title)} <span class="ver mono">v{html.escape(version)}</span></h3>
          <div class="meta mono">{html.escape(category)} · {size_h} · {released}{' · signed' if signed else ''}</div>
        </div>
      </div>
      <p class="desc">{html.escape(desc)}</p>
      <div class="row"><span class="label">packages</span>{pkgs_html}</div>
      {deps_html}
      <div class="card-foot">
        <div class="plats">{plats_html}</div>
        <a class="src mono" href="{SOURCE_GH}" target="_blank" rel="noopener">source ↗</a>
      </div>
    </article>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="index.json")
    ap.add_argument("--repo", default="logos-repo.json")
    ap.add_argument("--out", default="_site")
    args = ap.parse_args()

    repo = json.load(open(args.repo))
    try:
        index = json.load(open(args.index))
    except (OSError, json.JSONDecodeError):
        index = {"packages": []}

    apps = group_apps(index.get("packages", []))
    cards = "\n".join(render_app(m) for m in apps) if apps else (
        '<p class="empty mono">no modules published yet — check back soon.</p>'
    )
    repo_url = f"{repo['homepage']}/logos-repo.json"
    generated = html.escape(index.get("generatedAt", ""))

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Guru's Logos Modules</title>
<meta name="description" content="{html.escape(repo['description'])}">
<style>
  :root {{
    --bg: #121212; --card: #17171a; --border: #27272a;
    --fg: #f4f4f5; --dim: #a1a1aa; --dimmer: #71717a;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--fg);
    font-family: Inter, -apple-system, "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased; line-height: 1.6;
  }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  main {{ max-width: 880px; margin: 0 auto; padding: 72px 24px 96px; }}
  header p.kicker {{ color: var(--dimmer); font-size: 13px; letter-spacing: .06em; }}
  h1 {{ font-size: 34px; font-weight: 700; margin: 8px 0 12px; }}
  header p.sub {{ color: var(--dim); max-width: 560px; font-size: 15px; }}
  .add {{
    margin: 32px 0 56px; border: 1px solid var(--border); border-radius: 10px;
    background: var(--card); padding: 18px 20px;
  }}
  .add .label {{ display:block; color: var(--dimmer); font-size: 12px; margin-bottom: 10px; letter-spacing:.05em; }}
  .add .urlrow {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
  .add code {{
    font-size: 13px; color: var(--fg); background: #0c0c0e; border: 1px solid var(--border);
    border-radius: 6px; padding: 8px 12px; overflow-x: auto; flex: 1; min-width: 240px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  .add button {{
    background: var(--fg); color: #121212; border: 0; border-radius: 6px;
    padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer;
  }}
  .add button:hover {{ background: #d4d4d8; }}
  .add .hint {{ color: var(--dimmer); font-size: 12.5px; margin-top: 10px; }}
  h2 {{ font-size: 13px; font-weight: 500; color: var(--dimmer); letter-spacing: .08em; margin-bottom: 18px; }}
  .card {{
    border: 1px solid var(--border); border-radius: 10px; background: var(--card);
    padding: 22px; margin-bottom: 18px;
  }}
  .card-head {{ display: flex; gap: 14px; align-items: center; margin-bottom: 12px; }}
  .icon {{ width: 44px; height: 44px; border-radius: 9px; object-fit: contain; background: #0c0c0e; border: 1px solid var(--border); }}
  .icon-fallback {{ display:flex; align-items:center; justify-content:center; color: var(--dim); font-size: 20px; }}
  h3 {{ font-size: 17px; font-weight: 600; }}
  .ver {{ color: var(--dimmer); font-size: 12.5px; font-weight: 400; margin-left: 4px; }}
  .meta {{ color: var(--dimmer); font-size: 12px; }}
  .desc {{ color: var(--dim); font-size: 14.5px; margin-bottom: 14px; }}
  .row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }}
  .label {{ color: var(--dimmer); font-size: 12px; min-width: 64px; }}
  .chip {{
    font-size: 12px; color: var(--fg); border: 1px solid var(--border);
    border-radius: 999px; padding: 2px 10px; background: #0c0c0e;
  }}
  .chip-type {{ color: var(--dimmer); margin-left: 6px; }}
  .card-foot {{ display: flex; justify-content: space-between; align-items: center; margin-top: 14px; }}
  .plats {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .plat {{ font-size: 11.5px; color: var(--dimmer); border: 1px dashed var(--border); border-radius: 4px; padding: 1px 7px; }}
  a.src {{ color: var(--dim); font-size: 12.5px; text-decoration: none; }}
  a.src:hover {{ color: var(--fg); }}
  .empty {{ color: var(--dimmer); font-size: 14px; }}
  footer {{ margin-top: 64px; color: var(--dimmer); font-size: 12.5px; }}
  footer a {{ color: var(--dim); text-decoration: none; }}
  footer a:hover {{ color: var(--fg); }}
</style>
</head>
<body>
<main>
  <header>
    <p class="kicker mono">modules.hackyguru.com</p>
    <h1>Guru's Logos Modules</h1>
    <p class="sub">Sovereign apps for <a href="https://logos.co" style="color:var(--fg)">Logos Basecamp</a>,
    built by <a href="https://hackyguru.com" style="color:var(--fg)">Guru</a>.
    Add the catalog once — install and update everything below with one click.</p>
  </header>

  <div class="add">
    <span class="label mono">BASECAMP → PACKAGE MANAGER → ADD REPOSITORY</span>
    <div class="urlrow">
      <code id="repo-url">{html.escape(repo_url)}</code>
      <button onclick="navigator.clipboard.writeText(document.getElementById('repo-url').textContent).then(()=>{{this.textContent='copied';setTimeout(()=>this.textContent='copy',1500)}})">copy</button>
    </div>
    <p class="hint">Basecamp resolves versions and dependencies for you. Packages are Ed25519-signed.</p>
  </div>

  <h2 class="mono">MODULES</h2>
  {cards}

  <footer>
    <span class="mono">index generated {generated}</span> ·
    <a href="{REPO_GH}">github</a> ·
    <a href="{repo['homepage']}/logos-repo.json">logos-repo.json</a>
  </footer>
</main>
</body>
</html>"""

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "index.html"), "w") as f:
        f.write(page)
    print(f"wrote {args.out}/index.html — {len(apps)} app(s), {len(index.get('packages', []))} package(s)")


if __name__ == "__main__":
    main()
