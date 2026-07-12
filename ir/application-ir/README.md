# Application IR — Formal Specification

**Artifact type:** `application-ir`
**Produced by:** `pass-09-specifications`, `pass-10-software`
**Consumed by:** deployment targets (Next.js scaffold, etc.)

## Purpose
The Application IR is the *highest* intermediate representation: a deployable
software design compiled from knowledge. It is structured so a generator can
emit real source files from it without further reasoning.

## Containers
* **architecture** — layered design + rationale.
* **pages** — user-facing routes/screens.
* **components** — reusable UI/domain units.
* **routes** — URL → page mapping.
* **apis** — endpoints the app exposes.
* **deployment plan** — how to ship it.

## Field specification
* `specification.json` — `{requirements:[], data_model:{}, capabilities:[]}`
* `artifact.json` (full) — `{architecture, pages:[], components:[], routes:[],
  apis:[], deployment_plan}`
* Derived views: `architecture.mmd`, `deployment.md`.

## Invariants
* Each page maps to a theme; each component to a requirement/capability.
* `data_model` stays consistent with `graph-ir` node/edge types.
* Every component has a backing requirement (else `UNREFERENCED_ENTITY`).
* The compiler *plans* deployment; it does not execute it.

## Diagnostics emitted
`UNREFERENCED_ENTITY`, `HALLUCINATION_SUSPECT` (capability with no IR basis).
