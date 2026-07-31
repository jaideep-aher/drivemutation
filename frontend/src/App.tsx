import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import { PointCloudViewer } from "./components/PointCloudViewer";
import type {
  ConcreteScenario,
  CoverageStats,
  GapItem,
  PointCloudFrame,
  ScenarioSummary,
} from "./types/signalforge";

const FAMILIES = [
  "all",
  "rear_end",
  "cut_in",
  "cut_out",
  "deceleration",
  "pedestrian",
  "vru_crossing",
  "crossing_paths",
  "lane_change",
  "opposite_direction",
  "road_departure",
  "control_loss",
  "animal",
  "pedalcyclist",
  "sensor_degradation",
];

const WEATHERS = ["all", "clear", "rain", "fog", "snow"];
const DIFFS = ["all", "easy", "medium", "hard", "unpreventable"];

type Navigate = (path: string) => void;

export default function App({ onNavigate }: { onNavigate?: Navigate } = {}) {
  const [health, setHealth] = useState<string>("…");
  const [list, setList] = useState<ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConcreteScenario | null>(null);
  const [frames, setFrames] = useState<PointCloudFrame[]>([]);
  const [frameIdx, setFrameIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [coverage, setCoverage] = useState<CoverageStats | null>(null);
  const [gaps, setGaps] = useState<GapItem[]>([]);
  const [showRadar, setShowRadar] = useState(true);
  const [family, setFamily] = useState("all");
  const [weather, setWeather] = useState("all");
  const [difficulty, setDifficulty] = useState("all");
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<"viewer" | "coverage" | "gaps">("viewer");

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(`${h.service} v${h.version} · ${h.concrete_count} scenarios`))
      .catch(() => setHealth("API offline"));
    api.coverage().then(setCoverage).catch(() => undefined);
    api.gaps().then(setGaps).catch(() => undefined);
  }, []);

  const refreshList = useCallback(() => {
    api
      .scenarios({ family, weather, difficulty, q, limit: 120 })
      .then((rows) => {
        setList(rows);
        if (!selectedId && rows.length) setSelectedId(rows[0].id);
      })
      .catch((e) => setError(String(e)));
  }, [family, weather, difficulty, q, selectedId]);

  useEffect(() => {
    refreshList();
  }, [family, weather, difficulty]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadScenario = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    setPlaying(false);
    try {
      const [sc, fr] = await Promise.all([
        api.scenario(id),
        api.render(id, { max_frames: 16, lidar_beams: 24, lidar_azimuth: 160 }),
      ]);
      setDetail(sc);
      setFrames(fr);
      setFrameIdx(0);
    } catch (e) {
      setError(String(e));
      setFrames([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) loadScenario(selectedId);
  }, [selectedId, loadScenario]);

  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const id = window.setInterval(() => {
      setFrameIdx((i) => (i + 1) % frames.length);
    }, 180);
    return () => clearInterval(id);
  }, [playing, frames.length]);

  const frame = frames[frameIdx] ?? null;

  const familyBars = useMemo(() => {
    if (!coverage) return [] as { k: string; n: number; pct: number }[];
    const entries = Object.entries(coverage.by_family).sort(
      (a, b) => (b[1] as number) - (a[1] as number)
    );
    const max = Math.max(...entries.map(([, n]) => n as number), 1);
    return entries.map(([k, n]) => ({ k, n: n as number, pct: (100 * (n as number)) / max }));
  }, [coverage]);

  const goHome = () => {
    if (onNavigate) onNavigate("/");
    else window.location.href = "/";
  };

  return (
    <div className="sf-app">
      <header className="sf-header">
        <div>
          <button type="button" className="sf-brand-btn" onClick={goHome}>
            SignalForge
          </button>
          <p className="tagline">
            Auditable AV scenarios · synthetic lidar/radar · traced to NHTSA / R157 / Euro NCAP /
            real ADS incidents
          </p>
        </div>
        <div className="sf-header-right">
          <button type="button" className="sf-link-btn" onClick={goHome}>
            Home
          </button>
          <div className="health">{health}</div>
        </div>
      </header>

      <nav className="sf-tabs">
        <button className={tab === "viewer" ? "active" : ""} onClick={() => setTab("viewer")}>
          Scenario Viewer
        </button>
        <button className={tab === "coverage" ? "active" : ""} onClick={() => setTab("coverage")}>
          Coverage
        </button>
        <button className={tab === "gaps" ? "active" : ""} onClick={() => setTab("gaps")}>
          Incident Gaps ({gaps.length})
        </button>
      </nav>

      {tab === "viewer" && (
        <div className="sf-main">
          <aside className="sf-sidebar">
            <div className="filters">
              <input
                placeholder="Search…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && refreshList()}
              />
              <select value={family} onChange={(e) => setFamily(e.target.value)}>
                {FAMILIES.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
              <select value={weather} onChange={(e) => setWeather(e.target.value)}>
                {WEATHERS.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
              <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
                {DIFFS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <div className="scenario-list">
              {list.map((s) => (
                <button
                  key={s.id}
                  className={`scenario-row ${selectedId === s.id ? "selected" : ""}`}
                  onClick={() => setSelectedId(s.id)}
                >
                  <div className="row-top">
                    <span className="family">{s.family}</span>
                    <span className={`diff ${s.difficulty ?? ""}`}>{s.difficulty ?? "—"}</span>
                  </div>
                  <div className="row-name">{s.name}</div>
                  <div className="row-meta">
                    {s.weather} · {s.lighting}
                    {s.min_ttc_s != null ? ` · TTC ${s.min_ttc_s.toFixed(2)}s` : ""}
                  </div>
                </button>
              ))}
              {list.length === 0 && <p className="empty">No scenarios match filters.</p>}
            </div>
          </aside>

          <section className="sf-stage">
            <div className="viewer-wrap">
              {loading && <div className="overlay">Rendering lidar…</div>}
              {error && <div className="overlay error">{error}</div>}
              <PointCloudViewer frame={frame} showRadar={showRadar} />
            </div>
            <div className="playback">
              <button onClick={() => setPlaying((p) => !p)} disabled={!frames.length}>
                {playing ? "Pause" : "Play"}
              </button>
              <input
                type="range"
                min={0}
                max={Math.max(frames.length - 1, 0)}
                value={frameIdx}
                onChange={(e) => {
                  setPlaying(false);
                  setFrameIdx(Number(e.target.value));
                }}
              />
              <span className="frame-label">
                frame {frameIdx + 1}/{frames.length || 0}
                {frame ? ` · t=${frame.t.toFixed(1)}s` : ""}
              </span>
              <label className="chk">
                <input
                  type="checkbox"
                  checked={showRadar}
                  onChange={(e) => setShowRadar(e.target.checked)}
                />
                radar
              </label>
            </div>

            {detail && (
              <div className="detail-grid">
                <div className="card provenance">
                  <h3>Provenance</h3>
                  <dl>
                    <dt>Source</dt>
                    <dd>{detail.provenance.source}</dd>
                    <dt>Citation</dt>
                    <dd>{detail.provenance.citation}</dd>
                    <dt>Parent logical</dt>
                    <dd>{detail.provenance.parent_id ?? detail.logical_id}</dd>
                    <dt>Seed</dt>
                    <dd>{detail.provenance.seed}</dd>
                  </dl>
                  <p className="hint">
                    Every scenario traces to a regulation clause, crash typology, HAZOP derivation,
                    or real ADS incident — never free-invented.
                  </p>
                </div>
                <div className="card metrics">
                  <h3>Criticality</h3>
                  <dl>
                    <dt>Difficulty</dt>
                    <dd>{detail.difficulty ?? "—"}</dd>
                    <dt>Min TTC</dt>
                    <dd>
                      {detail.metrics?.min_ttc_s != null
                        ? `${detail.metrics.min_ttc_s.toFixed(2)} s`
                        : "—"}
                    </dd>
                    <dt>Min distance</dt>
                    <dd>
                      {detail.metrics?.min_distance_m != null
                        ? `${detail.metrics.min_distance_m.toFixed(2)} m`
                        : "—"}
                    </dd>
                    <dt>Required decel</dt>
                    <dd>
                      {detail.metrics?.required_decel_mps2 != null
                        ? `${detail.metrics.required_decel_mps2.toFixed(2)} m/s²`
                        : "—"}
                    </dd>
                    <dt>Preventable (R157 model)</dt>
                    <dd>
                      {detail.metrics?.preventable == null
                        ? "—"
                        : detail.metrics.preventable
                          ? "yes"
                          : "no"}
                    </dd>
                    <dt>Collision</dt>
                    <dd>{detail.metrics?.collision ? "yes" : "no"}</dd>
                  </dl>
                </div>
                <div className="card odd">
                  <h3>ODD / Sensors</h3>
                  <dl>
                    <dt>Weather</dt>
                    <dd>{detail.weather}</dd>
                    <dt>Lighting</dt>
                    <dd>{detail.lighting}</dd>
                    <dt>Road</dt>
                    <dd>{detail.road_geometry}</dd>
                    <dt>Crash weight</dt>
                    <dd>{detail.crash_frequency_weight.toFixed(2)}</dd>
                  </dl>
                  <pre className="odd-json">{JSON.stringify(detail.odd, null, 2)}</pre>
                  {frame && (
                    <p className="hint">
                      Lidar points: {Math.floor(frame.xyz.length / 3)} · Radar returns:{" "}
                      {Math.floor(frame.radar_xyz.length / 3)} · Boxes: {frame.boxes.length}
                      {frame.boxes[0]
                        ? ` · occlusion[0]=${frame.boxes[0].occlusion.toFixed(2)}`
                        : ""}
                    </p>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {tab === "coverage" && coverage && (
        <div className="sf-panel">
          <div className="stat-row">
            <div className="stat">
              <div className="n">{coverage.total_concrete}</div>
              <div className="l">concrete scenarios</div>
            </div>
            <div className="stat">
              <div className="n">{coverage.total_logical}</div>
              <div className="l">logical (catalog)</div>
            </div>
            <div className="stat">
              <div className="n">{coverage.gap_count}</div>
              <div className="l">SGO gaps</div>
            </div>
            <div className="stat">
              <div className="n">{Object.keys(coverage.by_family).length}</div>
              <div className="l">families</div>
            </div>
          </div>
          <h3>By family</h3>
          <div className="bars">
            {familyBars.map(({ k, n, pct }) => (
              <div key={k} className="bar-row">
                <span className="bar-label">{k}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${pct}%` }} />
                </div>
                <span className="bar-n">{n}</span>
              </div>
            ))}
          </div>
          <div className="two-col">
            <div>
              <h3>Weather</h3>
              <ul>
                {Object.entries(coverage.by_weather).map(([k, n]) => (
                  <li key={k}>
                    {k}: {n as number}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3>Difficulty</h3>
              <ul>
                {Object.entries(coverage.by_difficulty).map(([k, n]) => (
                  <li key={k}>
                    {k}: {n as number}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {tab === "gaps" && (
        <div className="sf-panel">
          <p className="hint">
            Real NHTSA SGO ADS incident narratives that did not match any catalog family. These are
            candidates for new logical scenarios.
          </p>
          <div className="gap-list">
            {gaps.map((g) => (
              <article key={g.incident_id} className="gap-card">
                <header>
                  <strong>{g.incident_id}</strong>
                  <span>
                    {g.manufacturer} · {g.date}
                  </span>
                </header>
                <p>{g.narrative}</p>
              </article>
            ))}
            {gaps.length === 0 && <p>No gaps loaded.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
