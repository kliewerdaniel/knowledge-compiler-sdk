"""Evaluation dashboard generator.

Builds a single, self-contained ``evaluation_dashboard.html`` from every
``<build>/<artifact>/evaluation.json``. The dashboard is local-first: no CDN,
no build step, no runtime services — it embeds the evaluation data inline and
renders with hand-rolled SVG so it opens straight from disk. This is the
"observability is the OS" payoff: the 9-dimension scorecard for every compiled
artifact, visualized.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

# Canonical 9 evaluation dimensions (order = display order).
DIMENSIONS = [
    "completeness",
    "correctness",
    "coverage",
    "consistency",
    "hallucination",
    "traceability",
    "provenance",
    "confidence",
    "reproducibility",
]

_DIM_LABEL = {d: d.capitalize() for d in DIMENSIONS}


def collect(build_dir: str) -> List[Dict[str, Any]]:
    """Read every evaluation.json in the build dir into a list of records."""
    records: List[Dict[str, Any]] = []
    if not os.path.isdir(build_dir):
        return records
    for name in sorted(os.listdir(build_dir)):
        ev_path = os.path.join(build_dir, name, "evaluation.json")
        if not os.path.isfile(ev_path):
            continue
        try:
            with open(ev_path, "r", encoding="utf-8") as fh:
                ev = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        scores = ev.get("scores", {}) or {}
        # Backfill any missing dimension so the chart stays full-width.
        norm = {d: float(scores.get(d, 0.0)) for d in DIMENSIONS}
        records.append({
            "artifact": name,
            "artifact_type": ev.get("artifact_type", name),
            "overall": float(ev.get("overall", 0.0)),
            "scores": norm,
            "notes": ev.get("notes", {}),
        })
    # Sort by overall score ascending so the weakest artifacts surface first.
    records.sort(key=lambda r: r["overall"])
    return records


def _bar_color(score: float) -> str:
    if score >= 0.75:
        return "#16a34a"   # green
    if score >= 0.5:
        return "#d97706"   # amber
    return "#dc2626"       # red


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def render_html(records: List[Dict[str, Any]], build_dir: str) -> str:
    """Render the dashboard HTML with the data embedded inline."""
    data = json.dumps(records, ensure_ascii=False)
    n = len(records)
    avg_overall = (sum(r["overall"] for r in records) / n) if n else 0.0

    # Per-dimension averages (for the radar/summary).
    dim_avg = {
        d: (sum(r["scores"][d] for r in records) / n) if n else 0.0
        for d in DIMENSIONS
    }

    cards = []
    for r in records:
        bars = []
        for d in DIMENSIONS:
            v = r["scores"][d]
            pct = int(round(v * 100))
            bars.append(
                f'<div class="dimrow"><span class="dimlabel">{_esc(_DIM_LABEL[d])}'
                f'</span><span class="track"><span class="fill" '
                f'style="width:{pct}%;background:{_bar_color(v)}"></span></span>'
                f'<span class="dimval">{pct}</span></div>'
            )
        cards.append(
            f'<section class="card">\n'
            f'  <header><h2>{_esc(r["artifact"])}</h2>'
            f'<span class="ovr" style="color:{_bar_color(r["overall"])}">'
            f'{int(round(r["overall"] * 100))}</span></header>\n'
            f'  <div class="bars">{"".join(bars)}</div>\n'
            f'</section>'
        )
    cards_html = "\n".join(cards) if cards else '<p class="empty">No evaluations found.</p>'

    dim_summary = "".join(
        f'<div class="dimrow"><span class="dimlabel">{_esc(_DIM_LABEL[d])}</span>'
        f'<span class="track"><span class="fill" style="width:'
        f'{int(round(dim_avg[d] * 100))}%;background:{_bar_color(dim_avg[d])}">'
        f'</span></span><span class="dimval">{int(round(dim_avg[d] * 100))}</span></div>'
        for d in DIMENSIONS
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Knowledge Compiler — Evaluation Dashboard</title>
<style>
  :root {{ --bg:#0b1120; --panel:#111a2e; --ink:#e2e8f0; --muted:#94a3b8; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
  header.top {{ padding:24px 28px 8px; }}
  header.top h1 {{ margin:0 0 4px; font-size:22px; }}
  header.top p {{ margin:0; color:var(--muted); font-size:13px; }}
  .wrap {{ padding:0 28px 40px; }}
  .summary {{ display:flex; gap:20px; align-items:center; flex-wrap:wrap;
             background:var(--panel); border-radius:12px; padding:18px 22px;
             margin:16px 0 24px; }}
  .summary .big {{ font-size:40px; font-weight:700; }}
  .summary .lbl {{ color:var(--muted); font-size:12px; text-transform:uppercase;
                  letter-spacing:.06em; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr));
          gap:16px; }}
  .card {{ background:var(--panel); border-radius:12px; padding:16px 18px; }}
  .card header {{ display:flex; justify-content:space-between; align-items:baseline;
                 margin-bottom:12px; border-bottom:1px solid #1e293b; padding-bottom:8px; }}
  .card h2 {{ margin:0; font-size:15px; font-family:ui-monospace,monospace; }}
  .card .ovr {{ font-size:26px; font-weight:700; }}
  .bars {{ display:flex; flex-direction:column; gap:6px; }}
  .dimrow {{ display:flex; align-items:center; gap:8px; font-size:12px; }}
  .dimlabel {{ width:104px; color:var(--muted); flex:none; }}
  .track {{ flex:1; height:8px; background:#1e293b; border-radius:5px; overflow:hidden; }}
  .fill {{ display:block; height:100%; border-radius:5px; }}
  .dimval {{ width:28px; text-align:right; font-variant-numeric:tabular-nums; }}
  .empty {{ color:var(--muted); }}
  .legend {{ color:var(--muted); font-size:12px; margin-top:18px; }}
</style>
</head>
<body>
<header class="top">
  <h1>Knowledge Compiler — Evaluation Dashboard</h1>
  <p>{n} artifact(s) evaluated · build: {_esc(os.path.basename(build_dir) or build_dir)}</p>
</header>
<div class="wrap">
  <div class="summary">
    <div><div class="big" style="color:{_bar_color(avg_overall)}">{int(round(avg_overall*100))}</div>
         <div class="lbl">Mean overall</div></div>
    <div style="flex:1; min-width:280px;">
      <div class="lbl" style="margin-bottom:6px;">Mean by dimension</div>
      {dim_summary}
    </div>
  </div>
  <div class="grid">
    {cards_html}
  </div>
  <div class="legend">Scores are 0–100. Green ≥ 75 · Amber ≥ 50 · Red &lt; 50.
    Computed by <code>compiler/core/evaluation.py</code> (structural heuristics + pass hints).</div>
</div>
<script>
  // The raw per-artifact data, embedded for inspection/export.
  window.__EVAL__ = {data};
</script>
</body>
</html>
"""


def build_dashboard(build_dir: str, out_name: str = "evaluation_dashboard.html") -> Optional[str]:
    """Scan evaluations and write the dashboard. Returns its path or None."""
    records = collect(build_dir)
    html = render_html(records, build_dir)
    out_path = os.path.join(build_dir, out_name)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path
