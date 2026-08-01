import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { HomePage } from "../components/HomePage";
import App from "../App";

vi.mock("../components/PointCloudViewer", () => ({
  PointCloudViewer: () => <div data-testid="viewer-mock">viewer</div>,
}));

vi.mock("../components/HeroAtmosphere", () => ({
  HeroAtmosphere: () => <div data-testid="hero-atmosphere" />,
}));

vi.mock("../api/client", () => ({
  api: {
    health: vi.fn(async () => ({
      status: "ok",
      service: "SignalForge",
      version: "0.1.0",
      concrete_count: 2200,
      logical_count: 19,
    })),
    scenarios: vi.fn(async () => []),
    scenarioCount: vi.fn(async () => ({ count: 0 })),
    coverage: vi.fn(async () => ({
      total_concrete: 5000,
      total_logical: 46,
      by_family: { cut_in: 5 },
      by_weather: { clear: 5 },
      by_lighting: { day: 5 },
      by_difficulty: { easy: 5 },
      by_road: { straight: 5 },
      gap_count: 12,
    })),
    oddCoverage: vi.fn(async () => ({
      strength: 2,
      covered_tuples: 1769,
      reachable_tuples: 1769,
      unreachable_tuples: 4,
      coverage_pct: 100,
      complete: true,
      incomplete_logicals: [],
      by_logical: {},
    })),
    gaps: vi.fn(async () => []),
    showcase: vi.fn(async () => []),
    scenario: vi.fn(),
    openscenarioUrl: vi.fn((id: string) => `/api/scenarios/${id}/openscenario`),
    render: vi.fn(),
  },
}));

describe("SignalForge HomePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders brand-first hero and CTA", async () => {
    const onNavigate = vi.fn();
    render(<HomePage onNavigate={onNavigate} />);
    expect(screen.getAllByText("SignalForge").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Grounded AV scenarios you can audit end to end/i)
    ).toBeInTheDocument();
    const cta = screen.getAllByRole("button", { name: /Explore scenarios/i })[0];
    cta.click();
    expect(onNavigate).toHaveBeenCalledWith("/app");
  });
});

describe("SignalForge App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders viewer chrome with brand home control", async () => {
    render(<App onNavigate={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "SignalForge" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Scenario Viewer" })).toBeInTheDocument();
  });
});
