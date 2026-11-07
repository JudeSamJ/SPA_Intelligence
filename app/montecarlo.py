"""Probabilistic penalty simulator (seeded NumPy). ASSUMPTION-DRIVEN, not a forecast.

For each trial we draw a delay (days) from a user-set distribution (rules/simulation.yaml), then look up the
deterministic results for that many days: contractual penalty (app/penalty.py) and statutory entitlement
(app/statute_gap.py). Because every outcome comes from the same tested functions, a degenerate (fixed) distribution
reproduces the deterministic simulator exactly. No arithmetic about money happens in NumPy.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

import numpy as np
import yaml

from . import config
from .penalty import SimulationUnavailable, penalty_for_contract
from .schema import ContractData
from .statute_gap import compute_gap, effective_jurisdiction

LABEL = ("Assumption-driven: the delay distribution is a user assumption, not a prediction. "
         "No machine-learning delay forecast is used.")
MAX_DAYS = 3650


def sim_config() -> dict:
    return yaml.safe_load((config.RULES_DIR / "simulation.yaml").read_text())


# ------------------------------------------------------------------ delay distribution
def draw_delays(dist: dict, trials: int, seed: int, shift_days: float = 0.0) -> np.ndarray:
    """Integer delay days, shape (trials,). Same seed -> same draws."""
    rng = np.random.default_rng(seed)
    fam = dist["family"]
    if fam == "triangular":
        t = dist["triangular"]
        lo, mode, hi = float(t["min_days"]), float(t["mode_days"]), float(t["max_days"])
        if not lo <= mode <= hi:
            raise ValueError("triangular needs min_days <= mode_days <= max_days")
        x = np.full(trials, lo) if hi == lo else rng.triangular(lo, mode, hi, trials)
    elif fam == "lognormal":
        t = dist["lognormal"]
        if t["median_days"] <= 0 or t["sigma"] < 0:
            raise ValueError("lognormal needs median_days > 0 and sigma >= 0")
        x = rng.lognormal(np.log(float(t["median_days"])), float(t["sigma"]), trials)
    elif fam == "fixed":
        x = np.full(trials, float(dist["fixed"]["days"]))
    else:
        raise ValueError(f"unknown distribution family '{fam}'")
    x = np.clip(np.rint(x + shift_days), 0, MAX_DAYS).astype(int)
    return x


def parse_signal_csv(text: str) -> list[dict]:
    """CSV with header date,planned_progress_pct,actual_progress_pct. Raises ValueError with a clear message."""
    rows = []
    rd = csv.DictReader(io.StringIO(text.strip()))
    need = {"date", "planned_progress_pct", "actual_progress_pct"}
    if not rd.fieldnames or not need <= {h.strip() for h in rd.fieldnames}:
        raise ValueError("signal CSV needs the columns: date, planned_progress_pct, actual_progress_pct")
    for i, r in enumerate(rd, 2):
        try:
            rows.append({"date": date.fromisoformat(r["date"].strip()),
                         "planned": float(r["planned_progress_pct"]), "actual": float(r["actual_progress_pct"])})
        except (ValueError, TypeError, KeyError):
            raise ValueError(f"signal CSV line {i}: bad date or number") from None
    if not rows:
        raise ValueError("signal CSV has no data rows")
    return sorted(rows, key=lambda r: r["date"])


def signal_shift(rows: list[dict], cfg: dict) -> dict:
    last = rows[-1]
    gap = last["planned"] - last["actual"]
    raw = gap * float(cfg["days_per_gap_point"])
    m = float(cfg["max_shift_days"])
    shift = max(-m, min(m, raw))
    return {"as_of": last["date"].isoformat(), "gap_points": round(gap, 3), "days_per_gap_point": cfg["days_per_gap_point"],
            "shift_days": round(shift, 3), "clamped": shift != raw,
            "rule": "shift_days = clamp(latest (planned - actual) progress gap x days_per_gap_point, +/- max_shift_days)"}


# ------------------------------------------------------------------ outcomes per delay day (deterministic code)
def exposure_by_day(c: ContractData, days: np.ndarray, as_of: date, amounts_paid, pack_id: str | None,
                    rules: dict) -> dict:
    """{"contractual": array, "statutory": array|None, "cap": array(bool)|None, "reason": str|None}"""
    uniq = sorted(set(int(d) for d in np.unique(days)))
    con, sta, cap, reason = {}, {}, {}, None
    stat_ok = True
    for d in uniq:
        try:
            r = penalty_for_contract(c, d, rules)
            con[d], cap[d] = r["penalty"], bool(r["cap_reached"] and r["cap_amount"] is not None and r["penalty"] > 0)
        except SimulationUnavailable as e:
            return {"contractual": None, "statutory": None, "cap": None, "reason": str(e)}
        if stat_ok:
            g = compute_gap(c, d, as_of, amounts_paid, pack_id=pack_id, rules=rules)
            if g["can_compute"]:
                sta[d] = g["statutory"]["amount"]
            else:
                stat_ok, reason = False, g["reason"]
    lut = lambda m: np.array([m[int(d)] for d in days], dtype=float)           # noqa: E731
    return {"contractual": lut(con), "statutory": lut(sta) if stat_ok else None,
            "cap": np.array([cap[int(d)] for d in days]) if c.delay_cap.value is not None else None,
            "reason": None if stat_ok else reason}


def pct(a: np.ndarray, q: float) -> float:
    return round(float(np.percentile(a, q)), 2)


def summarize(a: Optional[np.ndarray]) -> Optional[dict]:
    if a is None:
        return None
    return {"p10": pct(a, 10), "p50": pct(a, 50), "p90": pct(a, 90), "mean": round(float(a.mean()), 2)}


def simulate_contract(c: ContractData, *, trials: int | None = None, seed: int | None = None,
                      dist: dict | None = None, as_of: date | None = None, amounts_paid=None,
                      signal_rows: list[dict] | None = None, pack_id: str | None = None,
                      delays: np.ndarray | None = None, cfg: dict | None = None) -> dict:
    cfg = cfg or sim_config()
    trials = int(trials or cfg["trials"])
    if not 1 <= trials <= cfg["max_trials"]:
        raise ValueError(f"trials must be between 1 and {cfg['max_trials']}")
    seed = cfg["seed"] if seed is None else int(seed)
    dist = dist or cfg["delay_distribution"]
    as_of = as_of or date.today()
    pack_id = pack_id or effective_jurisdiction(c)
    sig = signal_shift(signal_rows, cfg["signal"]) if signal_rows else None
    if delays is None:
        delays = draw_delays(dist, trials, seed, sig["shift_days"] if sig else 0.0)
    try:
        rules = config.load_rules(pack_id)
    except FileNotFoundError:
        rules = config.load_rules()
    ex = exposure_by_day(c, delays, as_of, amounts_paid, pack_id, rules)
    grace = c.grace_period_days.value or 0
    out = {"assumption_driven": True, "label": LABEL, "trials": trials, "seed": seed, "jurisdiction": pack_id,
           "currency": c.currency or rules.get("currency"),
           "assumptions": {"delay_distribution": dist, "signal": sig, "as_of": as_of.isoformat(),
                           "grace_days": grace, "cap_pct": c.delay_cap.value},
           "delay_days": summarize(delays.astype(float)),
           "prob_delay_exceeds_grace": round(float((delays > grace).mean()), 4),
           "prob_cap_binds": None if ex["cap"] is None else round(float(ex["cap"].mean()), 4),
           "contractual": summarize(ex["contractual"]), "statutory": summarize(ex["statutory"]),
           "shortfall": summarize(ex["statutory"] - ex["contractual"]) if ex["statutory"] is not None and ex["contractual"] is not None else None,
           "unavailable_reason": ex["reason"]}
    if ex["contractual"] is None:
        out["unavailable_reason"] = ex["reason"]
    # histogram + percentile curve for the charts
    hi = int(max(delays.max(), 1))
    edges = np.linspace(0, hi, 21)
    cnt, _ = np.histogram(delays, bins=edges)
    out["histogram"] = [{"from": round(float(edges[i]), 1), "to": round(float(edges[i + 1]), 1), "count": int(cnt[i])}
                        for i in range(20)]
    qs = list(range(5, 100, 5))
    out["quantiles"] = [{"q": q, "delay": pct(delays.astype(float), q),
                         "contractual": pct(ex["contractual"], q) if ex["contractual"] is not None else None,
                         "statutory": pct(ex["statutory"], q) if ex["statutory"] is not None else None} for q in qs]
    out["_vectors"] = {"delays": delays, "contractual": ex["contractual"], "statutory": ex["statutory"]}
    return out


def public(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}


def portfolio(contracts: list[tuple[str, str, ContractData]], **kw) -> dict:
    """Rollup across contracts with COMMON delay draws (one project-wide delay shock). Currencies are never mixed."""
    cfg = kw.get("cfg") or sim_config()
    trials = int(kw.get("trials") or cfg["trials"])
    seed = cfg["seed"] if kw.get("seed") is None else int(kw["seed"])
    dist = kw.get("dist") or cfg["delay_distribution"]
    sig = signal_shift(kw["signal_rows"], cfg["signal"]) if kw.get("signal_rows") else None
    delays = draw_delays(dist, trials, seed, sig["shift_days"] if sig else 0.0)
    rows, by_cur = [], {}
    for cid, name, c in contracts:
        r = simulate_contract(c, trials=trials, seed=seed, dist=dist, as_of=kw.get("as_of"), signal_rows=kw.get("signal_rows"),
                              delays=delays, cfg=cfg)
        v = r.pop("_vectors")
        rows.append({"contract_id": cid, "name": name, "currency": r["currency"], "jurisdiction": r["jurisdiction"],
                     "contractual": r["contractual"], "statutory": r["statutory"], "shortfall": r["shortfall"],
                     "prob_cap_binds": r["prob_cap_binds"], "unavailable_reason": r["unavailable_reason"]})
        if v["contractual"] is None:
            continue
        agg = by_cur.setdefault(r["currency"] or "?", {"contractual": np.zeros(trials), "statutory": np.zeros(trials),
                                                       "n": 0, "n_stat": 0})
        agg["contractual"] += v["contractual"]
        agg["n"] += 1
        if v["statutory"] is not None:
            agg["statutory"] += v["statutory"]
            agg["n_stat"] += 1
    totals = {}
    for cur, a in by_cur.items():
        st = a["statutory"] if a["n_stat"] else None
        totals[cur] = {"contracts": a["n"], "contracts_with_statute": a["n_stat"],
                       "contractual": summarize(a["contractual"]), "statutory": summarize(st),
                       "shortfall": summarize(st - a["contractual"]) if st is not None else None}
    return {"assumption_driven": True, "label": LABEL, "trials": trials, "seed": seed,
            "assumptions": {"delay_distribution": dist, "signal": sig},
            "delay_days": summarize(delays.astype(float)), "rows": rows, "totals_by_currency": totals,
            "note": "Currencies are never converted or mixed. A common delay draw is applied to every contract."}
