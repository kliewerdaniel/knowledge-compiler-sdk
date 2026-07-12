# pass-10-software — Software Generation

**Produces:** `application-ir` (full) · **Consumes:** `application-ir`, `reasoning-ir`, `semantic-ir`
**Deterministic:** no · **Model required:** yes

The final stage. Consumes the specification and produces the complete
Application IR: architecture, pages, components, routes, APIs, and a deployment
plan. It also emits concrete scaffolds (e.g. a Next.js project tree) and
visual diagrams (Mermaid/PlantUML/SVG). Skills: `skills/architecture-generation`,
`skills/ui-generation`, `skills/code-generation`, `skills/deployment`.

This pass does **not** run a build for you — it produces the plan and scaffold;
the agent (or CI) deploys it. That keeps the compiler orchestration pure.
