"""SPA Intelligence: Streamlit demo. Run: streamlit run app/main.py"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app import config  # noqa: E402
from app.agent import BuyerAgent  # noqa: E402
from app.cashflow import CashflowUnavailable, at_risk_summary, build_schedule, milestone_rows  # noqa: E402
from app.extract import extract_contract, load_cached  # noqa: E402
from app.llm import calls_made  # noqa: E402
from app.penalty import SimulationUnavailable, penalty_for_contract, simulate  # noqa: E402
from app.schema import ContractData  # noqa: E402

RULES = config.load_rules()
BLUE, AMBER = "#2563eb", "#d97706"

st.set_page_config(page_title="SPA Intelligence", page_icon="🏢", layout="wide")


# ------------------------------------------------------------------ helpers
def aed(x) -> str:
    return "n/a" if x is None else f"AED {x:,.2f}"


def aed0(x) -> str:
    return "n/a" if x is None else f"AED {x:,.0f}"


def fmt_value(name: str, c: ContractData) -> str:
    item = getattr(c, name)
    v = item.value
    if name == "delay_cap":
        if v is not None:
            return f"{v:g}% of purchase price"
        return "No cap (stated in contract)" if item.source_quote else "Not stated"
    if v is None:
        return "Not stated"
    if name == "price":
        return f"AED {v:,.0f}"
    if name == "area_sqft":
        return f"{v:,.2f} sq ft"
    if name == "grace_period_days":
        return f"{v} days"
    if name == "delay_rate":
        basis = c.delay_basis.value
        return (f"{v:g}% per annum" if basis == "percent_per_annum"
                else f"AED {v:g} per sq ft per year" if basis == "fixed_per_sqft_per_year" else f"{v:g}")
    return str(v)


FIELD_LABELS = {
    "buyer": "Buyer", "unit_id": "Unit ID", "price": "Purchase price", "area_sqft": "Saleable area",
    "handover_date": "Handover date", "grace_period_days": "Grace period", "delay_rate": "Delay compensation rate",
    "delay_basis": "Delay basis", "delay_cap": "Delay compensation cap", "cancellation_clause": "Cancellation clause",
}


def load_contract(label: str, data: bytes, use_cache: bool = True):
    try:
        return extract_contract(data, source_name=label, use_cache=use_cache), None
    except Exception as e:  # network/API errors should show, not crash
        return None, f"{type(e).__name__}: {e}"


# ------------------------------------------------------------------ header + banner
st.title("🏢 SPA Intelligence")
st.warning(f"**{RULES['disclaimer']}** Figures are extracted from the uploaded contract and computed "
           f"deterministically; verify against the source document.", icon="⚖️")

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Contract")
    samples = sorted(config.SAMPLES_DIR.glob("*.pdf"))
    source = st.radio("Source", ["Sample", "Upload PDF"], horizontal=True)
    pdf_bytes, label = None, None
    if source == "Sample":
        if samples:
            choice = st.selectbox("Sample SPA", samples, format_func=lambda p: p.name)
            pdf_bytes, label = choice.read_bytes(), choice.name
        else:
            st.info("No samples found. Run `python scripts/generate_samples.py`.")
    else:
        up = st.file_uploader("SPA PDF", type=["pdf"])
        if up:
            pdf_bytes, label = up.getvalue(), up.name
    st.caption(f"Model: `{config.model_tag()}`  \nJurisdiction rules: `{RULES['jurisdiction']}`")
    calls_slot = st.empty()   # updated again after an extraction so the count is never stale

    def show_calls():
        calls_slot.caption(f"LLM calls this session: {calls_made()} / {config.MAX_LLM_CALLS} (cap)")
    show_calls()
    if not config.llm_configured():
        st.caption("⚠️ " + config.setup_hint() + " Cached extractions still load.")

if pdf_bytes is None:
    st.info("Pick a sample or upload an SPA PDF in the sidebar.")
    st.stop()

def run_extraction(force: bool):
    """Run the LLM extraction with a visible progress panel. Returns ContractData or None."""
    before = calls_made()
    with st.status(f"Extracting **{label}** with `{config.model_tag()}`…", expanded=True) as status:
        st.write("① Reading PDF text and sending it to the model")
        st.write("② Waiting for the model's structured answer (this is the LLM call)…")
        c, err = load_contract(label, pdf_bytes, use_cache=not force)
        if err:
            status.update(label="Extraction failed", state="error", expanded=True)
            st.error(err)
            return None
        used = calls_made() - before
        st.write(f"③ Validated, verified quotes against the PDF, checked totals: {len(c.warnings)} warning(s)")
        status.update(label=f"✅ Extraction complete: {used} LLM call(s) used", state="complete", expanded=False)
    msg = (f"{'Re-extracted' if force else 'Extracted'} {label} at {c.extracted_at} with `{c.model}`: "
           f"{used} LLM call(s) this time, {calls_made()}/{config.MAX_LLM_CALLS} this session.")
    st.session_state[f"extract_log_{c.file_hash}"] = msg
    show_calls()
    st.toast(f"Extraction complete ({used} LLM call)", icon="✅")
    return c


contract = load_cached(pdf_bytes)          # free: reads data/cache
if contract is None:
    holder = st.empty()
    with holder.container():
        st.info(f"**{label}** has not been extracted with `{config.model_tag()}` yet. Extraction makes 1 LLM call "
                f"(2 if the first output fails validation); the result is cached afterwards.")
        if not config.llm_configured():
            st.error(config.setup_hint())
            st.stop()
        clicked = st.button("Extract with LLM", type="primary")
    if not clicked:
        st.stop()
    holder.empty()                          # remove the button/info once started
    contract = run_extraction(force=False)
    if contract is None:
        st.stop()
else:
    with st.expander("🔄 Re-run extraction"):
        st.caption(f"Extracted {contract.extracted_at or 'earlier'} with `{contract.model}`. Re-running makes "
                   f"1 LLM call (2 if validation fails) and replaces the cached result.")
        if not config.llm_configured():
            st.caption(config.setup_hint())
        elif st.button("Re-run extraction now"):
            contract = run_extraction(force=True) or contract

tab_terms, tab_pen, tab_cash, tab_chat, tab_acc = st.tabs(
    ["📄 Extracted Terms", "⏱ Penalty Simulator", "💰 Cash-flow", "💬 Buyer Assistant", "🎯 Accuracy"])

# ------------------------------------------------------------------ Extracted terms
with tab_terms:
    st.subheader(f"{label}")
    log = st.session_state.get(f"extract_log_{contract.file_hash}")
    if log:
        st.success(log, icon="✅")
    elif contract.extracted_at:
        st.caption(f"Loaded from cache: extracted {contract.extracted_at} with `{contract.model}` (no LLM call made).")
    if contract.warnings:
        for w in contract.warnings:
            st.error(w, icon="🚨")
    else:
        st.success("No warnings: the payment plan totals 100% and all quotes were found in the PDF.")

    rows = []
    for name, lbl in FIELD_LABELS.items():
        item = getattr(contract, name)
        shown = ("Present (see quote)" if name == "cancellation_clause" and item.value is not None
                 else "Not found in contract" if name == "cancellation_clause" else fmt_value(name, contract))
        rows.append({"Field": lbl, "Value": shown, "Page": item.source_page, "Source quote": item.source_quote})
    df = pd.DataFrame(rows)
    df["Page"] = df["Page"].astype("Int64")

    def hl(row):
        missing = row["Value"] in ("Not stated", "Not found in contract")
        return ["background-color: #fde68a; color: #111" if missing else ""] * len(row)

    st.dataframe(df.style.apply(hl, axis=1), hide_index=True, use_container_width=True,
                 column_config={"Page": st.column_config.NumberColumn(width="small"),
                                "Source quote": st.column_config.TextColumn(width="large")})

    st.markdown("#### Payment plan")
    if contract.payment_plan:
        total = contract.payment_plan_percent_sum
        c1, c2 = st.columns(2)
        c1.metric("Plan total (computed)", f"{total:g}%", delta=None if abs(total - 100) < 0.01 else f"{total - 100:+g}% vs 100%",
                  delta_color="inverse")
        c2.metric("Milestones", len(contract.payment_plan))
        try:
            amounts = {r["milestone"]: r["amount"] for r in milestone_rows(contract)}
        except CashflowUnavailable:
            amounts = {}
        pp = pd.DataFrame([{
            "Milestone": m.name, "%": m.percent, "Amount (AED)": amounts.get(m.name),
            "Due date": m.due_date, "Trigger": m.trigger, "Page": m.source_page, "Source quote": m.source_quote,
        } for m in contract.payment_plan])
        pp["Page"] = pp["Page"].astype("Int64")
        bad = abs(total - 100) > 0.01
        st.dataframe(pp.style.apply(lambda r: ["background-color: #fde68a; color: #111" if bad else ""] * len(r), axis=1)
                     .format({"Amount (AED)": "{:,.2f}"}, na_rep="n/a"),
                     hide_index=True, use_container_width=True)
    else:
        st.info("No payment plan extracted.")

# ------------------------------------------------------------------ Penalty simulator
with tab_pen:
    st.subheader("Delay penalty simulator")
    st.caption("Deterministic calculation from the extracted terms. Compensation accrues only on days "
               "after the grace period; day-count and scenarios come from `rules/uae.yaml`.")
    try:
        grace = contract.grace_period_days.value or 0
        st.markdown(
            f"**Terms used:** rate {fmt_value('delay_rate', contract)} · grace {grace} days · "
            f"cap {fmt_value('delay_cap', contract)}")
        days = st.slider("Delay beyond the handover date (days)", 0, 730, RULES["cashflow"]["default_delay_scenario_days"],
                         step=5, key="pen_days")
        one = penalty_for_contract(contract, days, RULES)
        m1, m2, m3, m4 = st.columns([1.5, 1, 1, 1.2])
        m1.metric("Compensation owed by developer", aed0(one["penalty"]))
        m2.metric("Chargeable days", one["chargeable_days"])
        m3.metric("% of purchase price", f"{one['pct_of_price']}%" if one["pct_of_price"] is not None else "n/a")
        m4.metric("Cap", aed0(one["cap_amount"]) if one["cap_amount"] is not None else "No cap")
        if one["cap_reached"]:
            st.info("The cap is reached at this delay: compensation stops growing.")
        table = pd.DataFrame(simulate(contract, rules=RULES)).rename(columns={
            "delay_days": "Delay (days)", "grace_days": "Grace (days)", "chargeable_days": "Chargeable days",
            "penalty": "Compensation (AED)", "cap_amount": "Cap (AED)", "cap_reached": "Cap reached",
            "pct_of_price": "% of price"})
        st.dataframe(table.style.format({"Compensation (AED)": "{:,.2f}", "Cap (AED)": "{:,.2f}", "% of price": "{:.3f}"}, na_rep="no cap"),
                     hide_index=True, use_container_width=True)
    except SimulationUnavailable as e:
        st.warning(f"Cannot simulate this contract: {e}")

# ------------------------------------------------------------------ Cash-flow
with tab_cash:
    st.subheader("Cash-flow")
    try:
        c1, c2 = st.columns([1, 2])
        period = c1.radio("Group by", ["quarter", "month"], horizontal=True,
                          index=["quarter", "month"].index(RULES["cashflow"]["default_period"]))
        delay = c2.slider("Delay scenario for penalty exposure (days)", 0, 730,
                          RULES["cashflow"]["default_delay_scenario_days"], step=5, key="cf_days")
        sched, unscheduled = build_schedule(contract, period, as_of=date.today(), rules=RULES)
        risk = at_risk_summary(contract, delay, RULES)

        k1, k2, k3, k4 = st.columns([1.3, 1.2, 1.3, 1])
        k1.metric("Construction/handover-linked", aed0(risk["linked_amount"]),
                  help="Payments tied to construction or handover milestones (keywords in rules/uae.yaml).")
        k2.metric("Penalty exposure", aed0(risk["penalty_exposure"]),
                  help=risk["penalty_note"] or "Compensation owed to the buyer in this delay scenario.")
        k3.metric("At risk (sum)", aed0(risk["at_risk_total"]))
        k4.metric("Linked share of plan", f"{risk['linked_pct_of_plan']}%" if risk["linked_pct_of_plan"] is not None else "n/a")

        if not sched.empty:
            fig = go.Figure()
            fig.add_bar(x=sched["period"], y=sched["safe_amount"], name="Time-based", marker_color=BLUE,
                        hovertemplate="%{x}<br>Time-based: AED %{y:,.0f}<extra></extra>")
            fig.add_bar(x=sched["period"], y=sched["at_risk_amount"], name="Construction/handover-linked",
                        marker_color=AMBER, hovertemplate="%{x}<br>Linked: AED %{y:,.0f}<extra></extra>")
            fig.add_scatter(x=sched["period"], y=sched["cumulative"], name="Cumulative", yaxis="y2",
                            mode="lines+markers", line=dict(color="#6b7280", width=2),
                            hovertemplate="%{x}<br>Cumulative: AED %{y:,.0f}<extra></extra>")
            fig.update_layout(barmode="stack", height=420, margin=dict(l=10, r=10, t=30, b=10),
                              yaxis=dict(title="Amount due (AED)", tickformat=",.0f", rangemode="tozero"),
                              yaxis2=dict(title="Cumulative (AED)", overlaying="y", side="right", tickformat=",.0f", showgrid=False, rangemode="tozero"),
                              legend=dict(orientation="h", y=1.12), template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(sched.rename(columns={
                "period": "Period", "amount_due": "Amount due", "at_risk_amount": "Linked (at risk)",
                "safe_amount": "Time-based", "cumulative": "Cumulative", "cumulative_pct": "Cumulative %",
                "is_past": f"Ended before {date.today().isoformat()}"}).style.format(
                {"Amount due": "{:,.2f}", "Linked (at risk)": "{:,.2f}", "Time-based": "{:,.2f}",
                 "Cumulative": "{:,.2f}", "Cumulative %": "{:.2f}"}), hide_index=True, use_container_width=True)
        if unscheduled:
            st.warning("Milestones with no stated due date are not placed on the timeline: "
                       + ", ".join(f"{u['milestone']} ({aed(u['amount'])})" for u in unscheduled))
        pt = risk["plan_total"]
        if contract.price.value and abs(pt - contract.price.value) > 0.01:
            st.error(f"The payment plan totals {aed(pt)} but the purchase price is {aed(contract.price.value)}: "
                     f"the plan does not add up to 100%.")
        st.caption("At risk = construction/handover-linked payments + penalty exposure for the chosen scenario "
                   "(definition in `app/cashflow.py` and `rules/uae.yaml`).")
    except CashflowUnavailable as e:
        st.warning(f"Cannot build the cash-flow: {e}")

# ------------------------------------------------------------------ Buyer assistant
with tab_chat:
    st.subheader("Buyer assistant")
    st.caption("Answers only from this contract's extracted terms and cites the clause. "
               "Legal questions are referred to the legal team.")
    key = f"chat_{contract.file_hash}"
    hist = st.session_state.setdefault(key, [])
    for m in hist:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            for cit in m.get("citations", []):
                st.caption(f"📎 page {cit['page']}: “{cit['quote']}”")
    q = st.chat_input("Ask about your payments, handover date, or late-fee rule…")
    if q:
        with st.chat_message("user"):
            st.markdown(q)
        # Only prior plain-text turns are sent as history.
        past = [{"role": m["role"], "content": m["content"]} for m in hist]
        try:
            with st.spinner("Checking the contract…"):
                reply = BuyerAgent(contract).ask(q, history=past)
            ans, cits = reply.answer, reply.citations
        except Exception as e:
            ans, cits = f"Sorry, the assistant could not answer: {e}", []
        with st.chat_message("assistant"):
            st.markdown(ans)
            for cit in cits:
                st.caption(f"📎 page {cit['page']}: “{cit['quote']}”")
        hist.append({"role": "user", "content": q})
        hist.append({"role": "assistant", "content": ans, "citations": cits})

# ------------------------------------------------------------------ Accuracy
with tab_acc:
    st.subheader("Extraction accuracy")
    p = config.EVAL_RESULTS_PATH
    if not p.exists():
        st.info("No evaluation results yet. Run `python eval/run_eval.py` (needs LLM settings in `.env`) to generate them.")
    else:
        res = json.loads(p.read_text())
        st.caption(f"Model `{res.get('model')}` · {res.get('generated_at')} · files: {', '.join(res.get('files', []))}")
        if res.get("model") != config.model_tag():
            st.warning(f"These results were produced with `{res.get('model')}`, not the current `{config.model_tag()}`.")
        o = res["overall"]
        a1, a2, a3 = st.columns(3)
        a1.metric("Value accuracy", f"{o['value_accuracy']:.1%}", help=f"{o['checks']} checks")
        a2.metric("Quotes found in PDF", f"{o['quote_accuracy']:.1%}" if o["quote_accuracy"] is not None else "n/a",
                  help=f"{o['quotes_checked']} quotes checked")
        pt = res.get("penalty_tests", {})
        a3.metric("Penalty tests passing", f"{pt.get('passed')}/{pt.get('total')}")
        tbl = pd.DataFrame([{
            "Field": k, "Correct": f"{v['correct']}/{v['total']}", "Accuracy": v["accuracy"],
            "Quote in PDF": f"{v['quote_valid']}/{v['quote_total']}" if v["quote_total"] else "-",
        } for k, v in res["fields"].items()])
        st.dataframe(tbl.style.format({"Accuracy": "{:.0%}"}), hide_index=True, use_container_width=True)
