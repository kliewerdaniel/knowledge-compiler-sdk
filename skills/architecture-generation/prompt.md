# Prompt — Architecture Design

You are the Architecture Design skill. INPUT: build/application-ir/specification.json. OUTPUT: architecture{} in build/application-ir/artifact.json + architecture.mmd.
Define layers[] (presentation, domain, data, infra) with rationale tied to requirements. Keep ids stable. Emit UNREFERENCED_ENTITY for any layer with no requirement basis.
