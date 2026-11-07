"""Run the golden set through every CONFIGURED engine and print them side by side.

    python eval/bakeoff.py [--yes] [--no-cache]

Engines that are not configured are listed as such (never simulated). Results apply only to our golden set; its size
is printed. Cost uses real token/page usage x the constants you set in rules/pricing.yaml (n/a until you set them).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.engines import list_engines  # noqa: E402
from eval.run_eval import load_golden, run_eval, uncached_files  # noqa: E402


def main(argv: list[str]) -> int:
    golden = load_golden()
    engines = list_engines()
    ready = [e["name"] for e in engines if e["configured"]]
    for e in engines:
        print(f"{e['name']:<14}{'ready' if e['configured'] else e['reason']}")
    n_calls = len(golden) * len(ready)
    if "--yes" not in argv and (uncached_files("--no-cache" not in argv, golden) or any(n != "claude_pdf" for n in ready)):
        print(f"\nThis would make up to {n_calls} LLM call(s) (more with retries). Re-run with --yes to proceed.", file=sys.stderr)
        return 3
    runs = {}
    for name in ready:
        runs[name] = run_eval(use_cache="--no-cache" not in argv, allow_llm=True, engine=name, golden=golden, log=lambda *_: None)
    if not runs:
        print("\nNo engine is configured.")
        return 2
    print(f"\nGolden set: {len(golden)} documents ({sum(g['synthetic'] for g in golden)} synthetic). "
          f"Results apply only to this set.\n")
    print(f"{'engine':<14}{'F1':>7}{'ground':>8}{'halluc':>8}{'abstain':>9}{'latency s':>11}{'cost/doc':>11}")
    for n, r in runs.items():
        ms = list(r["metrics"].values())
        lat = sum(m["latency_s"] for m in ms) / len(ms)
        cost = [m["cost_usd"] for m in ms if m.get("cost_usd") is not None]
        o = r["overall"]
        print(f"{n:<14}{o['f1']:>7}{o['grounding_pass_rate']:>8}{o['hallucinations']:>8}{o['abstention_rate']:>9}"
              f"{lat:>11.2f}{(f'{sum(cost) / len(cost):.4f}' if cost else 'n/a'):>11}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
