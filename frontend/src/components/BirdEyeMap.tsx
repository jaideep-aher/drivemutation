import type { ActorFrameState, RoadLayout, SimulationFrame } from "../types/scenario";

/* Waymo palette only — from waymo.com */
const ACTOR_COLORS: Record<string, string> = {
  ego: "#0077ff",
  vehicle: "#006fee",
  cyclist: "#00e89d",
  pedestrian: "#ea0000",
};

interface BirdEyeProps {
  road: RoadLayout;
  frame: SimulationFrame | null;
  trajectories: Record<string, [number, number][]>;
  width?: number;
  height?: number;
}

function laneLeft(centerY: number, width: number): number {
  return centerY + width / 2;
}

function laneRight(centerY: number, width: number): number {
  return centerY - width / 2;
}

export function BirdEyeMap({
  road,
  frame,
  trajectories,
  width = 720,
  height = 360,
}: BirdEyeProps) {
  const pad = 24;
  const worldW = road.length;
  const ys = road.lanes.flatMap((l) => [laneRight(l.center_y, l.width), laneLeft(l.center_y, l.width)]);
  const minY = Math.min(-12, ...ys) - 4;
  const maxY = Math.max(12, ...ys) + 4;
  const worldH = maxY - minY;

  const sx = (x: number) => pad + (x / worldW) * (width - 2 * pad);
  const sy = (y: number) => height - pad - ((y - minY) / worldH) * (height - 2 * pad);

  return (
    <svg
      className="bird-eye"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Bird's-eye scenario map"
      data-testid="bird-eye-map"
    >
      <defs>
        <linearGradient id="asphalt" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#132237" />
          <stop offset="100%" stopColor="#050f1e" />
        </linearGradient>
      </defs>
      <rect x={0} y={0} width={width} height={height} fill="#000000" />
      <rect
        x={sx(0)}
        y={sy(maxY)}
        width={sx(worldW) - sx(0)}
        height={sy(minY) - sy(maxY)}
        fill="url(#asphalt)"
        rx={2}
      />

      {road.lanes.map((lane) => (
        <g key={lane.id}>
          <line
            x1={sx(0)}
            y1={sy(lane.center_y)}
            x2={sx(worldW)}
            y2={sy(lane.center_y)}
            stroke="#a2abb9"
            strokeWidth={1}
            strokeDasharray="8 10"
            opacity={0.55}
          />
          <line
            x1={sx(0)}
            y1={sy(laneLeft(lane.center_y, lane.width))}
            x2={sx(worldW)}
            y2={sy(laneLeft(lane.center_y, lane.width))}
            stroke="#ccd3dc"
            strokeWidth={1.2}
            opacity={0.28}
          />
          <line
            x1={sx(0)}
            y1={sy(laneRight(lane.center_y, lane.width))}
            x2={sx(worldW)}
            y2={sy(laneRight(lane.center_y, lane.width))}
            stroke="#ccd3dc"
            strokeWidth={1.2}
            opacity={0.28}
          />
        </g>
      ))}

      {road.kind === "four_way_intersection" &&
        road.intersection_center &&
        road.intersection_size != null && (
          <rect
            x={sx(road.intersection_center[0] - road.intersection_size)}
            y={sy(road.intersection_center[1] + road.intersection_size)}
            width={
              sx(road.intersection_center[0] + road.intersection_size) -
              sx(road.intersection_center[0] - road.intersection_size)
            }
            height={
              sy(road.intersection_center[1] - road.intersection_size) -
              sy(road.intersection_center[1] + road.intersection_size)
            }
            fill="#2f3e4f"
            stroke="#0077ff"
            strokeWidth={1.5}
            opacity={0.9}
          />
        )}

      {Object.entries(trajectories).map(([id, pts]) => {
        if (pts.length < 2) return null;
        const d = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${sx(p[0])} ${sy(p[1])}`).join(" ");
        const actor = frame?.actors.find((a) => a.id === id);
        const color = ACTOR_COLORS[actor?.actor_type ?? "vehicle"] ?? "#7c899a";
        return (
          <path
            key={`traj-${id}`}
            d={d}
            fill="none"
            stroke={color}
            strokeWidth={1.5}
            opacity={0.45}
          />
        );
      })}

      {frame?.actors.map((actor) => (
        <ActorRect key={actor.id} actor={actor} sx={sx} sy={sy} />
      ))}
    </svg>
  );
}

function ActorRect({
  actor,
  sx,
  sy,
}: {
  actor: ActorFrameState;
  sx: (x: number) => number;
  sy: (y: number) => number;
}) {
  const color = ACTOR_COLORS[actor.actor_type] ?? "#7c899a";
  const cx = sx(actor.x);
  const cy = sy(actor.y);
  const metre = Math.abs(sx(1) - sx(0));
  const w = actor.length * metre;
  const h = actor.width * metre;
  return (
    <g transform={`translate(${cx} ${cy}) rotate(${-actor.heading_deg})`}>
      <rect
        x={-w / 2}
        y={-h / 2}
        width={w}
        height={h}
        fill={color}
        stroke="#050f1e"
        strokeWidth={0.8}
        rx={1.5}
        opacity={0.95}
        data-testid={`actor-${actor.id}`}
        aria-label={`${actor.id} (${actor.actor_type})`}
      >
        <title>{`${actor.id} (${actor.actor_type})`}</title>
      </rect>
      <line x1={0} y1={0} x2={w * 0.45} y2={0} stroke="#ffffff" strokeWidth={1.5} />
    </g>
  );
}
