#!/usr/bin/env python3
"""pass-10-software entrypoint (model-required -> code generation).

Consumes the Application IR and *generates a deployable Next.js (App Router)
scaffold* into ``<build>/app/``. This is a deterministic transform from the IR
to files — the intelligence lives in the Application IR (produced by the
model-required spec + layout passes), so code generation itself is
reproducible and inspectable.

Emitted:
    app/package.json
    app/next.config.mjs
    app/tsconfig.json
    app/app/layout.tsx
    app/app/<route>/page.tsx        (one per route)
    app/components/<Component>.tsx  (one per component)
    app/app/api/<name>/route.ts    (one per api)
    app/README.md                   (deployment plan + provenance)

Invocation: python run.py <build_dir>
"""

from __future__ import annotations

import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from compiler.core import ArtifactStore, DiagnosticEmitter, evaluate_artifact, write_evaluation

PRODUCES = "application-ir"


def to_pascal(name: str) -> str:
    return "".join(w.capitalize() for w in name.replace("-", " ").replace("_", " ").split())


def route_dir(route: str) -> str:
    r = route.strip("/")
    return r if r else "index"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # The orchestrator forwards --port/--model/--embed-model to every model
    # pass; code generation is deterministic so we accept and ignore them.
    args = [a for a in argv if not a.startswith("--")]
    build_dir = args[0] if args else os.getcwd()
    store = ArtifactStore(build_dir)
    if not store.has(PRODUCES):
        print(f"error: missing input artifact: {PRODUCES}", file=sys.stderr)
        return 1
    app = store.read(PRODUCES)
    emitter = DiagnosticEmitter(PRODUCES, build_dir)

    app_root = os.path.join(build_dir, "app")
    os.makedirs(os.path.join(app_root, "app"), exist_ok=True)
    os.makedirs(os.path.join(app_root, "components"), exist_ok=True)
    os.makedirs(os.path.join(app_root, "app", "api"), exist_ok=True)

    # package.json
    pkg = {
        "name": "knowledge-compiled-app",
        "version": "0.1.0",
        "private": True,
        "scripts": {"dev": "next dev", "build": "next build", "start": "next start"},
        "dependencies": {
            "next": "14.2.5",
            "react": "18.3.1",
            "react-dom": "18.3.1",
        },
    }
    _write(app_root, "package.json", json.dumps(pkg, indent=2))

    _write(
        app_root,
        "next.config.mjs",
        "/** @type {import('next').NextConfig} */\nexport default {};\n",
    )
    _write(
        app_root,
        "tsconfig.json",
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2017",
                    "lib": ["dom", "dom.iterable", "esnext"],
                    "jsx": "preserve",
                    "module": "esnext",
                    "moduleResolution": "bundler",
                    "strict": True,
                },
                "include": ["**/*.ts", "**/*.tsx"],
            },
            indent=2,
        ),
    )

    # layout
    _write(
        app_root,
        os.path.join("app", "layout.tsx"),
        "export default function RootLayout({\n"
        "  children,\n"
        "}: {\n"
        "  children: React.ReactNode;\n"
        "}) {\n"
        "  return (\n"
        "    <html lang=\"en\">\n"
        "      <body>{children}</body>\n"
        "    </html>\n"
        "  );\n"
        "}\n",
    )

    pages = app.get("pages", [])
    components = {c.get("id"): c for c in app.get("components", [])}
    # page per route
    for p in pages:
        rdir = route_dir(p.get("route", "/"))
        comp_names = [
            to_pascal(components[c]["name"]) if c in components else to_pascal(str(c))
            for c in p.get("components", [])
        ]
        imports = "\n".join(
            f'import {n} from "@/components/{n}";' for n in comp_names
        )
        body = "\n".join(f"      <{n} />" for n in comp_names) or "      <p>No components.</p>"
        code = (
            f'// page: {p.get("title", p.get("id"))} (route {p.get("route")})\n'
            f"{imports}\n"
            f"export default function Page() {{\n"
            f"  return (\n"
            f"    <main>\n"
            f"      <h1>{p.get('title', p.get('id'))}</h1>\n"
            f"{body}\n"
            f"    </main>\n"
            f"  );\n"
            f"}}\n"
        )
        _write(app_root, os.path.join("app", "app", rdir, "page.tsx"), code)

    # components
    for c in app.get("components", []):
        name = to_pascal(c.get("name", c.get("id")))
        resp = c.get("responsibility", "Generated component.")
        code = (
            f"// {resp}\n"
            f"export default function {name}() {{\n"
            f"  return <div className=\"{name}\">{name}</div>;\n"
            f"}}\n"
        )
        _write(app_root, os.path.join("components", f"{name}.tsx"), code)

    # api routes
    for api in app.get("apis", []):
        name = api.get("path", "/").strip("/").replace("/", "_") or "endpoint"
        purpose = api.get("purpose", "API endpoint")
        code = (
            f"// {purpose}\n"
            f"import {{ NextResponse }} from \"next/server\";\n\n"
            f"export async function {api.get('method', 'GET')}(\n"
            f"  _req: Request,\n"
            f") {{\n"
            f"  return NextResponse.json({{ ok: true }});\n"
            f"}}\n"
        )
        adir = os.path.join("app", "app", "api", name)
        _write(app_root, os.path.join(adir, "route.ts"), code)

    # deployment README
    dp = app.get("deployment_plan", {})
    readme = (
        "# Knowledge-Compiled Application\n\n"
        "Generated by the Knowledge Compiler (`pass-10-software`) from the "
        "Application IR. This is a Next.js App Router scaffold.\n\n"
        f"## Architecture\n{app.get('architecture', {}).get('rationale', 'n/a')}\n\n"
        "## Pages\n"
        + "\n".join(f"- `{p.get('route')}` — {p.get('title')}" for p in pages)
        + "\n\n## Deployment\n"
        f"- target: `{dp.get('target', 'unknown')}`\n"
        f"- prerequisites: {', '.join(dp.get('prerequisites', [])) or 'none'}\n"
        "### steps\n"
        + "\n".join(f"{i+1}. {s}" for i, s in enumerate(dp.get('steps', [])))
        + "\n"
    )
    _write(app_root, "README.md", readme)

    # diagnostics: warn on empty pages/apis
    if not pages:
        emitter.warning("MISSING_EVIDENCE", "no pages in application-ir")
    if not app.get("components"):
        emitter.warning("MISSING_EVIDENCE", "no components in application-ir")

    # record the generated artifact + emit metadata
    meta = store.write(
        PRODUCES, app, pass_id="pass-10-software",
        source_artifacts=["application-ir"], schema_id=PRODUCES,
    )
    # also write a manifest of generated files for inspectability
    manifest = {"generated_files": sorted(_walk(app_root))}
    with open(os.path.join(app_root, "manifest.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, indent=2))
    ev = evaluate_artifact(PRODUCES, app, meta, hints={"reproducibility": 1.0})
    write_evaluation(build_dir, PRODUCES, ev)
    emitter.write()
    print(
        f"wrote Next.js app to {app_root} "
        f"({len(manifest['generated_files'])} files, eval {ev.overall:.3f})"
    )
    return 0


def _write(root, rel, content):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(content)


def _walk(root):
    out = []
    for dp, _, files in os.walk(root):
        for f in files:
            out.append(os.path.relpath(os.path.join(dp, f), root))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
