// Families come from the backend catalog and grow with it (the NHTSA typology
// added backing, object, evasive_action, non_collision and vehicle_failure), so
// this stays a string rather than a closed union the UI would silently fall
// behind on. The filter list is built from the live coverage response.
export type ScenarioFamily = string;

export interface ScenarioSummary {
  id: string;
  logical_id: string;
  family: ScenarioFamily;
  name: string;
  weather: string;
  lighting: string;
  road_geometry: string;
  difficulty: string | null;
  min_ttc_s: number | null;
  collision: boolean;
  provenance_citation: string;
  crash_frequency_weight: number;
}

export interface Provenance {
  source: string;
  citation: string;
  parent_id: string | null;
  seed: number;
  notes: string;
}

export interface CriticalityMetrics {
  min_ttc_s: number | null;
  min_distance_m: number | null;
  pet_s: number | null;
  required_decel_mps2: number | null;
  collision: boolean;
  preventable: boolean | null;
}

export interface ConcreteScenario {
  id: string;
  logical_id: string;
  family: string;
  name: string;
  provenance: Provenance;
  weather: string;
  lighting: string;
  road_geometry: string;
  duration_s: number;
  ego: Record<string, unknown>;
  actors: Record<string, unknown>[];
  odd: Record<string, unknown>;
  crash_frequency_weight: number;
  metrics: CriticalityMetrics | null;
  difficulty: string | null;
}

export interface Box3D {
  instance_id: number;
  category: string;
  x: number;
  y: number;
  z: number;
  length: number;
  width: number;
  height: number;
  heading_deg: number;
  vx: number;
  vy: number;
  occlusion: number;
  num_lidar_hits: number;
}

export interface PointCloudFrame {
  t: number;
  xyz: number[];
  intensity: number[];
  semantic: number[];
  instance: number[];
  boxes: Box3D[];
  radar_xyz: number[];
  radar_doppler: number[];
  radar_rcs: number[];
}

export interface CoverageStats {
  total_concrete: number;
  total_logical: number;
  by_family: Record<string, number>;
  by_weather: Record<string, number>;
  by_lighting: Record<string, number>;
  by_difficulty: Record<string, number>;
  by_road: Record<string, number>;
  gap_count: number;
}

export interface OddCoverage {
  strength: number;
  covered_tuples: number;
  reachable_tuples: number;
  unreachable_tuples: number;
  coverage_pct: number;
  complete: boolean;
  incomplete_logicals: string[];
  by_logical: Record<string, Record<string, unknown>>;
}

export interface GapItem {
  incident_id: string;
  narrative: string;
  manufacturer: string;
  date: string;
  reason: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  concrete_count: number;
  logical_count: number;
}
