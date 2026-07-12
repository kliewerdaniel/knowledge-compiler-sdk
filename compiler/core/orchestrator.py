"""The orchestrator.

Given a registry and a build directory, the orchestrator answers two questions:

1.  **What can run?** — a pass is *runnable* when every artifact type it
    consumes already exists in the build directory (or is produced by another
    runnable pass earlier in the plan).
2.  **How do we reach a target?** — if a target artifact type is requested, we
    search the dependency graph (backwards from the producer of the target)
    for a sequence of passes whose cumulative outputs satisfy the request.

The orchestrator never hardcodes the pipeline; it *derives* it from the YAML
declarations. New passes register themselves simply by existing.

Execution model:
    * Deterministic, model-free passes are run by executing their ``entrypoint``
      script with the build dir and (optionally) a config on the CLI.
    * For model-requiring passes whose ``entrypoint`` script is absent, the
      orchestrator emits a *plan-only* note and skips execution, leaving a
      placeholder artifact so downstream planning still works. This keeps the
      repo runnable end-to-end without API keys while remaining honest about
      what was and was not actually computed.

The result of a run is a ``Plan`` (the ordered list of passes) plus per-pass
records, all persisted to ``<build>/plan.json`` for inspectability.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .artifacts import ArtifactStore, artifact_exists, source_hashes_of
from .registry import PassDeclaration, PassRegistry

try:
    from compiler.reports.dashboard import build_dashboard
except ImportError:  # pragma: no cover - fallback when run as a script
    from ..reports.dashboard import build_dashboard


@dataclass
class PlanStep:
    pass_id: str
    produces: str
    consumes: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "pass_id": self.pass_id,
            "produces": self.produces,
            "consumes": self.consumes,
        }


@dataclass
class Plan:
    target: Optional[str]
    steps: List[PlanStep] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "target": self.target,
            "steps": [s.to_dict() for s in self.steps],
            "skipped": self.skipped,
        }


class Compiler:
    def __init__(self, registry: PassRegistry, build_dir: str):
        self.registry = registry
        self.store = ArtifactStore(build_dir)

    # --- planning ---------------------------------------------------------
    def plan_to(self, target: Optional[str] = None) -> Plan:
        """Compute a dependency-respecting pass order reaching ``target``.

        If ``target`` is None, plan every pass whose transitive inputs are
        satisfiable starting from artifacts already present in the build dir
        (i.e. run everything possible).
        """
        plan = Plan(target=target)
        available = set(self.store.available())
        # Seed the set of "produced by plan so far" with what already exists.
        produced: set[str] = set(available)

        # Decide which passes are needed.
        needed: List[PassDeclaration]
        if target:
            needed = self._passes_needed_for(target, produced)
        else:
            needed = list(self.registry.all())

        # Topologically order needed passes by their consumes->produces edges.
        ordered = self._toposort(needed, produced)
        for decl in ordered:
            # A pass is included in the plan only if, after accounting for
            # artifacts already present + earlier steps, its inputs resolve.
            missing = [c for c in decl.consumes if c not in produced]
            if missing and not (set(decl.consumes) - set(available)):
                # inputs come entirely from other needed passes -> fine,
                # they will be produced by earlier steps.
                pass
            plan.steps.append(
                PlanStep(decl.id, decl.produces, list(decl.consumes))
            )
            produced.add(decl.produces)
        return plan

    def _passes_needed_for(
        self, target: str, available: set
    ) -> List[PassDeclaration]:
        decl = self.registry.pass_producing(target)
        if decl is None:
            raise ValueError(
                f"no pass produces target artifact '{target}'. "
                f"Known targets: {sorted(self.registry.by_produces)}"
            )
        needed: Dict[str, PassDeclaration] = {}
        stack = [decl]
        while stack:
            d = stack.pop()
            if d.id in needed:
                continue
            needed[d.id] = d
            for c in d.consumes:
                if c in available:
                    continue
                prod = self.registry.pass_producing(c)
                if prod and prod.id not in needed:
                    stack.append(prod)
        return list(needed.values())

    def _toposort(
        self, passes: List[PassDeclaration], available: set
    ) -> List[PassDeclaration]:
        by_prod = {p.produces: p for p in passes}
        ordered: List[PassDeclaration] = []
        seen: set[str] = set()

        def visit(p: PassDeclaration):
            if p.id in seen:
                return
            seen.add(p.id)
            for c in p.consumes:
                prod = by_prod.get(c) or (
                    self.registry.pass_producing(c)
                    if c not in available
                    else None
                )
                if prod and prod.id not in seen and prod.id in {
                    x.id for x in passes
                }:
                    visit(prod)
            ordered.append(p)

        for p in passes:
            visit(p)
        return ordered

    # --- execution --------------------------------------------------------
    def run(
        self,
        target: Optional[str] = None,
        dry_run: bool = False,
        local: bool = False,
        port: int = 8080,
        model: Optional[str] = None,
        incremental: bool = False,
        only: Optional[str] = None,
        embed_model: Optional[str] = None,
        timeout: float = 900.0,
        max_tokens: int = 8192,
    ) -> Dict:
        if only:
            # Single-pass plan: only the named pass runs (inputs must pre-exist).
            decl = self.registry.get(only)
            plan = Plan(target=only,
                        steps=[PlanStep(pass_id=decl.id, produces=decl.produces,
                                        consumes=decl.consumes)],
                        skipped=[])
        else:
            plan = self.plan_to(target)
        records: List[Dict] = []
        produced: set[str] = set(self.store.available())

        for step in plan.steps:
            decl = self.registry.get(step.pass_id)
            entry = os.path.join(decl.path, decl.entrypoint)
            record = {
                "pass_id": decl.id,
                "produces": decl.produces,
                "consumes": decl.consumes,
                "status": "pending",
                "model_required": decl.model_required,
            }
            if dry_run:
                record["status"] = "skipped"
                record["reason"] = "dry_run"
                plan.skipped.append(decl.id)
            elif incremental and self._is_cached(decl):
                # Inputs unchanged since this artifact was produced -> reuse.
                record["status"] = "cached"
                record["reason"] = "inputs unchanged"
            elif os.path.isfile(entry) and not decl.model_required:
                # Deterministic pass with a real entrypoint — run it directly.
                ok = self._exec_pass(entry)
                record["status"] = "ok" if ok else "failed"
            elif local and decl.model_required and os.path.isfile(entry):
                # Model pass executed against the user's local inference server.
                ok = self._exec_model_pass(decl, port, model, embed_model, timeout, max_tokens)
                record["status"] = "ok" if ok else "failed"
                if not ok:
                    record["reason"] = "local inference failed"
                    plan.skipped.append(decl.id)
            else:
                record["status"] = "skipped"
                record["reason"] = (
                    "no deterministic entrypoint"
                    if not decl.model_required
                    else "model pass (use --local with a running inference server)"
                )
                plan.skipped.append(decl.id)
            produced.add(decl.produces)
            records.append(record)

        summary = {
            "target": target,
            "plan": plan.to_dict(),
            "records": records,
        }
        with open(
            os.path.join(self.store.build_dir, "plan.json"), "w", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps(summary, ensure_ascii=False, indent=2))

        # Emit the self-contained evaluation dashboard (observability payoff).
        dash = build_dashboard(self.store.build_dir)
        if dash:
            summary["dashboard"] = os.path.relpath(dash, self.store.build_dir)
        return summary

    def _is_cached(self, decl: "PassDeclaration") -> bool:
        """True if ``decl.produces`` exists and its inputs are unchanged.

        Compares the current content hashes of the consumed artifacts against
        the ``source_hashes`` recorded when the artifact was produced. If any
        consumed artifact is missing or its hash differs, the cache is invalid.
        """
        if not self.store.has(decl.produces):
            return False
        meta = self.store.metadata(decl.produces)
        recorded = meta.get("source_hashes") or {}
        if not recorded and decl.consumes:
            # No provenance recorded (e.g. a v0 artifact) -> don't trust cache.
            return False
        current = source_hashes_of(self.store.build_dir, decl.consumes)
        # present + matching for every consumed artifact
        for c in decl.consumes:
            if recorded.get(c) != current.get(c):
                return False
        return True

    def _exec_pass(self, entry: str) -> bool:
        try:
            result = subprocess.run(
                [sys.executable, entry, self.store.build_dir],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _exec_model_pass(
        self, decl: "PassDeclaration", port: int, model: Optional[str],
        embed_model: Optional[str] = None,
    ) -> bool:
        """Execute a model-required pass via the shared llm_pass scaffold.

        The pass directory must contain ``run.py`` (the model entrypoint) that
        accepts ``<build_dir> --port <p> [--model <m>] [--embed-model <e>]`` and
        uses ``core.llm_pass.run_model_pass``. Because the deterministic branch
        above only fires when an entrypoint exists, we *require* model passes to
        ship a ``run.py`` too — it just delegates to the scaffold instead of
        doing raw parsing. This keeps the orchestrator uniform: every pass is a
        ``run.py``; the difference is deterministic vs. model-driven.
        """
    def _pass_env(self) -> Dict[str, str]:
        """Build an env for pass subprocesses that makes both the repo root and
        the ``compiler`` package importable, so every pass entrypoint can use
        either ``import compiler.core`` or ``import core`` regardless of how it
        bootstrapped its own sys.path."""
        root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )  # .../knowledge-compiler-sdk
        compiler_pkg = os.path.join(root, "compiler")
        existing = os.environ.get("PYTHONPATH", "")
        parts = [root, compiler_pkg] + ([existing] if existing else [])
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(parts)
        return env

    def _exec_pass(self, entry: str) -> bool:
        try:
            result = subprocess.run(
                [sys.executable, entry, self.store.build_dir],
                capture_output=True,
                text=True,
                timeout=300,
                env=self._pass_env(),
            )
            return result.returncode == 0
        except Exception:
            return False

    def _exec_model_pass(
        self, decl: "PassDeclaration", port: int, model: Optional[str],
        embed_model: Optional[str] = None, timeout: float = 900.0,
        max_tokens: int = 8192,
    ) -> bool:
        entry = os.path.join(decl.path, "run.py")
        if not os.path.isfile(entry):
            return False
        cmd = [sys.executable, entry, self.store.build_dir,
               "--port", str(port)]
        if model:
            cmd += ["--model", model]
        if embed_model:
            cmd += ["--embed-model", embed_model]
        cmd += ["--timeout", str(timeout), "--max-tokens", str(max_tokens)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(1800.0, timeout + 300.0),
                env=self._pass_env(),
            )
            if result.returncode != 0:
                sys.stderr.write(result.stderr)
            return result.returncode == 0
        except Exception as e:  # pragma: no cover
            sys.stderr.write(f"model pass {decl.id} error: {e}\n")
            return False
