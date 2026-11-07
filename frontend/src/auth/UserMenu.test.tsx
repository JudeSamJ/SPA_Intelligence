import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../i18n";
import { PrefsProvider } from "../state/prefs";
import { jsonResponse } from "../test/helpers";
import { UserMenu } from "./UserMenu";

afterEach(() => vi.unstubAllGlobals());
const me = (over: object) => vi.fn(async () => jsonResponse({ authenticated: true, mode: "apikey", name: "Alice A", login: "alice", avatar_url: "https://avatars.githubusercontent.com/u/11?v=4", roles: ["Spa.Reviewer"], ...over }));
const mount = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PrefsProvider>
        <UserMenu />
      </PrefsProvider>
    </QueryClientProvider>,
  );

describe("UserMenu (profile picture in the navigation bar)", () => {
  it("shows the GitHub picture, and name, username and role in a menu", async () => {
    vi.stubGlobal("fetch", me({}));
    mount();
    const btn = await screen.findByTestId("user-menu-button");
    const img = btn.querySelector("img")!;
    expect(img).toHaveAttribute("src", "https://avatars.githubusercontent.com/u/11?v=4");
    expect(img).toHaveAttribute("referrerpolicy", "no-referrer");
    fireEvent.click(btn);
    const menu = screen.getByTestId("user-menu");
    expect(menu).toHaveTextContent("Alice A");
    expect(menu).toHaveTextContent("@alice");
    expect(menu).toHaveTextContent("Reviewer");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("user-menu")).toBeNull();
  });

  it("falls back to initials when the picture cannot load or there is none", async () => {
    vi.stubGlobal("fetch", me({}));
    mount();
    const btn = await screen.findByTestId("user-menu-button");
    fireEvent.error(btn.querySelector("img")!);
    await waitFor(() => expect(btn).toHaveTextContent("AA"));
    expect(btn.querySelector("img")).toBeNull();
  });

  it("renders nothing when nobody is signed in or server auth is off", async () => {
    const f = me({ authenticated: false, name: null, login: null, avatar_url: null, roles: [] });
    vi.stubGlobal("fetch", f);
    mount();
    await waitFor(() => expect(f).toHaveBeenCalled());
    expect(screen.queryByTestId("user-menu-button")).toBeNull();
  });
});
