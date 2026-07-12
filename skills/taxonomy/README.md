# Taxonomy Construction — Agent Skill

**Skill id:** `taxonomy`
**Produces:** `ontology-ir (hierarchies)`
**Consumes:** `ontology-ir`
**Deterministic:** no (model-required)

Refine the ontology into a navigable taxonomy: layered is-a/part-of trees and canonical alias resolution. Makes the concept space browsable and disambiguated.

This skill is independently reusable: an autonomous agent loads it, reads the declared input artifact, performs the behaviour in `purpose.md`, and writes the declared output artifact following `artifact-schema.json`.
