"""Cross-document graph: planted-error precision/recall over 3 synthetic sets, normalisation, uncertain matching."""
import json
from datetime import date
from pathlib import Path

import pytest

from app import config
from app import crossdoc as cd
from app.crossdoc import FactsOutput, analyze, load_set, normalize, score_planted, unit_key
from app.extract import extract_from_llm, pdf_pages, postprocess
from app.schema import ContractData
from tests.fakes import FakeClient, oracle_input

ROOT = Path(__file__).resolve().parent.parent
SETS = ROOT / "samples" / "crossdoc"


def spa_contract(d: Path) -> ContractData:
    pdf = d / "spa.pdf"
    ref = next(p for p in (ROOT / "samples").glob("sample_*.pdf") if p.read_bytes() == pdf.read_bytes())
    b = pdf.read_bytes()
    out = extract_from_llm(b, FakeClient(oracle_input(ref)))
    return postprocess(ContractData(**out.model_dump()), pdf_pages(b), b)


def facts_oracle(d: Path):
    """Test stand-in for the LLM: facts.json holds what each generated PDF states (with verbatim quotes)."""
    facts = json.loads((d / "facts.json").read_text())

    def tool_input(entry):
        pages = pdf_pages((d / entry["doc"]).read_bytes())
        from app.extract import locate_quote

        def S(attr, val):
            q = entry["quotes"].get(attr)
            if val is None or q is None:
                return {"value": None, "source_page": None, "source_quote": None}
            return {"value": val, "source_page": locate_quote(pages, q), "source_quote": q}
        v = entry["values"]
        return {"unit_id": S("unit_id", v.get("unit_id")), "price": S("price", v.get("price")),
                "area_sqft": S("area_sqft", v.get("area_sqft")), "handover_date": S("handover_date", v.get("handover_date")),
                "payment_plan": S("payment_plan", v.get("payment_plan")), "delay_rate": S("delay_rate", v.get("delay_rate")),
                "registration_number": S("registration_number", v.get("registration_number"))}

    def provider(doc):
        key = "brochure" if doc.type == "brochure" else "filing"
        return cd.extract_facts((d / doc.name).read_bytes(), FakeClient(tool_input(facts[key])))
    return provider


@pytest.mark.parametrize("set_id", ["set_1", "set_2", "set_3"])
def test_each_set_finds_exactly_the_planted_conflicts(set_id):
    d = SETS / set_id
    ds = load_set(d)
    res = analyze(ds, spa_contract(d), facts_oracle(d))
    planted = json.loads((d / "manifest.json").read_text())["planted"]
    sc = score_planted(res["conflicts"], planted)
    assert sc["precision"] == 1.0 and sc["recall"] == 1.0, (res["conflicts"], planted)
    assert not res["pending"] and all(x["match"] != "unmatched" for x in res["documents"])


def test_overall_precision_recall_reported():
    tp = fp = fn = 0
    for set_id in ("set_1", "set_2", "set_3"):
        d = SETS / set_id
        res = analyze(load_set(d), spa_contract(d), facts_oracle(d))
        s = score_planted(res["conflicts"], json.loads((d / "manifest.json").read_text())["planted"])
        tp, fp, fn = tp + s["tp"], fp + s["fp"], fn + s["fn"]
    assert (tp, fp, fn) == (6, 0, 0)       # 6 planted across 3 sets: precision 6/6, recall 6/6


def test_conflict_carries_evidence_from_both_documents():
    d = SETS / "set_1"
    res = analyze(load_set(d), spa_contract(d), facts_oracle(d))
    price = next(c for c in res["conflicts"] if c["attribute"] == "price")
    by = {v["doc_type"]: v for v in price["values"]}
    assert by["brochure"]["quote"] == "Price: INR 8,250,000" and by["brochure"]["page"] == 1
    assert by["spa"]["field"] == "price" and by["spa"]["page"] and by["crm_export"]["locator"]["column"] == "Agreed Price"
    assert price["severity"] == "high"


def test_graph_json_has_conflict_edges_and_nodes():
    d = SETS / "set_2"
    g = analyze(load_set(d), spa_contract(d), facts_oracle(d))["graph"]
    kinds = {e["kind"] for e in g["edges"]}
    assert {"has_document", "states", "instance_of", "conflict"} <= kinds
    assert any(n["type"] == "fact" and n["conflict"] for n in g["nodes"])
    assert sum(1 for n in g["nodes"] if n["type"] == "document") == 4


