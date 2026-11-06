import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import "../i18n";
import { PrefsProvider, usePrefs } from "./prefs";

function Probe() {
  const p = usePrefs();
  return (
    <div>
      <button onClick={() => p.setLang(p.lang === "en" ? "ar" : "en")}>lang</button>
      <button onClick={() => p.setReduce(true)}>reduce</button>
      <span data-testid="tier">{p.tier}</span>
    </div>
  );
}

describe("preferences", () => {
  it("switching to Arabic sets <html lang='ar' dir='rtl'> and back", () => {
    render(
      <PrefsProvider>
        <Probe />
      </PrefsProvider>,
    );
    expect(document.documentElement.dir).toBe("ltr");
    act(() => screen.getByText("lang").click());
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    act(() => screen.getByText("lang").click());
    expect(document.documentElement.dir).toBe("ltr");
  });

  it("'Reduce effects' switches the effects tier and the data attribute", () => {
    render(
      <PrefsProvider>
        <Probe />
      </PrefsProvider>,
    );
    act(() => screen.getByText("reduce").click());
    expect(screen.getByTestId("tier")).toHaveTextContent("reduced");
    expect(document.documentElement.dataset.effects).toBe("reduced");
    expect(localStorage.getItem("spa.reduce")).toBe("1");
  });
});
