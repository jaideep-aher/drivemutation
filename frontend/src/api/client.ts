import type {
  ConcreteScenario,
  CoverageStats,
  GapItem,
  HealthResponse,
  PointCloudFrame,
  ScenarioSummary,
} from "../types/signalforge";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<HealthResponse>("/api/health"),
  scenarios: (params: Record<string, string | number | undefined>) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "" && v !== "all") q.set(k, String(v));
    });
    return get<ScenarioSummary[]>(`/api/scenarios?${q}`);
  },
  scenario: (id: string) => get<ConcreteScenario>(`/api/scenarios/${encodeURIComponent(id)}`),
  coverage: () => get<CoverageStats>("/api/coverage"),
  gaps: () => get<GapItem[]>("/api/gaps?limit=30"),
  showcase: () => get<string[]>("/api/showcase"),
  render: async (
    scenarioId: string,
    opts?: { max_frames?: number; lidar_beams?: number; lidar_azimuth?: number; degrade?: boolean }
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
    });
    if (!res.ok) throw new Error(`render failed: ${res.status}`);
    return res.json() as Promise<PointCloudFrame[]>;
  },
};
