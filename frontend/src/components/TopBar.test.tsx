import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import "../i18n";
import { PrefsProvider } from "../state/prefs";
import { TopBar } from "./TopBar";

const setViewport = (narrow: boolean) => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (q: string) => ({
      matches: /max-width: 860px/.test(q) ? narrow : false,
      media: q,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      onchange: null,
      dispatchEvent: () => false,
    }),
  });
};
const mount = () =>
  render(
    <PrefsProvider>
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    </PrefsProvider>,
  );
beforeEach(() => localStorage.clear());

describe("TopBar responsiveness", () => {
  it("wide screens: one row with navigation and controls, no menu button", () => {
    setViewport(false);
    mount();
    expect(screen.queryByTestId("menu-button")).toBeNull();
    expect(screen.getByRole("link", { name: "Accuracy" })).toBeInTheDocument();
    expect(screen.getByText("Reduce effects")).toBeInTheDocument();
  });

  it("narrow screens: nav and secondary controls live in a menu that opens, switches language and closes on Escape", () => {
    setViewport(true);
    mount();
    expect(screen.queryByRole("link", { name: "Accuracy" })).toBeNull(); // not in the bar
    const btn = screen.getByTestId("menu-button");
    expect(btn).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("menu-panel")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Accuracy" })).toBeInTheDocument();
    expect(screen.getByText("Reduce effects")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Language" }));
    expect(document.documentElement.dir).toBe("rtl");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("menu-panel")).toBeNull();
  });
});
