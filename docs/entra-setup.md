# Microsoft Entra sign-in: setup

The API validates Entra access tokens itself (signature against the tenant's public keys, audience, issuer, tenant, expiry).
It needs **no secret**. The browser uses the authorization-code flow with PKCE (a SPA registration has no client secret).
**Status: the token validation is covered by automated tests with locally signed tokens. The browser sign-in (MSAL) has not been
tried against a real tenant** because none was available when it was written; expect to adjust redirect URIs or consent on first run.

## 1. Register the API (Entra admin centre > App registrations > New)

1. Name `SPA Intelligence API`, single tenant. Copy the **Application (client) ID** (= `ENTRA_CLIENT_ID`) and **Directory (tenant) ID** (= `ENTRA_TENANT_ID`).
2. *Expose an API*: set the Application ID URI to `api://<client id>`; add a scope `access_as_user` (admins and users can consent).
3. *App roles* (allowed member types: Users/Groups). Create three, with these exact values:

| Display name | Value | Meaning |
|---|---|---|
| SPA Staff | `Spa.Staff` | read everything on the staff side |
| SPA Reviewer | `Spa.Reviewer` | Staff + review decisions, upload/extract, golden export, jurisdiction, eval runs, ERP push |
| SPA Buyer | `Spa.Buyer` | only `POST /buyer/chat`, for the contract linked to that person |

4. In *Manifest* set `"requestedAccessTokenVersion": 2` so tokens carry the v2 issuer.
5. *Enterprise applications > SPA Intelligence API > Users and groups*: assign people (or groups) to roles. Turn on
   *Assignment required* so unassigned users cannot get a token.

## 2. Register the SPA (the browser app)

1. New registration `SPA Intelligence Web`, platform **Single-page application**, redirect URI = where the app is served
   (for local use `http://localhost:8000` or `http://localhost:5173`). Copy its client ID.
2. *API permissions > Add > My APIs > SPA Intelligence API > `access_as_user`*; grant admin consent.

## 3. Configure

Server (`.env`):

```
AUTH_MODE=entra
ENTRA_TENANT_ID=<tenant id>
ENTRA_CLIENT_ID=<API client id>
CORS_ORIGINS=https://your-app-origin
# buyers: Entra object id (Users > the user > Object ID) -> contract id (GET /api/contracts)
BUYER_ACCOUNTS={"<buyer object id>":"<64-hex contract id>"}
```

With `AUTH_MODE=entra` and a missing tenant or client id the server **refuses to start**; an unknown `AUTH_MODE` value also refuses
(a typo never means "open"). `BUYER_TOKENS` is ignored in this mode.

Frontend (build-time, `frontend/.env.production`):

```
VITE_ENTRA_TENANT_ID=<tenant id>
VITE_ENTRA_SPA_CLIENT_ID=<SPA client id>
VITE_ENTRA_API_CLIENT_ID=<API client id>
```

These are identifiers, not secrets. Without them the build contains no sign-in code at all.

## What changes for users and for other tools

- Every `/api` route except `GET /api/health` returns 401 without a valid token and 403 without a suitable role.
- The reviewer name in the review log and the ERP-push audit entry is the **verified** identity from the token, not text typed into a request.
- Buyer chat is bound to the signed-in buyer's linked contract; the request cannot name a contract.
- **Power Automate / Copilot Studio / Power BI** call the API as an app or as a user: for a custom connector choose OAuth 2.0 with Azure AD,
  scope `api://<API client id>/.default` (app permissions need the roles assigned to the calling app registration).
- Page images, the PDF and CSV downloads are fetched with the token (they cannot carry a header from a plain `<img>`/`<a>`).

## Not done here

Sign-out button and displaying the signed-in user in the header; group-based roles; per-project (row-level) permissions;
refresh of role changes without a new token; rate limits keyed by user. Roles are read from the token, so a role change takes effect
on the next token.
