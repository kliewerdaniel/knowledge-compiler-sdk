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
    rel = rel.removesuffix(".tsx.tsx") + ".tsx" if rel.endswith(".tsx.tsx") else rel
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
            "typescript": "5.4.5",
            "@types/react": "18.3.3",
            "@types/node": "20.14.10",
            "framer-motion": "11.3.8",
            "lucide-react": "0.417.0",
            "clsx": "2.1.1",
            "tailwind-merge": "2.4.0",
        },
        "devDependencies": {"tailwindcss": "3.4.7", "postcss": "8.4.40",
                             "autoprefixer": "10.4.19"},
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
           "const nextConfig = {\n"
           "  reactStrictMode: true,\n"
           "  typescript: { ignoreBuildErrors: true },\n"
           "};\n"
           "export default nextConfig;\n")

    # ---- tailwind + postcss + globals (shadcn-style design system) --------
    _write(app_root, "tailwind.config.ts",
           "import type { Config } from 'tailwindcss';\n"
           "const config: Config = {\n"
           "  darkMode: 'class',\n"
           "  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],\n"
           "  theme: {\n"
           "    extend: {\n"
           "      colors: {\n"
           "        border: 'hsl(214 32% 91%)',\n"
           "        input: 'hsl(214 32% 91%)',\n"
           "        ring: 'hsl(222 47% 50%)',\n"
           "        background: 'hsl(0 0% 100%)',\n"
           "        foreground: 'hsl(222 47% 11%)',\n"
           "        muted: 'hsl(210 40% 96%)',\n"
           "        'muted-foreground': 'hsl(215 16% 47%)',\n"
           "        primary: 'hsl(222 47% 41%)',\n"
           "        'primary-foreground': 'hsl(0 0% 100%)',\n"
           "        card: 'hsl(0 0% 100%)',\n"
           "        'card-foreground': 'hsl(222 47% 11%)',\n"
           "        accent: 'hsl(199 89% 48%)',\n"
           "      },\n"
           "      borderRadius: { lg: '0.75rem', md: '0.5rem', sm: '0.375rem' },\n"
           "    },\n"
           "  },\n"
           "  plugins: [],\n"
           "};\n"
           "export default config;\n")
    _write(app_root, "postcss.config.js",
           "module.exports = {\n"
           "  plugins: { tailwindcss: {}, autoprefixer: {} },\n"
           "};\n")
    _write(app_root, "app/globals.css",
           "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n"
           "html, body { height: 100%; }\n"
           "body { @apply bg-background text-foreground antialiased; }\n"
           ".grid-bg {\n"
           "  background-image: radial-gradient(hsl(214 32% 91%) 1px, transparent 1px);\n"
           "  background-size: 22px 22px;\n"
           "}\n")

    # ---- lib/utils (shadcn cn helper) -------------------------------------
    _write(app_root, "lib/utils.ts",
           "import { clsx, type ClassValue } from 'clsx';\n"
           "import { twMerge } from 'tailwind-merge';\n"
           "export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }\n")


    # vercel.json: deploy the generated app to Vercel as a Node serverless
    # Next.js app (its /api/* routes become serverless functions).
    _write(app_root, "vercel.json",
           json.dumps({"buildCommand": "npm install && npm run build",
                       "outputDirectory": ".next",
                       "framework": "nextjs"}, indent=2) + "\n")

    _write(app_root, "app/layout.tsx",
           "import './globals.css';\n"
           'export const metadata = { title: "Knowledge App", description: "Generated by the Knowledge Compiler" };\n'
           'export default function RootLayout({ children }: { children: React.ReactNode }) {\n'
           '  return (\n'
           '    <html lang="en"><body>{children}</body></html>\n'
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
    # Emit a fixed, polished, heuristic-driven frontend (Tailwind + shadcn
    # style + framer-motion). We deliberately IGNORE the model's stub
    # pages/components (they are <div>Name</div> placeholders) and instead
    # build real views that read the compiled IRs via the /api/* routes.
    def _ui(name: str, code: str) -> None:
        _write(app_root, f"components/ui/{name}.tsx", code)

    def _cmp(name: str, code: str) -> None:
        _write(app_root, f"components/{name}.tsx", code)

    # shadcn-style primitives
    _ui("button.tsx",
        "import * as React from 'react';\n"
        "export function Button({ className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {\n"
        "  return (\n"
        "    <button className={'inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50 ' + (className || '')} {...props} />\n"
        "  );\n"
        "}\n")
    _ui("card.tsx",
        "import * as React from 'react';\n"
        "export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {\n"
        "  return <div className={'rounded-lg border bg-card text-card-foreground shadow-sm ' + (className || '')} {...props} />;\n"
        "}\n"
        "export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {\n"
        "  return <div className={'flex flex-col space-y-1 p-5 ' + (className || '')} {...props} />;\n"
        "}\n"
        "export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {\n"
        "  return <h3 className={'text-lg font-semibold leading-none tracking-tight ' + (className || '')} {...props} />;\n"
        "}\n"
        "export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {\n"
        "  return <div className={'p-5 pt-0 ' + (className || '')} {...props} />;\n"
        "}\n")
    _ui("badge.tsx",
        "import * as React from 'react';\n"
        "export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {\n"
        "  return <span className={'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium text-muted-foreground ' + (className || '')} {...props} />;\n"
        "}\n")

    # Sidebar nav
    _cmp("Sidebar.tsx",
        "'use client';\n"
        "import Link from 'next/link';\n"
        "import { motion } from 'framer-motion';\n"
        "import { Network, List, GitGraph, Lightbulb, Layers, Gauge } from 'lucide-react';\n"
        "const items = [\n"
        "  { href: '/', label: 'Overview', icon: Network },\n"
        "  { href: '/entities', label: 'Entities', icon: List },\n"
        "  { href: '/graph', label: 'Knowledge Graph', icon: GitGraph },\n"
        "  { href: '/reasoning', label: 'Reasoning', icon: Lightbulb },\n"
        "  { href: '/themes', label: 'Themes', icon: Layers },\n"
        "  { href: '/evaluation', label: 'Evaluation', icon: Gauge },\n"
        "];\n"
        "export default function Sidebar() {\n"
        "  return (\n"
        "    <aside className='flex h-screen w-60 flex-col border-r bg-card'>\n"
        "      <div className='px-5 py-5'>\n"
        "        <div className='text-sm font-semibold tracking-tight'>Knowledge Compiler</div>\n"
        "        <div className='text-xs text-muted-foreground'>compiled from your corpus</div>\n"
        "      </div>\n"
        "      <nav className='flex flex-col gap-1 px-3'>\n"
        "        {items.map((it) => (\n"
        "          <Link key={it.href} href={it.href} className='flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground'>\n"
        "            <it.icon className='h-4 w-4' /> {it.label}\n"
        "          </Link>\n"
        "        ))}\n"
        "      </nav>\n"
        "    </aside>\n"
        "  );\n"
        "}\n")

    # Entity explorer (provenance + filter)
    _cmp("EntityExplorer.tsx",
        "'use client';\n"
        "import { useEffect, useMemo, useState } from 'react';\n"
        "import { motion, AnimatePresence } from 'framer-motion';\n"
        "import { Badge } from './ui/badge';\n"
        "import { Card, CardContent, CardHeader, CardTitle } from './ui/card';\n"
        "type E = { id: string; label: string; type: string; confidence?: number; span?: any };\n"
        "export default function EntityExplorer() {\n"
        "  const [ents, setEnts] = useState<E[]>([]);\n"
        "  const [types, setTypes] = useState<string[]>([]);\n"
        "  const [filter, setFilter] = useState<string>('all');\n"
        "  const [sel, setSel] = useState<E | null>(null);\n"
        "  useEffect(() => {\n"
        "    fetch('/api/entities').then((r) => r.json()).then((d) => {\n"
        "      const es: E[] = d.entities || [];\n"
        "      setEnts(es);\n"
        "      setTypes(Array.from(new Set(es.map((e) => e.type))));\n"
        "    });\n"
        "  }, []);\n"
        "  const shown = useMemo(() => ents.filter((e) => filter === 'all' || e.type === filter), [ents, filter]);\n"
        "  return (\n"
        "    <div className='grid grid-cols-1 gap-4 lg:grid-cols-3'>\n"
        "      <div className='lg:col-span-2'>\n"
        "        <div className='mb-3 flex flex-wrap gap-2'>\n"
        "          <button onClick={() => setFilter('all')} className={filter === 'all' ? 'rounded-full bg-primary px-3 py-1 text-xs text-primary-foreground' : 'rounded-full border px-3 py-1 text-xs'}>all ({ents.length})</button>\n"
        "          {types.map((t) => (\n"
        "            <button key={t} onClick={() => setFilter(t)} className={filter === t ? 'rounded-full bg-primary px-3 py-1 text-xs text-primary-foreground' : 'rounded-full border px-3 py-1 text-xs'}>{t}</button>\n"
        "          ))}\n"
        "        </div>\n"
        "        <div className='grid grid-cols-1 gap-2 sm:grid-cols-2'>\n"
        "          <AnimatePresence>\n"
        "            {shown.map((e) => (\n"
        "              <motion.button key={e.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} onClick={() => setSel(e)} className='rounded-md border bg-card p-3 text-left transition hover:border-primary'>\n"
        "                <div className='text-sm font-medium'>{e.label}</div>\n"
        "                <div className='mt-1 flex items-center gap-2'>\n"
        "                  <Badge>{e.type}</Badge>\n"
        "                  {e.confidence != null && <span className='text-xs text-muted-foreground'>{(e.confidence * 100).toFixed(0)}%</span>}\n"
        "                </div>\n"
        "              </motion.button>\n"
        "            ))}\n"
        "          </AnimatePresence>\n"
        "        </div>\n"
        "      </div>\n"
        "      <Card>\n"
        "        <CardHeader><CardTitle>Provenance</CardTitle></CardHeader>\n"
        "        <CardContent className='text-sm text-muted-foreground'>\n"
        "          {sel ? (<div><div className='mb-1 text-foreground'>{sel.label}</div><div>type: {sel.type}</div><div>doc: {sel.span?.doc || '—'}</div><div>section: {sel.span?.section || '—'}</div></div>) : <div>Select an entity to see its source span.</div>}\n"
        "        </CardContent>\n"
        "      </Card>\n"
        "    </div>\n"
        "  );\n"
        "}\n")

    # Interactive graph (hand-rolled SVG radial layout + framer-motion)
    _cmp("GraphCanvas.tsx",
        "'use client';\n"
        "import { useEffect, useMemo, useState } from 'react';\n"
        "import { motion } from 'framer-motion';\n"
        "type N = { id: string; label: string; kind?: string };\n"
        "type E = { source: string; target: string; type?: string };\n"
        "export default function GraphCanvas() {\n"
        "  const [nodes, setNodes] = useState<N[]>([]);\n"
        "  const [edges, setEdges] = useState<E[]>([]);\n"
        "  const [hover, setHover] = useState<string | null>(null);\n"
        "  useEffect(() => {\n"
        "    fetch('/api/graph').then((r) => r.json()).then((d) => { setNodes(d.nodes || []); setEdges(d.edges || []); });\n"
        "  }, []);\n"
        "  const pos = useMemo(() => {\n"
        "    const n = nodes.length || 1;\n"
        "    const R = 260;\n"
        "    const m: Record<string, { x: number; y: number }> = {};\n"
        "    nodes.forEach((nd, i) => {\n"
        "      const a = (i / n) * Math.PI * 2;\n"
        "      m[nd.id] = { x: 400 + R * Math.cos(a), y: 320 + R * Math.sin(a) };\n"
        "    });\n"
        "    return m;\n"
        "  }, [nodes]);\n"
        "  return (\n"
        "    <svg viewBox='0 0 800 640' className='w-full rounded-lg border bg-card'>\n"
        "      {edges.map((e, i) => { const a = pos[e.source], b = pos[e.target]; if (!a || !b) return null; return (<line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={hover && hover !== e.source && hover !== e.target ? '#e5e7eb' : '#94a3b8'} strokeWidth={1.5} />); })}\n"
        "      {nodes.map((nd) => { const p = pos[nd.id]; if (!p) return null; return (\n"
        "        <motion.g key={nd.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} onMouseEnter={() => setHover(nd.id)} onMouseLeave={() => setHover(null)}>\n"
        "          <circle cx={p.x} cy={p.y} r={hover === nd.id ? 9 : 6} fill={hover === nd.id ? '#1e3a8a' : '#3b82f6'} />\n"
        "          <text x={p.x + 10} y={p.y + 4} className='fill-foreground text-[11px]'>{nd.label.slice(0, 18)}</text>\n"
        "        </motion.g>\n"
        "      ); })}\n"
        "    </svg>\n"
        "  );\n"
        "}\n")

    # Reasoning panel (observations / hypotheses / contradictions / questions)
    _cmp("ReasoningPanel.tsx",
        "'use client';\n"
        "import { useEffect, useState } from 'react';\n"
        "import { motion } from 'framer-motion';\n"
        "import { Card, CardContent, CardHeader, CardTitle } from './ui/card';\n"
        "import { Badge } from './ui/badge';\n"
        "export default function ReasoningPanel() {\n"
        "  const [d, setD] = useState<any>(null);\n"
        "  useEffect(() => { fetch('/api/reasoning').then((r) => r.json()).then(setD); }, []);\n"
        "  if (!d) return <div className='text-sm text-muted-foreground'>Loading reasoning…</div>;\n"
        "  const block = (title: string, items: any[], key: string, color: string) => (\n"
        "    <Card>\n"
        "      <CardHeader><CardTitle className='flex items-center justify-between'><span>{title}</span><Badge>{items.length}</Badge></CardTitle></CardHeader>\n"
        "      <CardContent className='space-y-2'>\n"
        "        {items.length === 0 && <div className='text-xs text-muted-foreground'>none</div>}\n"
        "        {items.map((it, i) => (\n"
        "          <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} className='rounded-md border-l-2 bg-muted/40 p-2 text-sm' style={{ borderColor: color }}>\n"
        "            <div>{it.text}</div>\n"
        "            {it.provenance && <div className='mt-1 text-xs text-muted-foreground'>src: {Array.isArray(it.provenance) ? it.provenance.join(', ') : it.provenance}</div>}\n"
        "            {it.confidence != null && <div className='text-xs text-muted-foreground'>conf: {(it.confidence * 100).toFixed(0)}%</div>}\n"
        "          </motion.div>\n"
        "        ))}\n"
        "      </CardContent>\n"
        "    </Card>\n"
        "  );\n"
        "  return (\n"
        "    <div className='grid grid-cols-1 gap-4 lg:grid-cols-2'>\n"
        "      {block('Observations', d.observations || [], 'o', '#0ea5e9')}\n"
        "      {block('Hypotheses', d.hypotheses || [], 'h', '#8b5cf6')}\n"
        "      {block('Contradictions', d.contradictions || [], 'c', '#ef4444')}\n"
        "      {block('Open Questions', d.questions || [], 'q', '#f59e0b')}\n"
        "    </div>\n"
        "  );\n"
        "}\n")

    # Theme clusters
    _cmp("ThemeClusters.tsx",
        "'use client';\n"
        "import { useEffect, useState } from 'react';\n"
        "import { motion } from 'framer-motion';\n"
        "import { Card, CardContent, CardHeader, CardTitle } from './ui/card';\n"
        "import { Badge } from './ui/badge';\n"
        "export default function ThemeClusters() {\n"
        "  const [d, setD] = useState<any>(null);\n"
        "  useEffect(() => { fetch('/api/semantic').then((r) => r.json()).then(setD); }, []);\n"
        "  const themes = (d?.themes || d?.clusters || []);\n"
        "  return (\n"
        "    <div className='grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3'>\n"
        "      {themes.length === 0 && <div className='text-sm text-muted-foreground'>No themes extracted.</div>}\n"
        "      {themes.map((t: any, i: number) => (\n"
        "        <motion.div key={i} initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}>\n"
        "          <Card>\n"
        "            <CardHeader><CardTitle className='text-base'>{t.label || t.name || ('Theme ' + (i + 1))}</CardTitle></CardHeader>\n"
        "            <CardContent>\n"
        "              {t.summary && <p className='text-sm text-muted-foreground'>{t.summary}</p>}\n"
        "              <div className='mt-2 flex flex-wrap gap-1'>\n"
        "                {(t.node_ids || t.members || []).slice(0, 8).map((m: string, j: number) => <Badge key={j}>{m}</Badge>)}\n"
        "              </div>\n"
        "            </CardContent>\n"
        "          </Card>\n"
        "        </motion.div>\n"
        "      ))}\n"
        "    </div>\n"
        "  );\n"
        "}\n")

    # Stat card
    _cmp("StatCard.tsx",
        "'use client';\n"
        "import { Card, CardContent } from './ui/card';\n"
        "import { motion } from 'framer-motion';\n"
        "export function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {\n"
        "  return (\n"
        "    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>\n"
        "      <Card><CardContent className='p-5'>\n"
        "        <div className='text-3xl font-bold tracking-tight'>{value}</div>\n"
        "        <div className='text-sm text-muted-foreground'>{label}</div>\n"
        "        {sub && <div className='mt-1 text-xs text-muted-foreground'>{sub}</div>}\n"
        "      </CardContent></Card>\n"
        "    </motion.div>\n"
        "  );\n"
        "}\n")

    # Evaluation dashboard (9-dim scorecard)
    _cmp("EvaluationDashboard.tsx",
        "'use client';\n"
        "import { useEffect, useState } from 'react';\n"
        "import { motion } from 'framer-motion';\n"
        "import { Card, CardContent, CardHeader, CardTitle } from './ui/card';\n"
        "const DIMS = ['completeness','correctness','coverage','consistency','hallucination','traceability','provenance','confidence','reproducibility'];\n"
        "export default function EvaluationDashboard() {\n"
        "  const [rows, setRows] = useState<any[]>([]);\n"
        "  useEffect(() => { fetch('/api/evaluation').then((r) => r.json()).then(setRows); }, []);\n"
        "  const rowsSorted = [...rows].sort((a, b) => (a.overall || 0) - (b.overall || 0));\n"
        "  return (\n"
        "    <div className='space-y-3'>\n"
        "      {rows.length === 0 && <div className='text-sm text-muted-foreground'>No evaluation data.</div>}\n"
        "      {rowsSorted.map((r, i) => (\n"
        "        <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>\n"
        "          <Card><CardHeader><CardTitle className='flex items-center justify-between text-base'><span>{r.artifact_type}</span><span className='text-sm text-muted-foreground'>overall {( (r.overall||0)*100).toFixed(0)}%</span></CardTitle></CardHeader>\n"
        "            <CardContent>\n"
        "              <div className='grid grid-cols-3 gap-2 sm:grid-cols-5'>\n"
        "                {DIMS.map((dim) => {\n"
        "                  const v = (r.scores && r.scores[dim]) || 0;\n"
        "                  return (<div key={dim} className='rounded-md border p-2'>\n"
        "                    <div className='text-xs text-muted-foreground'>{dim}</div>\n"
        "                    <div className='text-sm font-medium'>{(v*100).toFixed(0)}%</div>\n"
        "                  </div>);\n"
        "                })}\n"
        "              </div>\n"
        "            </CardContent>\n"
        "          </Card>\n"
        "        </motion.div>\n"
        "      ))}\n"
        "    </div>\n"
        "  );\n"
        "}\n")

    # ---- pages (fixed heuristic-driven frontend) -------------------------
    # We ignore the model's stub pages and emit a consistent, polished app:
    # sidebar layout + 6 routes, each rendering a real component that reads
    # the compiled IRs via /api/*.
    def _page(rel: str, body: str) -> None:
        _write(app_root, rel, body)

    def _shell(title: str, comp: str, import_line: str) -> str:
        # client page with sidebar + animated content
        return (
            "'use client';\n"
            f"{import_line}\n"
            "import Sidebar from '../../components/Sidebar';\n"
            "import { motion } from 'framer-motion';\n"
            "export default function Page() {\n"
            "  return (\n"
            "    <div className='flex min-h-screen'>\n"
            "      <Sidebar />\n"
            "      <main className='grid-bg flex-1 overflow-auto p-8'>\n"
            "        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>\n"
            f"          <h1 className='mb-1 text-2xl font-semibold tracking-tight'>{title}</h1>\n"
            f"          <p className='mb-6 text-sm text-muted-foreground'>Compiled from your knowledge base.</p>\n"
            f"          <{comp} />\n"
            "        </motion.div>\n"
            "      </main>\n"
            "    </div>\n"
            "  );\n"
            "}\n"
        )

    # Overview (stats fetched live)
    _page("app/page.tsx",
          "'use client';\n"
          "import { useEffect, useState } from 'react';\n"
          "import Sidebar from '../components/Sidebar';\n"
          "import { StatCard } from '../components/StatCard';\n"
          "import { motion } from 'framer-motion';\n"
          "export default function Page() {\n"
          "  const [s, setS] = useState<any>(null);\n"
          "  useEffect(() => {\n"
          "    Promise.all([\n"
          "      fetch('/api/entities').then((r) => r.json()),\n"
          "      fetch('/api/graph').then((r) => r.json()),\n"
          "      fetch('/api/reasoning').then((r) => r.json()),\n"
          "      fetch('/api/semantic').then((r) => r.json()),\n"
          "    ]).then(([e, g, r, sm]) => setS({\n"
          "      entities: (e.entities || []).length,\n"
          "      nodes: (g.nodes || []).length,\n"
          "      edges: (g.edges || []).length,\n"
          "      obs: (r.observations || []).length,\n"
          "      themes: ((sm.themes || sm.clusters) || []).length,\n"
          "    }));\n"
          "  }, []);\n"
          "  return (\n"
          "    <div className='flex min-h-screen'>\n"
          "      <Sidebar />\n"
          "      <main className='grid-bg flex-1 overflow-auto p-8'>\n"
          "        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>\n"
          "          <h1 className='text-2xl font-semibold tracking-tight'>Knowledge Overview</h1>\n"
          "          <p className='mb-6 text-sm text-muted-foreground'>A compiled map of entities, relations, reasoning and themes extracted from your corpus.</p>\n"
          "          <div className='grid grid-cols-2 gap-4 lg:grid-cols-5'>\n"
          "            <StatCard label='Entities' value={s?.entities ?? '—'} sub='extracted terms' />\n"
          "            <StatCard label='Graph nodes' value={s?.nodes ?? '—'} sub='concepts' />\n"
          "            <StatCard label='Relations' value={s?.edges ?? '—'} sub='edges' />\n"
          "            <StatCard label='Observations' value={s?.obs ?? '—'} sub='reasoning' />\n"
          "            <StatCard label='Themes' value={s?.themes ?? '—'} sub='clusters' />\n"
          "          </div>\n"
          "          <p className='mt-8 text-sm text-muted-foreground'>Use the sidebar to explore the entity explorer, interactive knowledge graph, reasoning trace, theme clusters, and the evaluation scorecard.</p>\n"
          "        </motion.div>\n"
          "      </main>\n"
          "    </div>\n"
          "  );\n"
          "}\n")

    _page("app/entities/page.tsx", _shell("Entities", "EntityExplorer", "import EntityExplorer from '../../components/EntityExplorer';"))
    _page("app/graph/page.tsx", _shell("Knowledge Graph", "GraphCanvas", "import GraphCanvas from '../../components/GraphCanvas';"))
    _page("app/reasoning/page.tsx", _shell("Reasoning Trace", "ReasoningPanel", "import ReasoningPanel from '../../components/ReasoningPanel';"))
    _page("app/themes/page.tsx", _shell("Theme Clusters", "ThemeClusters", "import ThemeClusters from '../../components/ThemeClusters';"))
    _page("app/evaluation/page.tsx",
          _shell("Evaluation", "EvaluationDashboard", "import EvaluationDashboard from '../../components/EvaluationDashboard';"))

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
