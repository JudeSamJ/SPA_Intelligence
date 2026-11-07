# GitHub sign-in for the web UI (no IT help needed)

People open the UI on your Render URL, click **Sign in with GitHub**, and get in only if their GitHub username is on **your list**.
Each listed user has a role: `Spa.Reviewer` (can extract, review, upload) or `Spa.Staff` (read and compute only).
The connector and the Copilot agents keep using API keys (`X-API-Key`); the two can run side by side.

**Status: the server side (OAuth state, allow-list, signed cookie, CSRF header, roles, tamper/expiry/alg-none rejection) is covered by 10
automated tests against a mocked GitHub, and the sign-in gate by 5 UI tests. It has not been run against the real github.com**, because
that needs your OAuth App. Expect to fix at most a callback-URL typo.

## 1. Create the GitHub OAuth App (2 minutes, your own GitHub account)

GitHub → your avatar → **Settings** → **Developer settings** → **OAuth Apps** → **New OAuth App**:

| Field | Value |
|---|---|
| Application name | SPA Intelligence |
| Homepage URL | `https://spa-intelligence-bkf2.onrender.com` |
| Authorization callback URL | `https://spa-intelligence-bkf2.onrender.com/api/auth/github/callback` |

Click **Register application**, then **Generate a new client secret**. Copy the **Client ID** and the **Client secret** (the secret is shown once).
The callback URL must match **exactly**, including `https` and no trailing slash.

## 2. Set these in Render → Environment

| Variable | Value |
|---|---|
| `AUTH_MODE` | `apikey` (keep) |
| `API_KEYS` | keep (the connector keys) |
| `SERVE_FRONTEND` | `1` (so the UI is served again) |
| `GITHUB_CLIENT_ID` | from step 1 |
| `GITHUB_CLIENT_SECRET` | from step 1 |
| `PUBLIC_BASE_URL` | `https://spa-intelligence-bkf2.onrender.com` |
| `SESSION_SECRET` | 40+ random characters: `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `GITHUB_USERS` | `YourGitHubLogin:Spa.Reviewer,colleague:Spa.Staff` |

Save and redeploy. If a variable is missing or too weak the server **refuses to start** and says which one (check the Render logs).

## What people see

- **Login page (`/login`):** a dedicated page in the site's UAE look (dusk sky, skyline, dunes, mashrabiya band) with one button, **Continue with GitHub**.
  Opening anything under `/app` while signed out sends you there and, after sign-in, brings you back to where you were going (only paths inside `/app` are accepted).
- **Friendly failures:** Cancel at GitHub, a failed or unverifiable sign-in, or a GitHub account that is not on `GITHUB_USERS` each return to the login page with a short explanation (the refused username is shown).
- **Profile picture:** once signed in, your GitHub picture appears at the right end of the navigation bar (initials if it cannot load). Click it for your name, `@username`, role and **Sign out**.
  The picture URL is accepted only from GitHub's own image host (`avatars.githubusercontent.com`), so a profile cannot point the app at another site.
- Signed-in visitors who open `/login` go straight to the app. The landing page stays public.

## 3. Try it

1. Open the Render URL in a private window, go to `/app`. You should see **Sign in to continue**.
2. Click **Sign in with GitHub**, approve, and you land in the app with "Signed in as <your name>" at the top right.
3. A GitHub account that is **not** in `GITHUB_USERS` sees "Access not granted" (403) even after signing in at GitHub.
4. `curl https://spa-intelligence-bkf2.onrender.com/api/contracts` without a key still returns 401, and with your staff key still works.

## How it stays safe

- Only usernames in `GITHUB_USERS` get a session; removing one locks them out on their next request.
- The session is a signed, HttpOnly, SameSite=Lax, Secure cookie (default 8 hours, `SESSION_HOURS`). Tampered, expired or `alg:none` cookies are refused.
- Changes made with the cookie must carry `X-Requested-With: spa` (the UI does this), so another website cannot make your browser change data.
- The GitHub access token is used once to read your id and username and is then discarded (never stored or logged).
- The review log and ERP audit use your **verified GitHub name**, not text typed into a request.
- The OAuth callback address comes from `PUBLIC_BASE_URL`, never from request headers.

## Limits

- Roles are per GitHub username, not per project or contract; every signed-in user sees all contracts on the server.
- Buyers are not handled by this sign-in; the buyer agent still uses a buyer API key bound to one contract.
- A shared session secret signs all sessions: rotating `SESSION_SECRET` signs everyone out.
- Render's free tier wipes data on restart (extracted contracts must be extracted again).
- Microsoft sign-in is not included here: it needs an Entra app registration (see `docs/entra-setup.md`), which an admin may have to approve in your tenant.
