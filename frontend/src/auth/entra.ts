/**
 * Microsoft Entra sign-in (MSAL, authorization-code flow with PKCE). Loaded only when VITE_ENTRA_TENANT_ID is set,
 * so the default bundle does not contain it. Nothing secret lives in the browser: a SPA registration has no client secret.
 *
 * VITE_ENTRA_TENANT_ID   directory (tenant) id
 * VITE_ENTRA_SPA_CLIENT_ID  the SPA app registration's client id
 * VITE_ENTRA_API_CLIENT_ID  the API app registration's client id (scope api://<id>/access_as_user)
 */
import { PublicClientApplication, InteractionRequiredAuthError } from "@azure/msal-browser";
import { setTokenProvider } from "./token";

export async function initEntra(): Promise<void> {
  const tenant = import.meta.env.VITE_ENTRA_TENANT_ID as string;
  const spa = import.meta.env.VITE_ENTRA_SPA_CLIENT_ID as string;
  const api = import.meta.env.VITE_ENTRA_API_CLIENT_ID as string;
  if (!tenant || !spa || !api) throw new Error("Set VITE_ENTRA_TENANT_ID, VITE_ENTRA_SPA_CLIENT_ID and VITE_ENTRA_API_CLIENT_ID.");
  const app = new PublicClientApplication({
    auth: { clientId: spa, authority: `https://login.microsoftonline.com/${tenant}`, redirectUri: window.location.origin },
    cache: { cacheLocation: "sessionStorage" },
  });
  await app.initialize();
  const redirect = await app.handleRedirectPromise();
  const scopes = [`api://${api}/access_as_user`];
  let account = redirect?.account ?? app.getAllAccounts()[0];
  if (!account) {
    await app.loginRedirect({ scopes });
    return new Promise<void>(() => {}); // the page navigates away
  }
  app.setActiveAccount(account);
  setTokenProvider(async () => {
    try {
      return (await app.acquireTokenSilent({ scopes, account })).accessToken;
    } catch (e) {
      if (e instanceof InteractionRequiredAuthError) {
        await app.acquireTokenRedirect({ scopes });
        return new Promise<string | null>(() => {});
      }
      throw e;
    }
  });
  account = app.getActiveAccount() ?? account;
}
