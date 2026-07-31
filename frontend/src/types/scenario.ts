export interface Position2D {
  x: number;
  y: number;
}

export interface Velocity2D {
  vx: number;
  vy: number;
}

export interface Dimensions2D {
  length: number;
  width: number;
}

export interface ActorBehavior {
  type: string;
  trigger_id?: string | null;
  post_trigger_velocity?: Velocity2D | null;
  target_lane_id?: string | null;
  lateral_speed?: number | null;
}

export interface ActorState {
  id: string;
  actor_type: string;
  position: Position2D;
  velocity: Velocity2D;
  dimensions: Dimensions2D;
  lane_id?: string | null;
  heading_deg: number;
  behavior: ActorBehavior;
}

export interface Lane {
  id: string;
  center_y: number;
  width: number;
  direction: 1 | -1;
}

export interface RoadLayout {
  kind: string;
  length: number;
  lanes: Lane[];
  intersection_center?: [number, number] | null;
  intersection_size?: number | null;
  cross_lane_width?: number;
}

export interface Trigger {
  id: string;
  type: string;
  time_s?: number | null;
  distance_m?: number | null;
  reference_point?: Position2D | null;
  region_half_extent_m?: number | null;
}

export interface SafetyOracle {
  id: string;
  type: string;
  threshold?: number | null;
  actor_id?: string | null;
}

export interface ScenarioSpec {
  id: string;
  name: string;
  description: string;
  duration_s: number;
  timestep_s: number;
  road: RoadLayout;
  ego: ActorState;
  actors: ActorState[];
  triggers: Trigger[];
  oracles: SafetyOracle[];
  assumptions?: { id: string; statement: string }[];
  unknowns?: { id: string; statement: string }[];
}

export interface PresetSummary {
  id: string;
  name: string;
  description: string;
}

export interface ValidationIssue {
  code: string;
  message: string;
  path?: string | null;
}

export interface ActorFrameState {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  heading_deg: number;
  length: number;
  width: number;
  actor_type: string;
}

export interface SimulationFrame {
  t: number;
  actors: ActorFrameState[];
  collisions: [string, string][];
  ego_speed: number;
  min_ttc: number | null;
}

export interface OracleResult {
  id: string;
  type: string;
  passed: boolean;
  value?: number | null;
  message: string;
}

export interface SimulationMetrics {
  duration_s: number;
  timestep_s: number;
  frame_count: number;
  collision_count: number;
  min_ttc: number | null;
  max_acceleration: number;
  max_jerk: number;
  lane_boundary_violations: number;
  initial_overlap: boolean;
  oracle_results: OracleResult[];
}

export interface SimulateResponse {
  scenario_id: string;
  valid: boolean;
  validation_issues: ValidationIssue[];
  frames: SimulationFrame[];
  metrics: SimulationMetrics | null;
  trajectories: Record<string, [number, number][]>;
}
