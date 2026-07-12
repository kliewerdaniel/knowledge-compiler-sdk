You are the Software Generation pass (final stage).
INPUT: build/application-ir/specification.json, build/reasoning-ir/artifact.json, build/semantic-ir/*
OUTPUT: build/application-ir/{artifact.json,metadata.json,diagnostics.json, architecture.mmd, deployment.md}

TASK: Produce the full Application IR:
  architecture: {layers:[], rationale}
  pages[]:       {id, title, route, components:[], theme_ref}
  components[]:  {id, name, props:[], responsibility}
  routes[]:      {path, page_id, method}
  apis[]:        {path, method, purpose, request, response}
  deployment_plan: {target, steps:[], prerequisites:[]}
RULES:
  - Each page maps to a theme; each component to a capability/requirement.
  - Emit UNREFERENCED_ENTITY for any component with no backing requirement.
  - Also write architecture.mmd (Mermaid) and deployment.md. Do NOT execute the
    deploy; only plan it.
