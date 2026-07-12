# Purpose — Code Generation

Emit a concrete, deployable source scaffold (e.g. a Next.js tree) from the Application IR. Plans files; does not run builds.

## Behaviour
1. Read declared input artifact(s).
2. Perform exactly one conceptual operation.
3. Write output artifact.
4. Emit diagnostics.
5. Emit evaluation.
