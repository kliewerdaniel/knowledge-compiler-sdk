# Markdown Parsing — Agent Skill

**Skill id:** `parsing`
**Produces:** `markdown-ir`
**Consumes:** `(raw Markdown)`
**Deterministic:** yes

Deterministically transform raw Markdown source into a Markdown IR: documents, section hierarchy, inline citations, and a document graph. No inference; pure syntax + structure.

This skill is independently reusable: an autonomous agent loads it, reads the declared input artifact, performs the behaviour in `purpose.md`, and writes the declared output artifact following `artifact-schema.json`.
