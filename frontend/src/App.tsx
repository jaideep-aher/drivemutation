import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api/client";
import { PointCloudViewer } from "./components/PointCloudViewer";
import type {
  ConcreteScenario,
  CoverageStats,
  GapItem,
  OddCoverage,
  PointCloudFrame,
  ScenarioSummary,
} from "./types/signalforge";

const WEATHERS = ["all", "clear", "rain", "fog", "snow"];
const LIGHTINGS = ["all", "day", "dusk", "night", "dawn"];
const DIFFS = ["all", "easy", "medium", "hard", "unpreventable"];

/** Scenarios fetched per request. The catalog holds thousands, so the list
 *  pages as you scroll instead of truncating at a fixed cap. */
const PAGE_SIZE = 60;

const prettify = (value: string) => value.replace(/_/g, " ");

type Navigate = (path: string) => void;

interface Filters {
  family: string;
  weather: string;
  lighting: string;
  difficulty: string;
  q: string;
}

const DEFAULT_FILTERS: Filters = {
  family: "all",
  weather: "all",
  lighting: "all",
  difficulty: "all",
  q: "",
};

export default function App({ onNavigate }: { onNavigate?: Navigate } = {}) {
  const [health, setHealth] = useState<string>("…");
  const [list, setList] = useState<ScenarioSummary[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConcreteScenario | null>(null);
  const [frames, setFrames] = useState<PointCloudFrame[]>([]);
  const [frameIdx, setFrameIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [coverage, setCoverage] = useState<CoverageStats | null>(null);
  const [oddCoverage, setOddCoverage] = useState<OddCoverage | null>(null);
  const [gaps, setGaps] = useState<GapItem[]>([]);
  const [showRadar, setShowRadar] = useState(true);
  const [tab, setTab] = useState<"viewer" | "coverage" | "gaps">("viewer");

  // `filters` drives the request; `queryInput` is what the user is typing, and
  // is debounced into it so results update as you type without a request per
  // keystroke.
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [queryInput, setQueryInput] = useState("");

  const listRef = useRef<HTMLDivElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api
      .health()
      .then((h) =>
        setHealth(
          `${h.concrete_count.toLocaleString()} scenarios · ${h.logical_count} logical · v${h.version}`
        )
      )
      .catch(() => setHealth("API offline"));
    api.coverage().then(setCoverage).catch(() => undefined);
    api.oddCoverage().then(setOddCoverage).catch(() => undefined);
    api.gaps().then(setGaps).catch(() => undefined);
  }, []);

  // Debounce the search box into the active filters.
  useEffect(() => {
    const handle = window.setTimeout(() => {
      setFilters((f) => (f.q === queryInput ? f : { ...f, q: queryInput }));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [queryInput]);

  // First page whenever the filters change. Aborting in-flight requests keeps a
  // fast typist from seeing results for a query they have already moved past.
  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true);
    setError(null);

    Promise.all([
      api.scenarios({ ...filters, limit: PAGE_SIZE, offset: 0 }, controller.signal),
      api.scenarioCount(filters, controller.signal),
    ])
      .then(([rows, { count }]) => {
        setList(rows);
        setTotal(count);
        if (listRef.current) listRef.current.scrollTop = 0;
        // Keep the current selection only if it survived the filter change.
        setSelectedId((current) => {
          if (current && rows.some((r) => r.id === current)) return current;
          return rows.length ? rows[0].id : null;
        });
      })
      .catch((e) => {
        if ((e as Error).name !== "AbortError") setError(String(e));
      })
      .finally(() => setListLoading(false));

    return () => controller.abort();
  }, [filters]);

  const hasMore = total !== null && list.length < total;

  const loadMore = useCallback(() => {
    if (loadingMore || listLoading || !hasMore) return;
    setLoadingMore(true);
    api
      .scenarios({ ...filters, limit: PAGE_SIZE, offset: list.length })
      .then((rows) => {
        setList((prev) => {
          // Guard against a late response duplicating rows.
          const seen = new Set(prev.map((r) => r.id));
          return [...prev, ...rows.filter((r) => !seen.has(r.id))];
        });
      })
      .catch(() => undefined)
      .finally(() => setLoadingMore(false));
  }, [filters, hasMore, list.length, listLoading, loadingMore]);

  // Infinite scroll: fetch the next page when the sentinel nears the viewport.
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadMore();
      },
      { root: listRef.current, rootMargin: "320px" }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

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
    else setDetail(null);
  }, [selectedId, loadScenario]);

  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const id = window.setInterval(() => {
      setFrameIdx((i) => (i + 1) % frames.length);
    }, 180);
    return () => clearInterval(id);
  }, [playing, frames.length]);

  // Arrow keys move through the list; space toggles playback.
  const onListKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const index = list.findIndex((s) => s.id === selectedId);
    const next = event.key === "ArrowDown" ? index + 1 : index - 1;
    if (next < 0 || next >= list.length) {
      if (next >= list.length) loadMore();
      return;
    }
    setSelectedId(list[next].id);
    // Optional call: not every environment implements scrollIntoView, and
    // keyboard selection should still work where it is missing.
    document
      .getElementById(`scenario-${list[next].id}`)
      ?.scrollIntoView?.({ block: "nearest" });
  };

  const setFilter = (key: keyof Filters, value: string) =>
    setFilters((f) => ({ ...f, [key]: value }));

  const resetFilters = () => {
    setQueryInput("");
    setFilters(DEFAULT_FILTERS);
  };

  const filtersActive =
    filters.family !== "all" ||
    filters.weather !== "all" ||
    filters.lighting !== "all" ||
    filters.difficulty !== "all" ||
    filters.q !== "";

  // Built from the live coverage response so new catalog families appear
  // automatically instead of being unreachable behind a hardcoded list.
  const familyOptions = useMemo(() => {
    if (!coverage) return ["all"];
    const names = Object.keys(coverage.by_family).sort();
    return ["all", ...names];
  }, [coverage]);

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
            Auditable AV scenarios · OpenSCENARIO export · traced to NHTSA / R157 / Euro NCAP /
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
              <div className="search-wrap">
                <input
                  className="search-input"
                  placeholder="Search name or id…"
                  value={queryInput}
                  aria-label="Search scenarios"
                  onChange={(e) => setQueryInput(e.target.value)}
                />
                {queryInput && (
                  <button
                    type="button"
                    className="search-clear"
                    aria-label="Clear search"
                    onClick={() => setQueryInput("")}
                  >
                    ×
                  </button>
                )}
              </div>
              <div className="filter-grid">
                <label>
                  <span>Family</span>
                  <select
                    value={filters.family}
                    onChange={(e) => setFilter("family", e.target.value)}
                  >
                    {familyOptions.map((f) => (
                      <option key={f} value={f}>
                        {prettify(f)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Difficulty</span>
                  <select
                    value={filters.difficulty}
                    onChange={(e) => setFilter("difficulty", e.target.value)}
                  >
                    {DIFFS.map((d) => (
                      <option key={d} value={d}>
                        {prettify(d)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Weather</span>
                  <select
                    value={filters.weather}
                    onChange={(e) => setFilter("weather", e.target.value)}
                  >
                    {WEATHERS.map((w) => (
                      <option key={w} value={w}>
                        {w}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Lighting</span>
                  <select
                    value={filters.lighting}
                    onChange={(e) => setFilter("lighting", e.target.value)}
                  >
                    {LIGHTINGS.map((l) => (
                      <option key={l} value={l}>
                        {l}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="filter-status">
                <span>
                  {listLoading
                    ? "Searching…"
                    : total === null
                      ? "—"
                      : `${list.length.toLocaleString()} of ${total.toLocaleString()}`}
                </span>
                {filtersActive && (
                  <button type="button" className="reset-btn" onClick={resetFilters}>
                    Reset
                  </button>
                )}
              </div>
            </div>

            <div
              className="scenario-list"
              ref={listRef}
              tabIndex={0}
              role="listbox"
              aria-label="Scenarios"
              aria-busy={listLoading}
              onKeyDown={onListKeyDown}
            >
              {listLoading && list.length === 0 && (
                <div className="list-skeleton">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="skeleton-row" />
                  ))}
                </div>
              )}

              {list.map((s) => (
                <button
                  key={s.id}
                  id={`scenario-${s.id}`}
                  role="option"
                  aria-selected={selectedId === s.id}
                  className={`scenario-row ${selectedId === s.id ? "selected" : ""}`}
                  onClick={() => setSelectedId(s.id)}
                >
                  <div className="row-top">
                    <span className="family">{prettify(s.family)}</span>
                    <span className={`diff ${s.difficulty ?? ""}`}>{s.difficulty ?? "—"}</span>
                  </div>
                  <div className="row-name">{s.name}</div>
                  <div className="row-meta">
                    {s.weather} · {s.lighting}
                    {s.min_ttc_s != null ? ` · TTC ${s.min_ttc_s.toFixed(2)}s` : ""}
                    {s.collision ? " · collision" : ""}
                  </div>
                </button>
              ))}

              {!listLoading && list.length === 0 && (
                <div className="empty">
                  <p>No scenarios match these filters.</p>
                  {filtersActive && (
                    <button type="button" className="reset-btn" onClick={resetFilters}>
                      Reset filters
                    </button>
                  )}
                </div>
              )}

              {hasMore && (
                <div ref={sentinelRef} className="list-sentinel">
                  {loadingMore ? "Loading more…" : `${(total ?? 0) - list.length} more`}
                </div>
              )}
            </div>
          </aside>

          <section className="sf-stage">
            <div className="viewer-wrap">
              {loading && <div className="overlay">Rendering lidar…</div>}
              {error && <div className="overlay error">{error}</div>}
              <PointCloudViewer frame={frame} showRadar={showRadar} />
            </div>

            <div className="playback">
              <button
                className="play-btn"
                onClick={() => setPlaying((p) => !p)}
                disabled={!frames.length}
              >
                {playing ? "❚❚ Pause" : "▶ Play"}
              </button>
              <input
                type="range"
                aria-label="Frame"
                min={0}
                max={Math.max(frames.length - 1, 0)}
                value={frameIdx}
                onChange={(e) => {
                  setPlaying(false);
                  setFrameIdx(Number(e.target.value));
                }}
              />
              <span className="frame-label">
                {frames.length ? `frame ${frameIdx + 1}/${frames.length}` : "no frames"}
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
              {detail && (
                <a
                  className="download-btn"
                  href={api.openscenarioUrl(detail.id)}
                  download
                  title="Download .xosc + .xodr, runnable in esmini"
                >
                  ↓ OpenSCENARIO
                </a>
              )}
            </div>

            {detail && (
              <div className="detail-grid">
                <div className="card provenance">
                  <h3>Provenance</h3>
                  <dl>
                    <dt>Source</dt>
                    <dd>{prettify(detail.provenance.source)}</dd>
                    <dt>Citation</dt>
                    <dd>{detail.provenance.citation}</dd>
                    <dt>Parent logical</dt>
                    <dd>{detail.provenance.parent_id ?? detail.logical_id}</dd>
                    <dt>Seed</dt>
                    <dd>{detail.provenance.seed}</dd>
                  </dl>
                  {detail.provenance.notes && (
                    <p className="hint">{detail.provenance.notes}</p>
                  )}
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
                    <dd>{prettify(detail.road_geometry)}</dd>
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
              <div className="n">{coverage.total_concrete.toLocaleString()}</div>
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

          {oddCoverage && (
            <div className="odd-coverage">
              <h3>Pairwise ODD coverage</h3>
              <div className="coverage-headline">
                <span className={oddCoverage.complete ? "pct ok" : "pct warn"}>
                  {oddCoverage.coverage_pct.toFixed(1)}%
                </span>
                <span className="coverage-detail">
                  of {oddCoverage.reachable_tuples.toLocaleString()} reachable{" "}
                  {oddCoverage.strength}-way combinations
                  {oddCoverage.unreachable_tuples > 0
                    ? ` · ${oddCoverage.unreachable_tuples} ruled out by physical constraints`
                    : ""}
                </span>
              </div>
              <p className="hint">
                Every pair of ODD values that is physically reachable appears in at least one
                scenario. Combinations that constraints rule out — an icy surface under clear skies
                — are reported as unreachable rather than counted as covered.
              </p>
            </div>
          )}

          <h3>By family</h3>
          <div className="bars">
            {familyBars.map(({ k, n, pct }) => (
              <div key={k} className="bar-row">
                <span className="bar-label">{prettify(k)}</span>
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
