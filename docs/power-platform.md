# Power Platform integration (Power Automate, Copilot Studio)

Power BI is intentionally **not** part of this application.

| Piece | Where | Status |
|---|---|---|
| Entra sign-in for the API | `docs/entra-setup.md`, `backend/api/auth.py` | token validation tested with locally signed tokens; browser sign-in not tried on a real tenant |
| Outbound webhook (alerts and review items) | `app/notifiers.py`, env `ALERT_WEBHOOK_URL` | tested with a mock transport |
| Custom connector (staff operations) | `integrations/power-platform/spa-intelligence.swagger.json`, regenerate with `python scripts/make_connector.py --host <your host>` | checked against the live API routes; not imported into a real tenant |
| Flow recipes and Teams cards | `integrations/power-automate/` | written, not run in a tenant |
| Copilot Studio buyer agent | `integrations/copilot-studio/` | definitions and acceptance script; not created in a tenant |
| D365 mapping check | `python -m app.erp.check metadata.xml` | tested on a sample metadata file; not run against your environment |

## Importing the connector

Power Automate > Data > Custom connectors > New > Import an OpenAPI file > `spa-intelligence.swagger.json`. Set the host to your deployed API,
Security: OAuth 2.0, identity provider Azure Active Directory, Client ID = the **Web/SPA registration you create for the connector**
(or a dedicated one), tenant, Resource URL `api://<API client id>`, scope `api://<API client id>/access_as_user`. Copy the redirect URL the
connector shows into that registration's redirect URIs. Test each operation in the connector's Test tab.

## Making the D365 push real

1. Open `https://<env>.operations.dynamics.com/data/$metadata` while signed in and save it as `metadata.xml`.
2. Pick the entity (OData entity set) that should receive schedule lines and its field names, then put them in `erp/d365_mapping.yaml` (replace every `TODO_`, set `placeholder: false`).
3. `python -m app.erp.check metadata.xml` until it prints "mapping OK".
4. Register an app in Entra for the push (client credentials), give it access in D365 (System administration > Microsoft Entra ID applications), then set `ERP_PUSH_ENABLED=1`, `D365_TENANT_ID`, `D365_CLIENT_ID`, `D365_CLIENT_SECRET`, `D365_RESOURCE`.
5. Push one test contract to a non-production environment first; every push is audit-logged (`data/audit/erp_push.jsonl`).
