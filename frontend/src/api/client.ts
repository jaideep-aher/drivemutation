import type {
  ConcreteScenario,
  CoverageStats,
  GapItem,
  HealthResponse,
  OddCoverage,
  PointCloudFrame,
  ScenarioSummary,
} from "../types/signalforge";

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export interface ScenarioQuery {
  family?: string;
  weather?: string;
  difficulty?: string;
  lighting?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

function queryString(params: ScenarioQuery): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "" && value !== "all") {
      search.set(key, String(value));
    }
  });
  return search.toString();
}

export const api = {
  health: () => get<HealthResponse>("/api/health"),

  scenarios: (params: ScenarioQuery, signal?: AbortSignal) =>
    get<ScenarioSummary[]>(`/api/scenarios?${queryString(params)}`, signal),

  /** How many scenarios match, so the list can page instead of silently truncating. */
  scenarioCount: (params: ScenarioQuery, signal?: AbortSignal) => {
    const { limit: _limit, offset: _offset, ...filters } = params;
    return get<{ count: number }>(`/api/scenarios/count?${queryString(filters)}`, signal);
  },

  scenario: (id: string, signal?: AbortSignal) =>
    get<ConcreteScenario>(`/api/scenarios/${encodeURIComponent(id)}`, signal),

  coverage: () => get<CoverageStats>("/api/coverage"),
  oddCoverage: () => get<OddCoverage>("/api/coverage/odd"),
  gaps: (limit = 50) => get<GapItem[]>(`/api/gaps?limit=${limit}`),
  showcase: () => get<string[]>("/api/showcase"),

  /** Direct link to the runnable OpenSCENARIO bundle (.xosc + .xodr, zipped). */
  openscenarioUrl: (id: string, opts?: { trajectoryMode?: boolean }) => {
    const search = new URLSearchParams();
    if (opts?.trajectoryMode) search.set("trajectory_mode", "true");
    const suffix = search.toString() ? `?${search}` : "";
    return `/api/scenarios/${encodeURIComponent(id)}/openscenario${suffix}`;
  },

  render: async (
    scenarioId: string,
    opts?: {
      max_frames?: number;
      lidar_beams?: number;
      lidar_azimuth?: number;
      degrade?: boolean;
    },
    signal?: AbortSignal
  ) => {
    const res = await fetch("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: scenarioId,
        max_frames: opts?.max_frames ?? 16,
        lidar_beams: opts?.lidar_beams ?? 24,
        lidar_azimuth: opts?.lidar_azimuth ?? 180,
        degrade: opts?.degrade ?? true,
      }),
      signal,
    });
    if (!res.ok) throw new Error(`render failed: ${res.status}`);
    return res.json() as Promise<PointCloudFrame[]>;
  },
};
