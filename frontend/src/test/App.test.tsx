import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "../App";
import { PlaybackControls } from "../components/PlaybackControls";
import { BirdEyeMap } from "../components/BirdEyeMap";
import { EvaluationPage } from "../components/EvaluationPage";
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
  ],
  metrics: {
    duration_s: 1,
    timestep_s: 0.1,
    frame_count: 1,
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
  trajectories: { ego: [[5, 0]] },
};

describe("PlaybackControls", () => {
  it("invokes play pause restart scrub handlers", () => {
    const onPlay = vi.fn();
    const onPause = vi.fn();
    const onRestart = vi.fn();
    const onScrub = vi.fn();
    render(
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

describe("EvaluationPage", () => {
  it("shows empty evaluation state", () => {
    render(
      <EvaluationPage
        summary={{ available: false, base: null, fine_tuned: null, comparison: null }}
        loading={false}
        error={null}
        onRefresh={() => undefined}
      />,
    );
    expect(screen.getByTestId("eval-empty")).toBeInTheDocument();
  });
});

describe("App integration", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.location.hash = "#/";
  });

  it("shows home then runs demo compare", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/presets")) {
        return new Response(
          JSON.stringify([
            {
              id: "wrong_way_vehicle",
              name: "Wrong-way vehicle",
              description: "Head-on conflict",
              default_testing_goal: "stress head-on",
              kind: "scenario",
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/models/status")) {
        return new Response(
          JSON.stringify({
            api_key_configured: true,
            base_model: "gpt-4o-mini-2024-07-18",
            fine_tuned_model: "ft:demo",
            fine_tuning_job_id: null,
            fine_tuning_status: "succeeded",
            fine_tuning_error: null,
            training_file_id: null,
            validation_file_id: null,
            base_ready: true,
            fine_tuned_ready: true,
            job_pending: false,
            job_failed: false,
          }),
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
      if (url.endsWith("/api/compile/base") || url.endsWith("/api/compile/fine-tuned")) {
        return new Response(
          JSON.stringify({
            mode: url.includes("fine") ? "fine-tuned" : "base",
            model: "gpt-4o-mini-2024-07-18",
            ok: true,
            error_code: null,
            error: null,
            target_kind: "mutation",
            json_parse_ok: true,
            schema_valid: true,
            physical_valid: true,
            parsed: { status: "accepted" },
            validation_issues: [],
            simulation: sampleResult,
            latency_s: 0.2,
            usage: { total_tokens: 100 },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/api/evaluation/summary")) {
        return new Response(
          JSON.stringify({
            available: false,
            base: null,
            fine_tuned: null,
            comparison: null,
            methodology: { test_set_size: 30, temperature: 0 },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    expect(screen.getByTestId("home-page")).toHaveTextContent("DriveMutation");
    await waitFor(() =>
      expect(screen.getByTestId("model-status")).toHaveTextContent("OpenAI"),
    );

    fireEvent.click(screen.getByTestId("home-cta"));
    await waitFor(() => expect(screen.getByTestId("demo-page")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("scenario-select")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("compare-both"));
    await waitFor(() =>
      expect(screen.getByTestId("compile-panel-fine-tuned")).toHaveTextContent("Worked"),
    );
    expect(screen.getByTestId("bird-eye-map")).toBeInTheDocument();
    expect(screen.getByTestId("oracle-results")).toHaveTextContent("PASS");

    fireEvent.click(screen.getByTestId("nav-eval"));
    await waitFor(() => expect(screen.getByTestId("evaluation-page")).toBeInTheDocument());
  });
});
