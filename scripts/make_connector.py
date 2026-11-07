"""Generate the Power Platform custom-connector definitions (Swagger 2.0, the format custom connectors import most reliably).

    python scripts/make_connector.py [--host api.example.com]

Writes integrations/power-platform/spa-intelligence.swagger.json (staff/automation operations) and
integrations/copilot-studio/buyer-chat.swagger.json (the ONE operation a buyer-facing Copilot Studio agent may call).
Operations are curated here on purpose (stable operationIds, small schemas, no internal routes such as the playbook);
tests/test_connector.py fails if an operation here no longer exists in the FastAPI app.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OBJ = {"type": "object", "additionalProperties": True}
ID = {"name": "contract_id", "in": "path", "required": True, "type": "string", "x-ms-summary": "Contract id", "description": "64-character id from List contracts"}


def op(method, path, op_id, summary, desc, params=(), body=None, role="Spa.Staff", resp=OBJ):
    d = {"operationId": op_id, "summary": summary, "description": f"{desc} Requires app role {role}.", "parameters": list(params),
         "responses": {"200": {"description": "OK", "schema": resp}, "default": {"description": "Error: {error: {code, message}}", "schema": OBJ}}}
    if body is not None:
        d["parameters"].append({"name": "body", "in": "body", "required": True, "schema": body})
    return path, method, d


def q(name, typ="string", desc="", required=False):
    return {"name": name, "in": "query", "required": required, "type": typ, "description": desc}


def B(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


STAFF_OPS = [
    op("get", "/contracts", "ListContracts", "List contracts", "Samples and uploads with extraction status."),
    op("get", "/contracts/{contract_id}", "GetContract", "Get extracted terms", "Terms with page, quote, grounding and evidence.", [ID]),
    op("post", "/contracts/{contract_id}/extract", "ExtractContract", "Extract contract (uses 1 LLM call)", "Starts extraction; cached results are reused.", [ID, q("force", "boolean", "Re-run even if cached")], role="Spa.Reviewer"),
    op("get", "/contracts/{contract_id}/status", "GetExtractionStatus", "Get extraction status", "Poll an extraction job.", [ID]),
    op("get", "/review-queue", "ListReviewQueue", "List fields needing review", "Fields that are partial, ungrounded or low-confidence."),
    op("post", "/contracts/{contract_id}/fields/{field}/review", "ReviewField", "Record a review decision", "Accept, correct or reject a field. The reviewer name is taken from the signed-in user.",
       [ID, {"name": "field", "in": "path", "required": True, "type": "string", "description": "e.g. price, handover_date, payment_plan.2"}],
       B({"action": {"type": "string", "enum": ["accept", "correct", "reject"]}, "value": {}, "note": {"type": "string"}}, ["action"]), role="Spa.Reviewer"),
    op("post", "/contracts/{contract_id}/statute-gap", "GetStatuteGap", "Compare contract with statute", "Contractual vs statutory delay compensation for a delay scenario. Statutory logic is unreviewed by a lawyer.",
       [ID], B({"delay_days": {"type": "integer"}, "as_of_date": {"type": "string", "format": "date"}}, ["delay_days"])),
    op("get", "/obligations", "ListObligations", "List obligations", "Dated obligations with evidence.", [q("as_of", "string", "YYYY-MM-DD"), q("within_days", "integer"), q("status", "string"), q("contract_id", "string")]),
    op("get", "/alerts", "ListAlerts", "List open alerts", "In-app alert feed (unacknowledged by default)."),
    op("post", "/alerts/{alert_id}/ack", "AcknowledgeAlert", "Acknowledge an alert", "Marks the alert handled.", [{"name": "alert_id", "in": "path", "required": True, "type": "string"}]),
    op("post", "/contracts/{contract_id}/erp/export", "PreviewErpExport", "Preview D365 export (dry run)", "Validated rows and CSV; nothing is sent.", [ID],
       B({"delay_days": {"type": "integer"}, "as_of_date": {"type": "string", "format": "date"}})),
    op("post", "/contracts/{contract_id}/erp/push", "PushToErp", "Push to D365 (needs confirm)", "Refused unless the server enables it, the mapping has no placeholders and confirm is true.", [ID],
       B({"confirm": {"type": "boolean"}, "delay_days": {"type": "integer"}, "as_of_date": {"type": "string", "format": "date"}}, ["confirm"]), role="Spa.Reviewer"),
]
BUYER_OPS = [
    op("post", "/buyer/chat", "AskBuyerAssistant", "Ask the buyer assistant", "Answers only from the signed-in buyer's own contract, with page and quote citations. Legal-advice questions are refused with a pointer to the legal team.",
       body=B({"message": {"type": "string", "maxLength": 1000}, "history": {"type": "array", "items": B({"role": {"type": "string"}, "content": {"type": "string"}})}, "channel": {"type": "string"}}, ["message"]),
       role="Spa.Buyer", resp=B({"answer": {"type": "string"}, "refused": {"type": "boolean"}, "reason": {"type": "string"}, "tool_calls": {"type": "array", "items": {"type": "string"}},
                                "citations": {"type": "array", "items": B({"tool": {"type": "string"}, "page": {"type": "integer"}, "quote": {"type": "string"}})}, "disclaimer": {"type": "string"}})),
]


def build(ops, title, host, description):
    paths: dict = {}
    for path, method, d in ops:
        paths.setdefault(path, {})[method] = d
    return {"swagger": "2.0", "info": {"title": title, "version": "1.0", "description": description},
            "host": host, "basePath": "/api", "schemes": ["https"], "consumes": ["application/json"], "produces": ["application/json"],
            "paths": paths,
            "securityDefinitions": {"oauth2": {"type": "oauth2", "flow": "accessCode",
                                               "authorizationUrl": "https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/authorize",
                                               "tokenUrl": "https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token",
                                               "scopes": {"api://<API_CLIENT_ID>/access_as_user": "Access SPA Intelligence"}}},
            "security": [{"oauth2": ["api://<API_CLIENT_ID>/access_as_user"]}]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="<your-api-host>")
    a = ap.parse_args()
    (ROOT / "integrations/power-platform/spa-intelligence.swagger.json").write_text(json.dumps(
        build(STAFF_OPS, "SPA Intelligence", a.host, "Decision support, not legal advice. Contract intelligence for staff automation."), indent=2))
    (ROOT / "integrations/copilot-studio/buyer-chat.swagger.json").write_text(json.dumps(
        build(BUYER_OPS, "SPA Intelligence Buyer Assistant", a.host, "Decision support, not legal advice. One operation: ask about your own contract."), indent=2))
    print("wrote 2 connector definitions")


if __name__ == "__main__":
    main()
