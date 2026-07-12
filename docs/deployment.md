# Deployment

The Knowledge Compiler's final IR — the Application IR — is a *deployable
software design*, not a running app. This document explains how artifacts
compose into software and how deployment is planned (and why the compiler
itself never deploys).

## From knowledge to software

The Application IR carries enough structure to generate real source:

- `architecture.layers[]` → folder/module structure.
- `pages[]` + `routes[]` → Next.js `app/` routes (or any router).
- `components[]` → React/TSX components (or framework equivalents).
- `apis[]` → route handlers / endpoints.
- `data_model` (from the Graph IR) → TypeScript interfaces + a schema.
- `deployment_plan` → the steps an agent or CI runs to ship it.

Because every element cites a knowledge source (theme, observation, or
requirement), the generated app is **traceable to the corpus that produced it**.
That traceability is the project's core value: the software is a compiled
artifact of human knowledge, not a black-box generation.

## What the compiler produces vs. what deploys it

| Concern                | Who does it                                   |
|------------------------|-----------------------------------------------|
| Compile knowledge → IR | the Knowledge Compiler (this repo)            |
| Generate source files  | `pass-10-software` / `skills/code-generation` |
| Install dependencies   | agent or CI (e.g. `npm install`)              |
| Build & deploy         | agent, CI, or platform (e.g. Vercel)          |

The compiler **plans** deployment by writing `deployment_plan` + `deployment.md`
and emits `UNREFERENCED_ENTITY` for any deploy step with no IR basis. It does
**not** run `vercel deploy` — keeping orchestration pure and reproducible, and
respecting the principle that the compiler is infrastructure, not an operator.

## Example: a Next.js app from a research corpus

Given a corpus of sovereignty/AI notes, the pipeline might produce:

```
build/app/
  app/
    page.tsx                 # home (theme_ref: "sovereign-stack")
    architecture/page.tsx    # theme_ref: "compiler-theory"
    api/knowledge/route.ts   # from apis[].path "/api/knowledge"
  components/
    GraphView.tsx            # component mapped to requirement R-3
  lib/
    types.ts                 # TS interfaces from data_model
  deployment.md              # Vercel static export steps
```

Each file's existence is justified by an IR element; deleting that element
( or its source claim) would remove the file on the next compile. That is
*source-controlled reasoning*: the software is a function of the knowledge.

## Reproducibility of the deploy

Because the entire build directory is static and committed:

1. `git checkout` the build dir → you have the exact compiled knowledge.
2. Re-run `python -m compiler.run --source . --target application-ir` → identical
   artifacts (deterministic passes) + a planned set of model passes.
3. An agent fills the model passes; the result is reviewable as a diff.

No conversation history is required to understand or reproduce what was built.

## Recommended CI shape

See `.github/workflows/ci.yml`: it installs `pyyaml` + `jsonschema`, runs the
pytest suite (registry, parse, orchestration, evaluation), and validates that
every committed artifact conforms to its schema. Deployment to a live platform
is a *separate* job an operator triggers, keeping the compiler's own CI free of
secrets and side effects.
