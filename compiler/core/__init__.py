"""Knowledge Compiler SDK — core compiler infrastructure.

This package is the *engine* of the Knowledge Compiler. The engine itself is
standard-library + ``pyyaml`` so it runs in minimal agent sandboxes. Local
model inference is opt-in via ``core.inference`` (requires the ``openai``
package) and talks to **your own** OpenAI-compatible server (llama.cpp / Ollama
/ vLLM) on a port you control — no cloud API, no secret.

The core is organised around four ideas:

1.  **Artifacts** are immutable, version-controlled files written to a build
    directory. Every artifact is a directory named after its artifact type
    containing ``artifact.json`` (data), ``metadata.json`` (provenance) and
    ``diagnostics.json`` (compiler warnings/errors).
2.  **Passes** are declared declaratively in YAML. The orchestrator *discovers*
    them; it never hardcodes the pipeline.
3.  **The orchestrator** resolves dependencies between passes, plans a path
    from source Markdown to any target Intermediate Representation (IR), and
    executes only the passes whose inputs are satisfied.
4.  **Diagnostics and evaluation** are first-class outputs of every pass,
    exactly like warnings and optimisation reports in LLVM/GCC.

See ``docs/architecture.md`` for the full design rationale.
"""

from .artifacts import (
    ArtifactStore,
    artifact_exists,
    read_artifact,
    write_artifact,
)
from .registry import PassDeclaration, PassRegistry
from .orchestrator import Compiler, Plan
from .diagnostics import Diagnostic, DiagnosticEmitter, Severity
from .evaluation import Evaluation, evaluate_artifact, write_evaluation
from .inference import InferenceClient, extract_json
from .llm_pass import run_model_pass

__all__ = [
    "ArtifactStore",
    "artifact_exists",
    "read_artifact",
    "write_artifact",
    "PassDeclaration",
    "PassRegistry",
    "Compiler",
    "Plan",
    "Diagnostic",
    "DiagnosticEmitter",
    "Severity",
    "Evaluation",
    "evaluate_artifact",
    "InferenceClient",
    "extract_json",
    "run_model_pass",
]

__version__ = "0.1.0"
