import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import "../i18n";
import { DisclaimerBar } from "./Disclaimer";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-banner");
});

describe("disclaimer banner", () => {
  it("is shown by default with the required wording", () => {
    render(<DisclaimerBar />);
    expect(screen.getByTestId("disclaimer")).toHaveTextContent("Decision support, not legal advice.");
    expect(document.documentElement.dataset.banner).toBe("shown");
  });

  it("can be dismissed, leaves a restore tab, and the choice is remembered", () => {
    const { unmount } = render(<DisclaimerBar />);
    fireEvent.click(screen.getByTestId("disclaimer-dismiss"));
    expect(screen.queryByTestId("disclaimer")).toBeNull();
    expect(screen.getByTestId("disclaimer-show")).toBeInTheDocument(); // never fully gone
    expect(document.documentElement.dataset.banner).toBe("hidden");
    expect(localStorage.getItem("spa.banner")).toBe("hidden");
    unmount();
    render(<DisclaimerBar />); // remembered after a reload
    expect(screen.queryByTestId("disclaimer")).toBeNull();
    fireEvent.click(screen.getByTestId("disclaimer-show"));
    expect(screen.getByTestId("disclaimer")).toBeInTheDocument();
    expect(localStorage.getItem("spa.banner")).toBe("shown");
  });
});
