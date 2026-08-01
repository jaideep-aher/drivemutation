import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import App from "../App";
import { api } from "../api/client";

vi.mock("../components/PointCloudViewer", () => ({
  PointCloudViewer: () => <div data-testid="viewer-mock">viewer</div>,
}));

const TOTAL = 5000;

function makeRow(i: number) {
  return {
    id: `scenario-${i}`,
    logical_id: "nhtsa-25-lead-vehicle-decelerating",
    family: i % 2 ? "rear_end" : "backing",
    name: `Scenario ${i}`,
    weather: "clear",
    lighting: "day",
    road_geometry: "straight",
    difficulty: "medium",
    min_ttc_s: 2.4,
    collision: false,
    provenance_citation: "NHTSA DOT HS 810 767 (2007) pre-crash scenario 25",
    crash_frequency_weight: 0.44,
  };
}

vi.mock("../api/client", () => {
  const scenarios = vi.fn(async (params: { limit?: number; offset?: number }) => {
    const offset = params.offset ?? 0;
    const limit = params.limit ?? 60;
    return Array.from({ length: limit }, (_, k) => makeRow(offset + k));
  });
  return {
    api: {
      health: vi.fn(async () => ({
        status: "ok",
        service: "SignalForge",
        version: "0.1.0",
        concrete_count: TOTAL,
        logical_count: 46,
      })),
      scenarios,
      scenarioCount: vi.fn(async () => ({ count: TOTAL })),
      coverage: vi.fn(async () => ({
        total_concrete: TOTAL,
        total_logical: 46,
        // Includes families the old hardcoded filter list did not have.
        by_family: { rear_end: 770, backing: 120, evasive_action: 90, object: 80 },
        by_weather: { clear: 5 },
        by_lighting: { day: 5 },
        by_difficulty: { easy: 5 },
        by_road: { straight: 5 },
        gap_count: 354,
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
      scenario: vi.fn(async (id: string) => ({
        ...makeRow(0),
        id,
        provenance: {
          source: "nhtsa_precrash",
          citation: "NHTSA DOT HS 810 767 (2007) pre-crash scenario 25",
          parent_id: "nhtsa-25-lead-vehicle-decelerating",
          seed: 42,
          notes: "",
        },
        duration_s: 8,
        ego: {},
        actors: [],
        odd: {},
        metrics: {
          min_ttc_s: 2.4,
          min_distance_m: 5.8,
          pet_s: null,
          required_decel_mps2: 3.1,
          collision: false,
          preventable: true,
        },
      })),
      openscenarioUrl: vi.fn((id: string) => `/api/scenarios/${id}/openscenario`),
      render: vi.fn(async () => []),
    },
  };
});

describe("scenario browsing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows how many scenarios matched, not just the page", async () => {
    render(<App onNavigate={vi.fn()} />);
    // The catalog has thousands; the list must say so rather than silently
    // truncating at the page size.
    expect(await screen.findByText(`60 of ${TOTAL.toLocaleString()}`)).toBeInTheDocument();
  });

  it("builds the family filter from the live catalog", async () => {
    render(<App onNavigate={vi.fn()} />);
    const familySelect = await screen.findByLabelText<HTMLSelectElement>("Family", {
      exact: false,
    });

    // The select renders with just "all" and is repopulated when the coverage
    // request resolves, so the options must be awaited rather than read once.
    await waitFor(() => {
      const values = Array.from(familySelect.options).map((o) => o.value);
      // These families were added with the NHTSA typology and are unreachable
      // if the filter list is hardcoded.
      expect(values).toContain("backing");
      expect(values).toContain("evasive_action");
      expect(values).toContain("object");
    });
  });

  it("requests the next page with an offset when loading more", async () => {
    render(<App onNavigate={vi.fn()} />);
    await screen.findByText(`60 of ${TOTAL.toLocaleString()}`);

    const scenarios = vi.mocked(api.scenarios);
    scenarios.mockClear();

    // IntersectionObserver does not fire in jsdom, so drive the same path the
    // sentinel would: keyboard past the end of the loaded page.
    const list = screen.getByRole("listbox", { name: "Scenarios" });
    for (let i = 0; i < 61; i += 1) {
      fireEvent.keyDown(list, { key: "ArrowDown" });
    }

    await waitFor(() => {
      expect(scenarios).toHaveBeenCalledWith(
        expect.objectContaining({ offset: 60, limit: 60 })
      );
    });
  });

  it("debounces the search box into a single filtered request", async () => {
    render(<App onNavigate={vi.fn()} />);
    await screen.findByText(`60 of ${TOTAL.toLocaleString()}`);

    const scenarios = vi.mocked(api.scenarios);
    scenarios.mockClear();

    const search = screen.getByLabelText("Search scenarios");
    fireEvent.change(search, { target: { value: "p" } });
    fireEvent.change(search, { target: { value: "pe" } });
    fireEvent.change(search, { target: { value: "ped" } });

    await waitFor(() => {
      expect(scenarios).toHaveBeenCalledWith(
        expect.objectContaining({ q: "ped", offset: 0 }),
        expect.anything()
      );
    });
    // One request for the settled query, not one per keystroke.
    const queries = scenarios.mock.calls.map(([params]) => (params as { q?: string }).q);
    expect(queries.filter((q) => q === "p")).toHaveLength(0);
    expect(queries.filter((q) => q === "pe")).toHaveLength(0);
  });

  it("moves the selection with the arrow keys", async () => {
    render(<App onNavigate={vi.fn()} />);
    await screen.findByText(`60 of ${TOTAL.toLocaleString()}`);

    const list = screen.getByRole("listbox", { name: "Scenarios" });
    // Matched by id rather than accessible name: "Scenario 1" is a prefix of
    // "Scenario 10", so a name regex would match several rows.
    const row = (i: number) => document.getElementById(`scenario-scenario-${i}`);

    expect(row(0)).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(list, { key: "ArrowDown" });
    await waitFor(() => {
      expect(row(1)).toHaveAttribute("aria-selected", "true");
    });

    fireEvent.keyDown(list, { key: "ArrowDown" });
    await waitFor(() => {
      expect(row(2)).toHaveAttribute("aria-selected", "true");
    });

    fireEvent.keyDown(list, { key: "ArrowUp" });
    await waitFor(() => {
      expect(row(1)).toHaveAttribute("aria-selected", "true");
    });
  });

  it("offers the selected scenario as a runnable OpenSCENARIO download", async () => {
    render(<App onNavigate={vi.fn()} />);
    const link = await screen.findByRole("link", { name: /OpenSCENARIO/i });
    expect(link).toHaveAttribute("href", "/api/scenarios/scenario-0/openscenario");
    expect(link).toHaveAttribute("download");
  });

  it("reports pairwise ODD coverage on the coverage tab", async () => {
    render(<App onNavigate={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Coverage" }));
    expect(await screen.findByText("100.0%")).toBeInTheDocument();
    expect(
      screen.getByText(/4 ruled out by physical constraints/i)
    ).toBeInTheDocument();
  });
});
