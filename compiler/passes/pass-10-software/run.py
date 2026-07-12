#!/usr/bin/env python3
"""pass-10-software entrypoint (model-required -> code generation).

Consumes the Application IR and *generates a deployable, runnable Next.js
(App Router) scaffold* into ``<build>/app/``:

  - ``data/*.json``        the compiled IRs, copied in so the app is
                           self-contained (no external services needed)
  - ``app/app/api/<n>/route.ts``   real route handlers that READ the copied
                           artifacts from ``data/`` and return them as JSON
  - ``app/components/*.tsx``       generated React components, one of which
                           (KnowledgeGraphVisualizer) fetches /api/graph and
                           renders an SVG knowledge graph with zero extra deps
  - ``app/app/<route>/page.tsx``   one page per declared route
  - ``package.json`` / ``next.config.mjs`` / ``tsconfig.json`` / ``README.md``

The generated app needs only ``npm install && npm run dev`` — no cloud, no
extra APIs. This is the "intelligence becomes software" payoff.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from compiler.core.artifacts import ArtifactStore  # noqa: E402
from compiler.core.llm_pass import parse_port_model, run_model_pass  # noqa: E402
from compiler.core.diagnostics import DiagnosticEmitter  # noqa: E402

try:
    from compiler.reports.dashboard import collect as _collect_evals  # noqa: E402
except ImportError:  # pragma: no cover - fallback when imported as a package
    from ..reports.dashboard import collect as _collect_evals  # noqa: E402

PRODUCES = "application-ir"
CONSUMES = ["reasoning-ir", "semantic-ir", "graph-ir"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def to_pascal(name: str) -> str:
    out = []
    for part in str(name).replace("-", " ").replace("_", " ").split():
        if part:
            out.append(part[0].upper() + part[1:])
    return "".join(out) or "Component"


def route_dir(route: str) -> str:
    """Map a route path to an app-router directory segment.

    The root route "/" becomes "" (so the page lands at app/page.tsx, the
    Next.js root), not "index" (which would create a broken app/index route).
    Nested routes like "/foo/bar" become "foo_bar".
    """
    r = (route or "/").strip().strip("/")
    return r.replace("/", "_")


def _copy_artifacts(build_dir: str, app_root: str, emit: DiagnosticEmitter) -> dict:
    """Copy every compiled IR into the app's data/ dir. Returns {type: file}."""
    store = ArtifactStore(build_dir)
    data_dir = os.path.join(app_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    present = {}
    for art in ("markdown-ir", "entity-ir", "ontology-ir", "graph-ir",
                "semantic-ir", "reasoning-ir", "application-ir"):
        if store.has(art):
            data = store.read(art)
            fname = os.path.join(data_dir, f"{art}.json")
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            present[art] = f"{art}.json"
    # Fold the 9-dimension evaluations into a single file for the app's
    # /evaluation route (observability built into the generated app).
    try:
        evals = _collect_evals(build_dir)
    except Exception as e:  # noqa: BLE001 - never let eval copy break the app
        evals = []
        emit.warning("NO_EVAL_DATA", f"could not read evaluations: {e}")
    with open(os.path.join(data_dir, "evaluations.json"), "w", encoding="utf-8") as f:
        json.dump(evals, f, ensure_ascii=False, indent=2)
    present["evaluations"] = "evaluations.json"
    if not present:
        emit.warning("NO_DATA", "no compiled IRs found to embed in the app")
    return present


def _write(app_root: str, rel: str, content: str) -> None:
    path = os.path.join(app_root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _api_route_ts(data_file: str) -> str:
    return (
        'import { NextResponse } from "next/server";\n'
        'import { readFileSync } from "fs";\n'
        'import path from "path";\n\n'
        f'const FILE = "{data_file}";\n\n'
        "export async function GET() {\n"
        "  try {\n"
        '    const p = path.join(process.cwd(), "data", FILE);\n'
        "    const data = JSON.parse(readFileSync(p, \"utf-8\"));\n"
        "    return NextResponse.json(data);\n"
        "  } catch (e) {\n"
        '    return NextResponse.json({ error: String(e) }, { status: 500 });\n'
        "  }\n"
        "}\n"
    )


# Canonical artifact -> api base path + friendly label
CANON = [
    ("graph-ir", "graph", "Knowledge Graph"),
    ("ontology-ir", "ontology", "Ontology"),
    ("entity-ir", "entities", "Entities"),
    ("semantic-ir", "semantic", "Semantic Index"),
    ("reasoning-ir", "reasoning", "Reasoning"),
    ("application-ir", "app", "Application Spec"),
]


GRAPH_VIEWER_TSX = """'use client';
import { useEffect, useState } from 'react';

export default function KnowledgeGraphVisualizer() {
  const [g, setG] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    fetch('/api/graph')
      .then((r) => r.json())
      .then(setG)
      .catch((e) => setErr(String(e)));
  }, []);
  if (err) return <div className="error">graph error: {err}</div>;
  if (!g) return <div>Loading knowledge graph...</div>;
  const nodes = g.nodes || [];
  const edges = g.edges || [];
  const n = Math.max(nodes.length, 1);
  const R = 200;
  const pos = nodes.map((nd: any, i: number) => {
    const a = (2 * Math.PI * i) / n;
    return { id: nd.id, x: 260 + R * Math.cos(a), y: 260 + R * Math.sin(a), label: nd.label || nd.id };
  });
  const byId: Record<string, any> = Object.fromEntries(pos.map((p: any) => [p.id, p]));
  return (
    <svg width="520" height="520" viewBox="0 0 520 520" role="img" aria-label="knowledge graph">
      {edges.map((e: any, i: number) => {
        const s = byId[e.source], t = byId[e.target];
        if (!s || !t) return null;
        return <line key={'e' + i} x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke="#94a3b8" strokeWidth={1} />;
      })}
      {pos.map((p) => (
        <g key={p.id}>
          <circle cx={p.x} cy={p.y} r={6} fill="#3b82f6" />
          <text x={p.x + 8} y={p.y + 4} fontSize={11} fill="#0f172a">{p.label}</text>
        </g>
      ))}
    </svg>
  );
}
"""


# ---------------------------------------------------------------------------
# main generation
# ---------------------------------------------------------------------------

EVAL_DASHBOARD_TSX = """'use client';
import { useEffect, useState } from 'react';

type Rec = { artifact: string; overall: number; scores: Record<string, number> };
const DIMS = ['completeness','correctness','coverage','consistency','hallucination','traceability','provenance','confidence','reproducibility'];

function color(v: number): string {
  if (v >= 0.75) return '#16a34a';
  if (v >= 0.5) return '#d97706';
  return '#dc2626';
}

export default function EvaluationDashboard() {
  const [recs, setRecs] = useState<Rec[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    fetch('/api/evaluation')
      .then((r) => r.json())
      .then((d) => setRecs(Array.isArray(d) ? d : []))
      .catch((e) => setErr(String(e)));
  }, []);
  if (err) return <div className="error">eval error: {err}</div>;
  if (!recs) return <div>Loading evaluation…</div>;
  if (recs.length === 0) return <div>No evaluation data.</div>;

  return (
    <div>
      {recs.map((r) => (
        <div key={r.artifact} style={{ marginBottom: '1.2rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '0.8rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'ui-monospace, monospace' }}>
            <strong>{r.artifact}</strong>
            <span style={{ color: color(r.overall), fontWeight: 700 }}>{Math.round(r.overall * 100)}</span>
          </div>
          {DIMS.map((d) => {
            const v = r.scores[d] || 0;
            return (
              <div key={d} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 12, marginTop: 4 }}>
                <span style={{ width: 104, color: '#64748b', textTransform: 'capitalize' }}>{d}</span>
                <span style={{ flex: 1, height: 8, background: '#e2e8f0', borderRadius: 5, overflow: 'hidden' }}>
                  <span style={{ display: 'block', height: '100%', width: `${Math.round(v * 100)}%`, background: color(v) }} />
                </span>
                <span style={{ width: 28, textAlign: 'right' }}>{Math.round(v * 100)}</span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
"""


def generate(build_dir: str, app: dict, emit: DiagnosticEmitter) -> None:
    # The generated Next.js project lives in ``<build>/knowledge-app``. We avoid
    # naming it ``app`` so the Next App Router dir (``knowledge-app/app``) is the
    # only directory named ``app`` — Turbopack mis-detects nested ``app/app``.
    app_root = os.path.join(build_dir, "knowledge-app")
    shutil.rmtree(app_root, ignore_errors=True)
    os.makedirs(os.path.join(app_root, "app"), exist_ok=True)

    present = _copy_artifacts(build_dir, app_root, emit)

    # ---- config files -----------------------------------------------------
    _write(app_root, "package.json", json.dumps({
        "name": "knowledge-app",
        "version": "0.1.0",
        "private": True,
        "scripts": {
            "dev": "next dev",
            "build": "next build",
            "start": "next start",
        },
        "dependencies": {
            "next": "14.2.5",
            "react": "18.3.1",
            "react-dom": "18.3.1",
        },
        "devDependencies": {"typescript": "5.4.5", "@types/react": "18.3.3",
                             "@types/node": "20.14.10"},
        "engines": {"node": "22.x"},
    }, indent=2) + "\n")

    _write(app_root, "tsconfig.json", json.dumps({
        "compilerOptions": {
            "target": "ES2020",
            "lib": ["dom", "dom.iterable", "esnext"],
            "allowJs": True, "skipLibCheck": True,
            "strict": False, "noEmit": True,
            "esModuleInterop": True, "module": "esnext",
            "moduleResolution": "bundler", "resolveJsonModule": True,
            "isolatedModules": True, "jsx": "preserve",
            "incremental": True, "plugins": [{"name": "next"}],
            "baseUrl": ".",
            "paths": {"@/*": ["./*"]},
        },
        "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
        "exclude": ["node_modules"],
    }, indent=2) + "\n")

    _write(app_root, "next.config.mjs",
           'const nextConfig = { reactStrictMode: true };\nexport default nextConfig;\n')

    # vercel.json: deploy the generated app to Vercel as a Node serverless
    # Next.js app (its /api/* routes become serverless functions).
    _write(app_root, "vercel.json",
           json.dumps({"buildCommand": "npm install && npm run build",
                       "outputDirectory": ".next",
                       "framework": "nextjs"}, indent=2) + "\n")

    _write(app_root, "app/layout.tsx",
           'export const metadata = { title: "Knowledge App", description: "Generated by the Knowledge Compiler" };\n'
           'export default function RootLayout({ children }: { children: React.ReactNode }) {\n'
           '  return (\n'
           '    <html lang="en"><body style={{ fontFamily: "system-ui, sans-serif", margin: 0 }}>{children}</body></html>\n'
           '  );\n'
           '}\n')

    # ---- data overview route ---------------------------------------------
    def _overview() -> dict:
        out: dict = {}
        for art, _f, label in CANON:
            if art in present:
                out[label] = present[art]
        return out
    _write(app_root, "app/api/overview/route.ts",
           'import { NextResponse } from "next/server";\n'
           'export async function GET() {\n'
           f'  return NextResponse.json({json.dumps(_overview())});\n'
           '}\n')

    # ---- canonical API routes (real, data-serving) -----------------------
    for art, base, _label in CANON:
        if art in present:
            _write(app_root, f"app/api/{base}/route.ts",
                   _api_route_ts(present[art]))

    # ---- evaluation API route (observability built into the app) ---------
    _write(app_root, "app/api/evaluation/route.ts", _api_route_ts(present["evaluations"]))

    # ---- model-declared api routes (best-effort mapping) -----------------
    declared = app.get("apis", []) or []
    known_bases = {b for _a, b, _l in CANON}
    for api in declared:
        seg = api.get("path", "").strip("/").replace("/", "_") or "custom"
        if seg in known_bases or seg.startswith("api_"):
            continue  # already covered or previously handled
        # map keyword -> artifact, default to application-ir
        target = present.get("application-ir")
        low = seg.lower()
        for art, base, _l in CANON:
            if base in low and art in present:
                target = present[art]
                break
        if target:
            _write(app_root, f"app/api/{seg}/route.ts", _api_route_ts(target))

    # ---- components -------------------------------------------------------
    # Build the set of component names actually needed: declared components
    # PLUS every component any page imports. The model sometimes references
    # component ids in pages that aren't in the components list, so we write a
    # stub for any referenced name that has no real implementation. This keeps
    # the generated app buildable (no missing-module errors) instead of failing
    # the whole deploy on a model-output inconsistency.
    components = {c.get("id"): c for c in app.get("components", [])}

    def _component_stub(name: str, resp: str = "Generated component.") -> str:
        n = to_pascal(name)
        return (
            f"// {resp}\n"
            f"export default function {n}() {{\n"
            f"  return <div className=\"{n}\">{n}</div>;\n"
            f"}}\n"
        )

    needed = {to_pascal(c.get("name", c.get("id"))) for c in app.get("components", [])}
    for p in app.get("pages", []) or []:
        for c in p.get("components", []):
            needed.add(to_pascal(components[c]["name"]) if c in components else to_pascal(str(c)))

    for name in sorted(needed):
        c = next((x for x in app.get("components", []) if to_pascal(x.get("name", x.get("id"))) == name), None)
        resp = (c or {}).get("responsibility", "Generated component.")
        _write(app_root, f"components/{name}.tsx", _component_stub(name, resp))

    # always include the graph viewer (renders /api/graph)
    _write(app_root, "components/KnowledgeGraphVisualizer.tsx", GRAPH_VIEWER_TSX)
    # always include the evaluation dashboard (renders /api/evaluation)
    _write(app_root, "components/EvaluationDashboard.tsx", EVAL_DASHBOARD_TSX)

    # ---- pages ------------------------------------------------------------
    pages = app.get("pages", []) or []
    if not pages:
        pages = [{"id": "home", "title": "Home", "route": "/",
                  "components": ["KnowledgeGraphVisualizer"]}]
    for p in pages:
        rdir = route_dir(p.get("route", "/"))
        title = p.get("title", p.get("id"))
        comp_names = [
            to_pascal(components[c]["name"]) if c in components else to_pascal(str(c))
            for c in p.get("components", [])
        ]
        # Relative import path to components/ (alias-independent, so the
        # generated app builds on Vercel regardless of tsconfig paths support).
        # Page lives at app/<rdir>/page.tsx; to reach repo-root components/ we
        # go up (number of route segments + 1 for the app/ level).
        ups = len([s for s in rdir.split("/") if s]) + 1
        rel = "../" * ups + "components/"
        imports = "\n".join(
            f'import {n} from "{rel}{n}";' for n in comp_names
        )
        body = "\n".join(f"      <{n} />" for n in comp_names) or "      <p>No components.</p>"
        code = (
            f'// page: {title} (route {p.get("route")})\n'
            f"{imports}\n"
            f"export default function Page() {{\n"
            f"  return (\n"
            f"    <main style={{{{ padding: '2rem' }}}}>\n"
            f"      <h1>{title}</h1>\n"
            f"{body}\n"
            f"    </main>\n"
            f"  );\n"
            f"}}\n"
        )
        page_rel = f"app/{rdir}/page.tsx" if rdir else "app/page.tsx"
        _write(app_root, page_rel, code)

    # ---- evaluation page (observability built into the generated app) -----
    _write(app_root, "app/evaluation/page.tsx",
           "import EvaluationDashboard from \"../../components/EvaluationDashboard\";\n"
           "export default function Page() {\n"
           "  return (\n"
           "    <main style={{ padding: '2rem' }}>\n"
           "      <h1>Evaluation</h1>\n"
           "      <p style={{ color: '#64748b', fontSize: 13 }}>9-dimension scorecard for every compiled artifact.</p>\n"
           "      <EvaluationDashboard />\n"
           "    </main>\n"
           "  );\n"
           "}\n")

    # ---- README with deployment plan -------------------------------------
    dp = app.get("deployment_plan", {}) or {}
    steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(dp.get("steps", []))) or "1. npm install\n2. npm run dev"
    prereq = ", ".join(dp.get("prerequisites", [])) or "node 18+"
    readme = (
        "# Knowledge App\n\n"
        "Generated by the Knowledge Compiler from your compiled knowledge base.\n"
        "Self-contained: the compiled IRs are embedded in `data/` and served by\n"
        "the API routes — no external services required.\n\n"
        "## Run\n\n"
        "```bash\nnpm install\nnpm run dev\n# open http://localhost:3000\n```\n\n"
        "## What's inside\n\n"
        "- `data/*.json` — the compiled IRs (graph, ontology, entities, ...)\n"
        "- `knowledge-app/app/api/*/route.ts` — route handlers serving that data\n"
        "- `components/KnowledgeGraphVisualizer.tsx` — SVG knowledge-graph view\n\n"
        "## Deployment\n\n"
        f"- target: `{dp.get('target', 'static')}`\n"
        f"- prerequisites: {prereq}\n\n"
        "### steps\n\n"
        f"{steps}\n"
    )
    _write(app_root, "README.md", readme)
    _write(app_root, "manifest.json", json.dumps({
        "name": "Knowledge App",
        "generated_from": "application-ir",
        "data_artifacts": list(present.keys()),
        "api_routes": [f"/api/{b}" for _a, b, _l in CANON if _a in present] + ["/api/overview"],
    }, indent=2) + "\n")

    return app_root


# ---------------------------------------------------------------------------
# compiler entrypoint
# ---------------------------------------------------------------------------

def build_user_prompt(inputs):
    return (
        "Build an application spec (application-ir) from the reasoning and "
        "semantic IRs already compiled. Return the JSON object required by the "
        "application-ir schema: architecture, pages, components, routes, apis, "
        "deployment_plan. Every page.route must start with '/'."
    )


SYSTEM_PROMPT = (
    "You are a software architect. Given compiled knowledge IRs, produce a "
    "concrete application specification as strict JSON."
)


def repair(data, inputs, emitter: DiagnosticEmitter) -> dict:
    """Backfill a schema-valid application-ir from available inputs."""
    gi = inputs.get("graph-ir", {})
    si = inputs.get("semantic-ir", {})
    nodes = gi.get("nodes", [])
    themes = si.get("themes", [])

    if not data.get("architecture"):
        emitter.warning("MISSING_EVIDENCE", "no architecture; using default layers")
        data["architecture"] = {
            "layers": ["presentation", "application", "data"],
            "rationale": "default three-tier from available IRs",
        }
    if not data.get("pages"):
        emitter.warning("MISSING_EVIDENCE", "no pages; deriving one per theme/node")
        src = themes or nodes
        pages = []
        for i, t in enumerate(src[:5] or [{"id": "n1", "label": "Home"}]):
            label = t.get("label", f"Page {i+1}")
            pid = f"page-{i+1}"
            pages.append({
                "id": pid,
                "title": label,
                "route": "/" if i == 0 else f"/{t.get('id', f'p{i+1}')}",
                "components": ["KnowledgeGraphVisualizer"] if i == 0 else [f"cmp-{i+1}"],
                "theme_ref": t.get("id"),
            })
        data["pages"] = pages
    if not data.get("components"):
        emitter.warning("MISSING_EVIDENCE", "no components; deriving from pages")
        comps = []
        for p in data["pages"]:
            cid = (p.get("components") or [f"cmp-{p['id']}"])[0]
            comps.append({
                "id": cid,
                "name": p["title"].replace(" ", "") or "Component",
                "props": [],
                "responsibility": f"Renders {p['title']}",
            })
        data["components"] = comps
    if not data.get("routes"):
        data["routes"] = [
            {"path": p["route"], "page_id": p["id"], "method": "GET"}
            for p in data["pages"]
        ]
    if not data.get("apis"):
        data["apis"] = [{
            "path": "/api/knowledge",
            "method": "GET",
            "purpose": "serve the compiled knowledge graph",
            "request": {}, "response": {},
        }]
    if not data.get("deployment_plan"):
        emitter.warning("MISSING_EVIDENCE", "no deployment plan; using default")
        data["deployment_plan"] = {
            "target": "static",
            "steps": ["npm install", "npm run build", "npm run start"],
            "prerequisites": ["node 18+"],
        }
    return data


def main():
    # pass-10 is a *deterministic code-generation* pass: it consumes the
    # application-ir already produced by pass-09 and emits a runnable app. It
    # does NOT call the model. If the application-ir is missing required
    # sections, repair() backfills a valid scaffold from the other IRs.
    import argparse

    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("build_dir", nargs="?", default=os.getcwd())
    ap.add_argument("--port", type=int, default=int(os.environ.get("KC_PORT", "8080")))
    ap.add_argument("--model", default=os.environ.get("KC_MODEL"))
    ap.add_argument("--embed-model", default=os.environ.get("KC_EMBED_MODEL"))
    ns, _ = ap.parse_known_args(sys.argv[1:])

    store = ArtifactStore(ns.build_dir)
    if not store.has(PRODUCES):
        sys.stderr.write("missing input artifact: application-ir\n")
        return 1
    app = store.read(PRODUCES)
    emit = DiagnosticEmitter(PRODUCES, ns.build_dir)
    inputs = {}
    for a in CONSUMES:
        if store.has(a):
            inputs[a] = store.read(a)
    app = repair(app, inputs, emit)
    app_root = generate(ns.build_dir, app, emit)
    n = sum(len(fs) for _, _, fs in os.walk(app_root))
    print(f"wrote runnable Next.js app to {app_root} ({n} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
