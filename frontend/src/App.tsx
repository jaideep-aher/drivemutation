import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

const QUICK_FAMILIES = [
  "all",
  "cut_in",
  "rear_end",
  "pedestrian",
  "vru_crossing",
  "sensor_degradation",
  "lane_change",
];

const WEATHERS = ["all", "clear", "rain", "fog", "snow"];
const DIFFS = ["all", "easy", "medium", "hard", "unpreventable"];

type Navigate = (path: string) => void;

function labelFamily(f: string) {
  if (f === "all") return "All families";
  return f.replace(/_/g, " ");
}

function labelWeather(w: string) {
  if (w === "all") return "All weather";
  return w;
}

function labelDifficulty(d: string) {
  if (d === "all") return "All levels";
  return d;
}

function missing(value: string | number | null | undefined) {
  if (value == null || value === "") return "-";
  return String(value);
}

export default function App({ onNavigate }: { onNavigate?: Navigate } = {}) {
  const [health, setHealth] = useState<string>("...");
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
  const listRef = useRef<HTMLDivElement>(null);
  const selectedRef = useRef<HTMLButtonElement>(null);

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
        if (selectedId && rows.length && !rows.some((r) => r.id === selectedId)) {
          setSelectedId(rows[0].id);
        }
      })
      .catch((e) => setError(String(e)));
  }, [family, weather, difficulty, q, selectedId]);

  useEffect(() => {
    refreshList();
  }, [family, weather, difficulty]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const id = window.setTimeout(() => refreshList(), 220);
    return () => clearTimeout(id);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

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

  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedId]);

  const frame = frames[frameIdx] ?? null;

  const familyBars = useMemo(() => {
    if (!coverage) return [] as { k: string; n: number; pct: number }[];
    const entries = Object.entries(coverage.by_family).sort(
      (a, b) => (b[1] as number) - (a[1] as number)
    );
    const max = Math.max(...entries.map(([, n]) => n as number), 1);
    return entries.map(([k, n]) => ({ k, n: n as number, pct: (100 * (n as number)) / max }));
  }, [coverage]);

  const hasActiveFilters =
    family !== "all" || weather !== "all" || difficulty !== "all" || q.trim().length > 0;

  const clearFilters = () => {
    setFamily("all");
    setWeather("all");
    setDifficulty("all");
    setQ("");
  };

  const selectByOffset = (delta: number) => {
    if (!list.length) return;
    const idx = Math.max(
      0,
      list.findIndex((s) => s.id === selectedId)
    );
    const next = list[(idx + delta + list.length) % list.length];
    if (next) setSelectedId(next.id);
  };

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
            <section className="filters" aria-labelledby="filters-heading">
              <div className="filter-head">
                <h2 id="filters-heading">Filters</h2>
                {hasActiveFilters ? (
                  <button type="button" className="filter-clear" onClick={clearFilters}>
                    Clear all
                  </button>
                ) : (
                  <span className="filter-head-hint">Narrow the catalog</span>
                )}
              </div>

              <label className="filter-field">
                <span className="filter-label">Search</span>
                <input
                  className="filter-input"
                  placeholder="Search by name or id"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && refreshList()}
                  aria-label="Search scenarios"
                />
              </label>

              <div className="filter-block">
                <div className="filter-block-label">
                  <span className="filter-label">Family</span>
                  <span className="filter-block-hint">Quick picks</span>
                </div>
                <div className="family-rail" role="listbox" aria-label="Quick family filters">
                  {QUICK_FAMILIES.map((f) => (
                    <button
                      key={f}
                      type="button"
                      role="option"
                      aria-selected={family === f}
                      className={`family-chip ${family === f ? "active" : ""}`}
                      onClick={() => setFamily(f)}
                    >
                      {f === "all" ? "All" : f.replace(/_/g, " ")}
                    </button>
                  ))}
                </div>
                <label className="filter-field filter-field-flush">
                  <span className="visually-hidden">All families</span>
                  <select
                    className="filter-select"
                    value={family}
                    onChange={(e) => setFamily(e.target.value)}
                    aria-label="Scenario family"
                  >
                    {FAMILIES.map((f) => (
                      <option key={f} value={f}>
                        {labelFamily(f)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="filter-grid">
                <label className="filter-field">
                  <span className="filter-label">Weather</span>
                  <select
                    className="filter-select"
                    value={weather}
                    onChange={(e) => setWeather(e.target.value)}
                    aria-label="Weather"
                  >
                    {WEATHERS.map((w) => (
                      <option key={w} value={w}>
                        {labelWeather(w)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="filter-field">
                  <span className="filter-label">Difficulty</span>
                  <select
                    className="filter-select"
                    value={difficulty}
                    onChange={(e) => setDifficulty(e.target.value)}
                    aria-label="Difficulty"
                  >
                    {DIFFS.map((d) => (
                      <option key={d} value={d}>
                        {labelDifficulty(d)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {hasActiveFilters && (
                <div className="filter-active" aria-live="polite">
                  {q.trim() && (
                    <button type="button" className="filter-tag" onClick={() => setQ("")}>
                      Search: {q.trim()}
                      <span aria-hidden="true"> ×</span>
                    </button>
                  )}
                  {family !== "all" && (
                    <button type="button" className="filter-tag" onClick={() => setFamily("all")}>
                      {family.replace(/_/g, " ")}
                      <span aria-hidden="true"> ×</span>
                    </button>
                  )}
                  {weather !== "all" && (
                    <button type="button" className="filter-tag" onClick={() => setWeather("all")}>
                      {weather}
                      <span aria-hidden="true"> ×</span>
                    </button>
                  )}
                  {difficulty !== "all" && (
                    <button
                      type="button"
                      className="filter-tag"
                      onClick={() => setDifficulty("all")}
                    >
                      {difficulty}
                      <span aria-hidden="true"> ×</span>
                    </button>
                  )}
                </div>
              )}
            </section>

            <div className="scenario-list-head">
              <h2 id="scenario-list-heading">Scenarios</h2>
              <span className="filter-count">{list.length} shown</span>
            </div>

            <div
              className="scenario-list"
              ref={listRef}
              role="listbox"
              aria-labelledby="scenario-list-heading"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  selectByOffset(1);
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  selectByOffset(-1);
                } else if (e.key === "Home") {
                  e.preventDefault();
                  if (list[0]) setSelectedId(list[0].id);
                } else if (e.key === "End") {
                  e.preventDefault();
                  if (list.length) setSelectedId(list[list.length - 1].id);
                }
              }}
            >
              {list.map((s) => {
                const selected = selectedId === s.id;
                return (
                  <button
                    key={s.id}
                    ref={selected ? selectedRef : undefined}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    className={`scenario-row ${selected ? "selected" : ""}`}
                    onClick={() => setSelectedId(s.id)}
                  >
                    <span className="scenario-row-accent" aria-hidden="true" />
                    <span className="scenario-row-body">
                      <span className="row-top">
                        <span className="family">{s.family.replace(/_/g, " ")}</span>
                        <span className={`diff ${s.difficulty ?? ""}`}>
                          {missing(s.difficulty)}
                        </span>
                      </span>
                      <span className="row-name">{s.name}</span>
                      <span className="row-meta">
                        <span>
                          <span className="meta-dot" aria-hidden="true" />
                          {s.weather}
                        </span>
                        <span>
                          <span className="meta-dot" aria-hidden="true" />
                          {s.lighting}
                        </span>
                        {s.min_ttc_s != null && (
                          <span>
                            <span className="meta-dot" aria-hidden="true" />
                            TTC {s.min_ttc_s.toFixed(2)}s
                          </span>
                        )}
                      </span>
                    </span>
                  </button>
                );
              })}
              {list.length === 0 && (
                <p className="empty">No scenarios match these filters. Try clearing a filter.</p>
              )}
            </div>
          </aside>

          <section className="sf-stage">
            <div className="viewer-wrap">
              {loading && <div className="overlay">Rendering lidar...</div>}
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
                    or real ADS incident: never free-invented.
                  </p>
                </div>
                <div className="card metrics">
                  <h3>Criticality</h3>
                  <dl>
                    <dt>Difficulty</dt>
                    <dd>{missing(detail.difficulty)}</dd>
                    <dt>Min TTC</dt>
                    <dd>
                      {detail.metrics?.min_ttc_s != null
                        ? `${detail.metrics.min_ttc_s.toFixed(2)} s`
                        : "-"}
                    </dd>
                    <dt>Min distance</dt>
                    <dd>
                      {detail.metrics?.min_distance_m != null
                        ? `${detail.metrics.min_distance_m.toFixed(2)} m`
                        : "-"}
                    </dd>
                    <dt>Required decel</dt>
                    <dd>
                      {detail.metrics?.required_decel_mps2 != null
                        ? `${detail.metrics.required_decel_mps2.toFixed(2)} m/s²`
                        : "-"}
                    </dd>
                    <dt>Preventable (R157 model)</dt>
                    <dd>
                      {detail.metrics?.preventable == null
                        ? "-"
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
