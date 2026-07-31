import { useCallback, useEffect, useMemo, useState } from "react";
import {
  compileBase,
  compileFineTuned,
  fetchEvaluationSummary,
  fetchModelsStatus,
  fetchPreset,
  fetchPresets,
  simulateScenario,
} from "./api/client";
import { BirdEyeMap } from "./components/BirdEyeMap";
import { CompilePanel } from "./components/CompilePanel";
import { EvaluationPage } from "./components/EvaluationPage";
import { JsonDiff } from "./components/JsonDiff";
import { MetricsPanel } from "./components/MetricsPanel";
import { PlaybackControls } from "./components/PlaybackControls";
import { SceneEditor } from "./components/SceneEditor";
import { StatusBanner } from "./components/StatusBanner";
import type {
  CompileResponse,
  EvaluationSummary,
  ModelsStatus,
  PresetSummary,
  ScenarioSpec,
  SimulateResponse,
} from "./types/scenario";
import "./App.css";

type Page = "lab" | "eval";
type Busy = null | "simulate" | "base" | "fine-tuned" | "compare";

function readHashPage(): Page {
  const h = window.location.hash.replace(/^#\/?/, "");
  return h === "eval" ? "eval" : "lab";
}

function applyPlaybackSelection(
  compiled: CompileResponse,
  setResult: (r: SimulateResponse | null) => void,
  setFrameIndex: (n: number) => void,
  setPlaying: (b: boolean) => void,
) {
  if (compiled.simulation?.valid && compiled.ok && compiled.physical_valid) {
    setResult(compiled.simulation);
    setFrameIndex(0);
    setPlaying(true);
  } else if (compiled.simulation) {
    setResult(compiled.simulation);
    setFrameIndex(0);
    setPlaying(false);
  }
}

export default function App() {
  const [page, setPage] = useState<Page>(() => readHashPage());
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [scenario, setScenario] = useState<ScenarioSpec | null>(null);
  const [sceneText, setSceneText] = useState("");
  const [sceneError, setSceneError] = useState<string | null>(null);
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
    window.location.hash = p === "eval" ? "#/eval" : "#/lab";
    setPage(p);
  }, []);

  useEffect(() => {
    const onHash = () => setPage(readHashPage());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const refreshModels = useCallback(() => {
    fetchModelsStatus()
      .then(setModelStatus)
      .catch(() => setModelStatus(null));
  }, []);

  const refreshEval = useCallback(() => {
    setEvalLoading(true);
    setEvalError(null);
    fetchEvaluationSummary()
      .then(setEvalSummary)
      .catch((err: Error) => setEvalError(err.message))
      .finally(() => setEvalLoading(false));
  }, []);

  useEffect(() => {
    fetchPresets()
      .then((list) => {
        setPresets(list);
        if (list.length > 0) setSelectedId(list[0].id);
      })
      .catch((err: Error) => setError(err.message));
    refreshModels();
  }, [refreshModels]);

  useEffect(() => {
    if (page === "eval") refreshEval();
  }, [page, refreshEval]);

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
        setSceneText(JSON.stringify(sc, null, 2));
        setSceneError(null);
        const meta = presets.find((p) => p.id === selectedId);
        if (meta?.default_testing_goal) {
          setTestingGoal(meta.default_testing_goal);
        }
      })
      .catch((err: Error) => setError(err.message));
  }, [selectedId, presets]);

  const parseScene = useCallback((text: string): ScenarioSpec | null => {
    try {
      const obj = JSON.parse(text) as ScenarioSpec;
      setSceneError(null);
      setScenario(obj);
      return obj;
    } catch (err) {
      setSceneError(err instanceof Error ? err.message : String(err));
      return null;
    }
  }, []);

  const onSceneChange = (text: string) => {
    setSceneText(text);
    parseScene(text);
  };

  const runSimulation = useCallback(async () => {
    const sc = parseScene(sceneText);
    if (!sc) return;
    setBusy("simulate");
    setError(null);
    setPlaying(false);
    try {
      const sim = await simulateScenario(sc);
      setResult(sim);
      setFrameIndex(0);
      if (sim.valid) setPlaying(true);
      else setError("Simulation rejected — see validation issues.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }, [parseScene, sceneText]);

  const runCompile = useCallback(
    async (mode: "base" | "fine-tuned") => {
      const sc = parseScene(sceneText);
      if (!sc || !testingGoal.trim()) {
        setError("Valid scene JSON and a testing goal are required.");
        return;
      }
      setBusy(mode);
      setError(null);
      setPlaying(false);
      try {
        const compiled =
          mode === "base"
            ? await compileBase(sc, testingGoal.trim())
            : await compileFineTuned(sc, testingGoal.trim());
        if (mode === "base") setBaseCompile(compiled);
        else setFtCompile(compiled);
        applyPlaybackSelection(compiled, setResult, setFrameIndex, setPlaying);
        if (!compiled.ok && compiled.error_code) {
          setError(`${compiled.error_code}: ${compiled.error ?? "compile failed"}`);
        }
        refreshModels();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(null);
      }
    },
    [parseScene, sceneText, testingGoal, refreshModels],
  );

  const runCompare = useCallback(async () => {
    const sc = parseScene(sceneText);
    if (!sc || !testingGoal.trim()) {
      setError("Valid scene JSON and a testing goal are required.");
      return;
    }
    setBusy("compare");
    setError(null);
    setPlaying(false);
    try {
      const base = await compileBase(sc, testingGoal.trim());
      setBaseCompile(base);
      let ft: CompileResponse | null = null;
      try {
        ft = await compileFineTuned(sc, testingGoal.trim());
        setFtCompile(ft);
      } catch (err) {
        setFtCompile(null);
        setError(
          `Fine-tuned compile failed: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
      const preferred =
        ft && ft.ok && ft.physical_valid
          ? ft
          : base.ok && base.physical_valid
            ? base
            : ft ?? base;
      applyPlaybackSelection(preferred, setResult, setFrameIndex, setPlaying);
      refreshModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }, [parseScene, sceneText, testingGoal, refreshModels]);

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
      if (page !== "lab") return;
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
          result?.frames.length
            ? Math.min(result.frames.length - 1, i + 1)
            : i,
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

  const loading = busy !== null;
  const selectedMeta = presets.find((p) => p.id === selectedId);

  return (
    <div className="app">
      <header className="hero">
        <div className="hero-top">
          <div>
            <div className="brand">DriveMutation</div>
            <p className="tagline">
              Local counterfactual AV test compiler — base versus fine-tuned stress
              mutations. Not a vehicle controller. Not a safety proof.
            </p>
          </div>
          <nav className="nav" aria-label="Primary">
            <button
              type="button"
              className={page === "lab" ? "nav-active" : ""}
              onClick={() => navigate("lab")}
              data-testid="nav-lab"
            >
              Lab
            </button>
            <button
              type="button"
              className={page === "eval" ? "nav-active" : ""}
              onClick={() => navigate("eval")}
              data-testid="nav-eval"
            >
              Evaluation
            </button>
          </nav>
        </div>
        {modelStatus && (
          <p className="model-status" data-testid="model-status">
            Base {modelStatus.base_model}
            {" · "}
            FT{" "}
            {modelStatus.fine_tuned_model ??
              (modelStatus.job_pending
                ? `pending (${modelStatus.fine_tuning_status})`
                : modelStatus.job_failed
                  ? "failed"
                  : "not configured")}
            {" · "}
            API {modelStatus.api_key_configured ? "configured" : "missing"}
          </p>
        )}
      </header>

      {page === "eval" ? (
        <EvaluationPage
          summary={evalSummary}
          loading={evalLoading}
          error={evalError}
          onRefresh={refreshEval}
        />
      ) : (
        <main className="stage">
          <section className="controls-bar">
            <label>
              Seed scenario
              <select
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                data-testid="scenario-select"
              >
                {presets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.kind === "impossible" ? `⚠ ${p.name}` : p.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="primary"
              onClick={runSimulation}
              disabled={!scenario || loading || !!sceneError}
              data-testid="run-simulate"
            >
              {busy === "simulate" ? "Simulating…" : "Simulate seed"}
            </button>
            <button
              type="button"
              onClick={() => runCompile("base")}
              disabled={!scenario || loading || !!sceneError}
              data-testid="compile-base"
            >
              {busy === "base" ? "Running base…" : "Run base"}
            </button>
            <button
              type="button"
              onClick={() => runCompile("fine-tuned")}
              disabled={
                !scenario ||
                loading ||
                !!sceneError ||
                modelStatus?.job_pending === true
              }
              data-testid="compile-finetuned"
            >
              {busy === "fine-tuned" ? "Running FT…" : "Run fine-tuned"}
            </button>
            <button
              type="button"
              className="accent"
              onClick={runCompare}
              disabled={!scenario || loading || !!sceneError}
              data-testid="compare-both"
            >
              {busy === "compare" ? "Comparing…" : "Compare both"}
            </button>
          </section>

          {selectedMeta && (
            <p className="scenario-desc" data-testid="scenario-description">
              {selectedMeta.description}
            </p>
          )}

          <label className="goal-field">
            Natural-language stress-testing goal
            <textarea
              value={testingGoal}
              onChange={(e) => setTestingGoal(e.target.value)}
              rows={3}
              data-testid="testing-goal"
            />
          </label>

          {modelStatus?.job_pending && (
            <StatusBanner
              code="fine_tuning_pending"
              message={`Fine-tuning job ${modelStatus.fine_tuning_status ?? "pending"}`}
            />
          )}
          {modelStatus?.job_failed && (
            <StatusBanner
              code="fine_tuning_failed"
              message={modelStatus.fine_tuning_error ?? "Fine-tuning failed"}
            />
          )}
          {modelStatus &&
            !modelStatus.api_key_configured &&
            !modelStatus.fine_tuned_model && (
              <StatusBanner
                code="missing_api_key"
                message="OPENAI_API_KEY not configured — compile endpoints will fail."
              />
            )}
          {error && (
            <div className="status-banner tone-error" role="alert" data-testid="error-banner">
              {error}
            </div>
          )}

          <div className="lab-grid">
            <SceneEditor
              value={sceneText}
              onChange={onSceneChange}
              parseError={sceneError}
            />
            <div className="compare-col">
              <div className="compare-row">
                <CompilePanel
                  title="Base"
                  result={baseCompile}
                  loading={busy === "base" || busy === "compare"}
                />
                <CompilePanel
                  title="Fine-tuned"
                  result={ftCompile}
                  loading={busy === "fine-tuned" || busy === "compare"}
                />
              </div>
              <section className="diff-section">
                <h3>Structured JSON diff</h3>
                <JsonDiff
                  left={baseCompile?.parsed ?? null}
                  right={ftCompile?.parsed ?? null}
                />
              </section>
            </div>
          </div>

          <div className="workspace">
            <div className="viz">
              {scenario ? (
                <BirdEyeMap
                  road={scenario.road}
                  frame={frame}
                  trajectories={result?.trajectories ?? {}}
                />
              ) : (
                <div className="placeholder">Select a scenario</div>
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
              <p className="kbd-hint">
                Keyboard: Space play/pause · ←/→ scrub · R restart
              </p>
            </div>
            <MetricsPanel
              result={result}
              egoSpeed={frame?.ego_speed ?? null}
              frameMinTtc={frame?.min_ttc ?? null}
            />
          </div>
        </main>
      )}
    </div>
  );
}
