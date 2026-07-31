import { useCallback, useEffect, useMemo, useState } from "react";
import {
  compileBase,
  compileFineTuned,
  fetchEvaluationSummary,
  fetchModelsStatus,
  fetchPreset,
  fetchPresets,
} from "./api/client";
import { BirdEyeMap } from "./components/BirdEyeMap";
import { EvaluationPage } from "./components/EvaluationPage";
import { PlaybackControls } from "./components/PlaybackControls";
import type {
  CompileResponse,
  EvaluationSummary,
  ModelsStatus,
  PresetSummary,
  ScenarioSpec,
  SimulateResponse,
} from "./types/scenario";
import "./App.css";

type Page = "home" | "demo" | "scores";
type Busy = null | "compare";

function readHashPage(): Page {
  const h = window.location.hash.replace(/^#\/?/, "");
  if (h === "demo" || h === "lab") return "demo";
  if (h === "scores" || h === "eval") return "scores";
  return "home";
}

function verdict(c: CompileResponse | null): "win" | "lose" | "idle" {
  if (!c) return "idle";
  if (c.ok && (c.physical_valid || c.target_kind === "rejection")) return "win";
  return "lose";
}

function verdictLabel(c: CompileResponse | null): string {
  if (!c) return "Waiting";
  if (c.ok && c.target_kind === "rejection") return "Correctly rejected";
  if (c.ok && c.physical_valid) return "Worked";
  if (c.json_parse_ok && !c.schema_valid) return "Wrong JSON shape";
  return c.error_code ?? "Failed";
}

export default function App() {
  const [page, setPage] = useState<Page>(() => readHashPage());
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [scenario, setScenario] = useState<ScenarioSpec | null>(null);
  const [testingGoal, setTestingGoal] = useState("");
  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [baseCompile, setBaseCompile] = useState<CompileResponse | null>(null);
  const [ftCompile, setFtCompile] = useState<CompileResponse | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelsStatus | null>(null);
  const [evalSummary, setEvalSummary] = useState<EvaluationSummary | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  const navigate = useCallback((p: Page) => {
    const hash = p === "home" ? "#/" : p === "demo" ? "#/demo" : "#/scores";
    window.location.hash = hash;
    setPage(p);
  }, []);

  useEffect(() => {
    const onHash = () => setPage(readHashPage());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    fetchPresets()
      .then((list) => {
        setPresets(list);
        if (list.length > 0) setSelectedId(list[0].id);
      })
      .catch((err: Error) => setError(err.message));
    fetchModelsStatus()
      .then(setModelStatus)
      .catch(() => setModelStatus(null));
  }, []);

  useEffect(() => {
    if (page === "scores") {
      setEvalLoading(true);
      setEvalError(null);
      fetchEvaluationSummary()
        .then(setEvalSummary)
        .catch((err: Error) => setEvalError(err.message))
        .finally(() => setEvalLoading(false));
    }
  }, [page]);

  useEffect(() => {
    if (!selectedId) return;
    setPlaying(false);
    setResult(null);
    setBaseCompile(null);
    setFtCompile(null);
    setFrameIndex(0);
    setError(null);
    fetchPreset(selectedId)
      .then((sc) => {
        setScenario(sc);
        const meta = presets.find((p) => p.id === selectedId);
        if (meta?.default_testing_goal) setTestingGoal(meta.default_testing_goal);
      })
      .catch((err: Error) => setError(err.message));
  }, [selectedId, presets]);

  const runCompare = useCallback(async () => {
    if (!scenario || !testingGoal.trim()) {
      setError("Pick a scenario and write a goal first.");
      return;
    }
    setBusy("compare");
    setError(null);
    setPlaying(false);
    setResult(null);
    setBaseCompile(null);
    setFtCompile(null);
    try {
      const base = await compileBase(scenario, testingGoal.trim());
      setBaseCompile(base);
      let ft: CompileResponse | null = null;
      try {
        ft = await compileFineTuned(scenario, testingGoal.trim());
        setFtCompile(ft);
      } catch (err) {
        setError(
          `Fine-tuned call failed: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
      const preferred =
        ft && ft.ok && ft.physical_valid
          ? ft
          : base.ok && base.physical_valid
            ? base
            : ft ?? base;
      if (preferred?.simulation?.valid) {
        setResult(preferred.simulation);
        setFrameIndex(0);
        setPlaying(true);
      } else if (preferred?.simulation) {
        setResult(preferred.simulation);
        setFrameIndex(0);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }, [scenario, testingGoal]);

  useEffect(() => {
    if (!playing || !result?.frames.length) return;
    const id = window.setInterval(() => {
      setFrameIndex((i) => {
        if (i >= result.frames.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 100);
    return () => window.clearInterval(id);
  }, [playing, result]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (page !== "demo") return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") return;
      if (e.code === "Space") {
        e.preventDefault();
        if (!result?.valid) return;
        setPlaying((p) => !p);
      } else if (e.code === "ArrowLeft") {
        e.preventDefault();
        setPlaying(false);
        setFrameIndex((i) => Math.max(0, i - 1));
      } else if (e.code === "ArrowRight") {
        e.preventDefault();
        setPlaying(false);
        setFrameIndex((i) =>
          result?.frames.length ? Math.min(result.frames.length - 1, i + 1) : i,
        );
      } else if (e.code === "KeyR") {
        e.preventDefault();
        setFrameIndex(0);
        if (result?.valid) setPlaying(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [page, result]);

  const frame = useMemo(() => {
    if (!result?.frames.length) return null;
    return result.frames[Math.min(frameIndex, result.frames.length - 1)] ?? null;
  }, [result, frameIndex]);

  const metrics = result?.metrics;
  const selectedMeta = presets.find((p) => p.id === selectedId);

  return (
    <div className="app">
      <header className="topbar">
        <button type="button" className="brand-link" onClick={() => navigate("home")}>
          DriveMutation
        </button>
        <nav className="nav" aria-label="Primary">
          <button
            type="button"
            className={page === "home" ? "nav-active" : ""}
            onClick={() => navigate("home")}
            data-testid="nav-home"
          >
            Home
          </button>
          <button
            type="button"
            className={page === "demo" ? "nav-active" : ""}
            onClick={() => navigate("demo")}
            data-testid="nav-lab"
          >
            Demo
          </button>
          <button
            type="button"
            className={page === "scores" ? "nav-active" : ""}
            onClick={() => navigate("scores")}
            data-testid="nav-eval"
          >
            Scores
          </button>
        </nav>
      </header>

      {page === "home" && (
        <section className="home" data-testid="home-page">
          <p className="home-kicker">AIPI hackathon demo</p>
          <h1 className="home-title">DriveMutation</h1>
          <p className="home-lead">
            We taught an AI to write dangerous driving test scenarios from plain English.
          </p>
          <div className="home-steps">
            <div>
              <strong>1. You type a goal</strong>
              <span>like &quot;occluded pedestrian pops out&quot;</span>
            </div>
            <div>
              <strong>2. Two models answer</strong>
              <span>stock GPT vs our fine-tuned model</span>
            </div>
            <div>
              <strong>3. Only valid JSON runs</strong>
              <span>then you watch the crash / near-miss on a map</span>
            </div>
          </div>
          <p className="home-note">
            Stock GPT usually invents the wrong JSON. The fine-tuned model learned our schema.
            Not a real car. Not a safety certificate.
          </p>
          <button
            type="button"
            className="home-cta"
            onClick={() => navigate("demo")}
            data-testid="home-cta"
          >
            Open the demo
          </button>
          {modelStatus?.api_key_configured && (
            <p className="home-status" data-testid="model-status">
              OpenAI connected
              {modelStatus.fine_tuned_ready ? " · fine-tuned model ready" : ""}
            </p>
          )}
        </section>
      )}

      {page === "scores" && (
        <EvaluationPage
          summary={evalSummary}
          loading={evalLoading}
          error={evalError}
          onRefresh={() => {
            setEvalLoading(true);
            fetchEvaluationSummary()
              .then(setEvalSummary)
              .catch((err: Error) => setEvalError(err.message))
              .finally(() => setEvalLoading(false));
          }}
        />
      )}

      {page === "demo" && (
        <main className="demo" data-testid="demo-page">
          <section className="demo-controls">
            <label>
              Scenario
              <select
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                data-testid="scenario-select"
              >
                {presets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.kind === "impossible" ? `! ${p.name}` : p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="goal-field">
              What should go wrong?
              <textarea
                value={testingGoal}
                onChange={(e) => setTestingGoal(e.target.value)}
                rows={2}
                data-testid="testing-goal"
              />
            </label>
            <button
              type="button"
              className="home-cta demo-run"
              onClick={runCompare}
              disabled={!scenario || busy !== null}
              data-testid="compare-both"
            >
              {busy === "compare" ? "Calling OpenAI..." : "Run comparison"}
            </button>
            {selectedMeta && (
              <p className="scenario-desc" data-testid="scenario-description">
                {selectedMeta.description}
              </p>
            )}
            {error && (
              <div className="status-banner tone-error" role="alert" data-testid="error-banner">
                {error}
              </div>
            )}
          </section>

          <section className="stage-visual" data-testid="visual-stage">
            <div className="viz big-viz">
              {scenario ? (
                <BirdEyeMap
                  road={scenario.road}
                  frame={frame}
                  trajectories={result?.trajectories ?? {}}
                  height={420}
                />
              ) : (
                <div className="placeholder">Loading scenario...</div>
              )}
              <PlaybackControls
                playing={playing}
                frameIndex={frameIndex}
                frameCount={result?.frames.length ?? 0}
                onPlay={() => result?.valid && setPlaying(true)}
                onPause={() => setPlaying(false)}
                onRestart={() => {
                  setFrameIndex(0);
                  setPlaying(Boolean(result?.valid));
                }}
                onScrub={(i) => {
                  setPlaying(false);
                  setFrameIndex(i);
                }}
              />
            </div>

            <div className="result-hero" data-testid="result-hero">
              <div className="score-cards">
                <article className={`score-card ${verdict(baseCompile)}`}>
                  <h3>Stock GPT</h3>
                  <p className="score-big" data-testid="compile-panel-stock-gpt-(base)">
                    {busy === "compare" && !baseCompile
                      ? "..."
                      : verdictLabel(baseCompile)}
                  </p>
                </article>
                <article className={`score-card ${verdict(ftCompile)}`}>
                  <h3>Fine-tuned</h3>
                  <p className="score-big" data-testid="compile-panel-fine-tuned">
                    {busy === "compare" && !ftCompile
                      ? "..."
                      : verdictLabel(ftCompile)}
                  </p>
                </article>
              </div>

              <div className="metric-hero" data-testid="metrics-panel">
                <div>
                  <span className="metric-label">Collisions</span>
                  <strong className="metric-value">
                    {metrics ? metrics.collision_count : "-"}
                  </strong>
                </div>
                <div>
                  <span className="metric-label">Min TTC</span>
                  <strong className="metric-value">
                    {metrics?.min_ttc != null ? `${metrics.min_ttc.toFixed(1)}s` : "-"}
                  </strong>
                </div>
                <div>
                  <span className="metric-label">Speed</span>
                  <strong className="metric-value">
                    {frame?.ego_speed != null ? `${frame.ego_speed.toFixed(0)}` : "-"}
                    <small> m/s</small>
                  </strong>
                </div>
              </div>

              {metrics && (
                <ul className="oracle-row" data-testid="oracle-results">
                  {metrics.oracle_results.map((o) => (
                    <li key={o.id} className={o.passed ? "pass" : "fail"}>
                      {o.passed ? "PASS" : "FAIL"} {o.type.replace(/_/g, " ")}
                    </li>
                  ))}
                </ul>
              )}

              {!result && busy === null && (
                <p className="muted center-hint">
                  Hit Run comparison. The map and numbers show up here.
                </p>
              )}
            </div>
          </section>
        </main>
      )}
    </div>
  );
}