def test_normalisation_units_dates_formats():
    assert normalize("area_sqft", 95.27, "sqm") == pytest.approx(1025.48, abs=0.01)  # 95.27 x 10.7639 = 1025.4768
    assert cd.equal("area_sqft", normalize("area_sqft", 95.27, "sqm"), 1025.5)          # within 0.5%
    assert not cd.equal("area_sqft", 1150.0, 1180.0)
    assert normalize("registration_number", "dld - 8841") == "DLD8841"
    assert normalize("payment_plan", [20, 20.0]) == (20.0, 20.0)
    assert normalize("handover_date", date(2027, 6, 30)) == "2027-06-30"


def test_unit_key_normalisation_and_uncertain_matching():
    assert unit_key("Unit KH-T2-1503") == unit_key("kh t2 1503") == unit_key("KH-T2-1503")
    assert cd.match_unit(unit_key("KH T2 1503"), unit_key("KH-T2-1503"))[0] == "normalized"
    assert cd.match_unit(unit_key("KH-T2-1508"), unit_key("KH-T2-1503"))[0] == "uncertain"       # one digit off
    assert cd.match_unit(unit_key("ZZ-9-9999"), unit_key("KH-T2-1503"))[0] == "unmatched"


def test_uncertain_unit_is_flagged_and_unmatched_is_excluded(tmp_path):
    d = SETS / "set_1"
    ds = load_set(d)
    # CRM with a one-digit-off unit: matched as uncertain, conflicts flagged uncertain
    crm = tmp_path / "crm.csv"
    crm.write_text("Unit No,Customer,Agreed Price,Area,Possession Date,Plan %,Delay Rate,RERA No\n"
                   "KH-T2-1508,X,9999999,865,31-12-2026,10/20/20/20/20/10,60,P99999000001\n")
    ds.documents = [x for x in ds.documents if x.type in ("spa", "crm_export")]
    ds.documents[1].path = str(crm)
    res = analyze(ds, spa_contract(d), lambda doc: None)
    crm_doc = next(x for x in res["documents"] if x["type"] == "crm_export")
    assert crm_doc["match"] == "uncertain"
    assert next(c for c in res["conflicts"] if c["attribute"] == "price")["uncertain_match"] is True
    crm.write_text("Unit No,Customer,Agreed Price,Area,Possession Date,Plan %,Delay Rate,RERA No\nZZ-1,X,1,1,01-01-2020,1,1,1\n")
    res2 = analyze(ds, spa_contract(d), lambda doc: None)
    assert next(x for x in res2["documents"] if x["type"] == "crm_export")["match"] == "unmatched"
    assert res2["conflicts"] == []


def test_missing_pdf_facts_are_pending_not_invented():
    d = SETS / "set_1"
    res = analyze(load_set(d), spa_contract(d), lambda doc: None)
    assert set(res["pending"]) == {"brochure", "regulator_filing"}
    assert all(c["attribute"] != "registration_number" for c in res["conflicts"])


def test_grounding_applies_to_brochure_facts():
    d = SETS / "set_1"
    facts = json.loads((d / "facts.json").read_text())["brochure"]
    pages = pdf_pages((d / "brochure.pdf").read_bytes())
    from app.extract import locate_quote
    inp = {k: {"value": None, "source_page": None, "source_quote": None} for k in
           ("unit_id", "area_sqft", "handover_date", "payment_plan", "delay_rate", "registration_number")}
    inp["price"] = {"value": 9_999_999.0, "source_page": 1, "source_quote": facts["quotes"]["price"]}   # real quote, wrong number
    o = cd.extract_facts((d / "brochure.pdf").read_bytes(), FakeClient(inp))
    assert o.price.value is None and o.price.grounding.status == "ungrounded"


def test_xlsx_crm_via_mapping(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Unit No", "Customer", "Agreed Price", "Area", "Possession Date", "Plan %", "Delay Rate", "RERA No"])
    ws.append(["KH T2 1503", "X", 8450000, 865, "31-12-2026", "10/20/20/20/20/10", 60, "P99999000001"])
    p = tmp_path / "crm.xlsx"; wb.save(p)
    facts, unit = cd.facts_from_crm(p, "crm", unit_key("KH-T2-1503"))
    assert unit == "KH T2 1503" and {f.attribute for f in facts} == set(cd.ATTRS)
