import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "../App";
import { PlaybackControls } from "../components/PlaybackControls";
import { MetricsPanel } from "../components/MetricsPanel";
import { BirdEyeMap } from "../components/BirdEyeMap";
import type { SimulateResponse } from "../types/scenario";

const sampleRoad = {
  kind: "straight",
  length: 70,
  lanes: [{ id: "lane_ego", center_y: 0, width: 3.5, direction: 1 as const }],
};

const sampleResult: SimulateResponse = {
  scenario_id: "demo",
  valid: true,
  validation_issues: [],
  frames: [
    {
      t: 0,
      actors: [
        {
          id: "ego",
          x: 5,
          y: 0,
          vx: 10,
          vy: 0,
          heading_deg: 0,
          length: 4.5,
          width: 1.8,
          actor_type: "ego",
        },
      ],
      collisions: [],
      ego_speed: 10,
      min_ttc: 3.2,
    },
    {
      t: 0.1,
      actors: [
        {
          id: "ego",
          x: 6,
          y: 0,
          vx: 10,
          vy: 0,
          heading_deg: 0,
          length: 4.5,
          width: 1.8,
          actor_type: "ego",
        },
      ],
      collisions: [],
      ego_speed: 10,
      min_ttc: 3.1,
    },
  ],
  metrics: {
    duration_s: 1,
    timestep_s: 0.1,
    frame_count: 2,
    collision_count: 0,
    min_ttc: 3.1,
    max_acceleration: 0,
    max_jerk: 0,
    lane_boundary_violations: 0,
    initial_overlap: false,
    oracle_results: [
      {
        id: "o_collision",
        type: "no_collision",
        passed: true,
        value: 0,
        message: "no collisions",
      },
    ],
  },
  trajectories: { ego: [[5, 0], [6, 0]] },
};

describe("PlaybackControls", () => {
  it("invokes play pause restart scrub handlers", () => {
    const onPlay = vi.fn();
    const onPause = vi.fn();
    const onRestart = vi.fn();
    const onScrub = vi.fn();
    const { rerender } = render(
      <PlaybackControls
        playing={false}
        frameIndex={0}
        frameCount={10}
        onPlay={onPlay}
        onPause={onPause}
        onRestart={onRestart}
        onScrub={onScrub}
      />,
    );
    fireEvent.click(screen.getByLabelText("Play"));
    expect(onPlay).toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText("Restart"));
    expect(onRestart).toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Scrub timeline"), { target: { value: "4" } });
    expect(onScrub).toHaveBeenCalledWith(4);

    rerender(
      <PlaybackControls
        playing
        frameIndex={2}
        frameCount={10}
        onPlay={onPlay}
        onPause={onPause}
        onRestart={onRestart}
        onScrub={onScrub}
      />,
    );
    fireEvent.click(screen.getByLabelText("Pause"));
    expect(onPause).toHaveBeenCalled();
  });
});

describe("MetricsPanel", () => {
  it("shows oracle pass/fail and collision count", () => {
    render(
      <MetricsPanel result={sampleResult} egoSpeed={10} frameMinTtc={3.1} />,
    );
    expect(screen.getByTestId("oracle-results")).toHaveTextContent("PASS");
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("10.00 m/s")).toBeInTheDocument();
  });

  it("shows validation errors when invalid", () => {
    render(
      <MetricsPanel
        result={{
          ...sampleResult,
          valid: false,
          metrics: null,
          frames: [],
          validation_issues: [{ code: "no_oracle", message: "need oracle" }],
        }}
        egoSpeed={null}
        frameMinTtc={null}
      />,
    );
    expect(screen.getByTestId("validation-errors")).toHaveTextContent("no_oracle");
  });
});

describe("BirdEyeMap", () => {
  it("renders svg map with actors", () => {
    render(
      <BirdEyeMap
        road={sampleRoad}
        frame={sampleResult.frames[0]}
        trajectories={sampleResult.trajectories}
      />,
    );
    expect(screen.getByTestId("bird-eye-map")).toBeInTheDocument();
    expect(screen.getByTestId("actor-ego")).toBeInTheDocument();
  });
});

describe("App integration", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("loads presets and simulates", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/presets")) {
        return new Response(
          JSON.stringify([
            {
              id: "wrong_way_vehicle",
              name: "Wrong-way vehicle",
              description: "Head-on conflict",
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/presets/wrong_way_vehicle")) {
        return new Response(
          JSON.stringify({
            id: "wrong_way_vehicle",
            name: "Wrong-way vehicle",
            description: "Head-on conflict",
            duration_s: 1,
            timestep_s: 0.1,
            road: sampleRoad,
            ego: {
              id: "ego",
              actor_type: "ego",
              position: { x: 5, y: 0 },
              velocity: { vx: 10, vy: 0 },
              dimensions: { length: 4.5, width: 1.8 },
              lane_id: "lane_ego",
              heading_deg: 0,
              behavior: { type: "constant_velocity" },
            },
            actors: [],
            triggers: [],
            oracles: [{ id: "o", type: "no_collision" }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/api/simulate")) {
        return new Response(JSON.stringify(sampleResult), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(screen.getByTestId("scenario-select")).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByTestId("scenario-description")).toHaveTextContent("Head-on"),
    );
    fireEvent.click(screen.getByTestId("run-simulate"));
    await waitFor(() => expect(screen.getByTestId("oracle-results")).toHaveTextContent("PASS"));
    expect(screen.getByTestId("bird-eye-map")).toBeInTheDocument();
  });
});
