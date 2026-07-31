import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchPreset, fetchPresets, simulateScenario } from "./api/client";
import { BirdEyeMap } from "./components/BirdEyeMap";
import { MetricsPanel } from "./components/MetricsPanel";
import { PlaybackControls } from "./components/PlaybackControls";
import type { PresetSummary, ScenarioSpec, SimulateResponse } from "./types/scenario";
import "./App.css";

export default function App() {
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [scenario, setScenario] = useState<ScenarioSpec | null>(null);
  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchPresets()
      .then((list) => {
        setPresets(list);
        if (list.length > 0) setSelectedId(list[0].id);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setPlaying(false);
    setResult(null);
    setFrameIndex(0);
    setError(null);
    fetchPreset(selectedId)
      .then(setScenario)
      .catch((err: Error) => setError(err.message));
  }, [selectedId]);

  const runSimulation = useCallback(async () => {
    if (!scenario) return;
    setLoading(true);
    setError(null);
    setPlaying(false);
    try {
      const sim = await simulateScenario(scenario);
      setResult(sim);
      setFrameIndex(0);
      if (sim.valid) setPlaying(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [scenario]);

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

  const frame = useMemo(() => {
    if (!result?.frames.length) return null;
    return result.frames[Math.min(frameIndex, result.frames.length - 1)] ?? null;
  }, [result, frameIndex]);

  return (
    <div className="app">
      <header className="hero">
        <div className="brand">DriveMutation</div>
        <p className="tagline">
          Local counterfactual AV test compiler — Stage 1 deterministic simulator
        </p>
      </header>

      <main className="stage">
        <section className="controls-bar">
          <label>
            Scenario
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              data-testid="scenario-select"
            >
              {presets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="primary"
            onClick={runSimulation}
            disabled={!scenario || loading}
            data-testid="run-simulate"
          >
            {loading ? "Simulating…" : "Simulate"}
          </button>
        </section>

        {scenario && (
          <p className="scenario-desc" data-testid="scenario-description">
            {scenario.description}
          </p>
        )}

        {error && (
          <div className="banner error" role="alert">
            {error}
          </div>
        )}

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
          </div>
          <MetricsPanel
            result={result}
            egoSpeed={frame?.ego_speed ?? null}
            frameMinTtc={frame?.min_ttc ?? null}
          />
        </div>
      </main>
    </div>
  );
}
