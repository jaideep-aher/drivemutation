import type { SimulateResponse } from "../types/scenario";

interface MetricsPanelProps {
  result: SimulateResponse | null;
  egoSpeed: number | null;
  frameMinTtc: number | null;
}

export function MetricsPanel({ result, egoSpeed, frameMinTtc }: MetricsPanelProps) {
  const metrics = result?.metrics;
  return (
    <aside className="metrics" data-testid="metrics-panel">
      <h2>Metrics</h2>
      {!result && <p className="muted">Run a scenario to see results.</p>}
      {result && !result.valid && (
        <div className="errors" data-testid="validation-errors">
          <h3>Validation errors</h3>
          <ul>
            {result.validation_issues.map((issue) => (
              <li key={`${issue.code}-${issue.message}`}>
                <code>{issue.code}</code>: {issue.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {metrics && (
        <>
          <dl>
            <div>
              <dt>Ego speed</dt>
              <dd>{egoSpeed != null ? `${egoSpeed.toFixed(2)} m/s` : " - "}</dd>
            </div>
            <div>
              <dt>Min TTC (frame)</dt>
              <dd>{frameMinTtc != null ? `${frameMinTtc.toFixed(2)} s` : " - "}</dd>
            </div>
            <div>
              <dt>Min TTC (run)</dt>
              <dd>{metrics.min_ttc != null ? `${metrics.min_ttc.toFixed(2)} s` : " - "}</dd>
            </div>
            <div>
              <dt>Collisions</dt>
              <dd>{metrics.collision_count}</dd>
            </div>
            <div>
              <dt>Max |a|</dt>
              <dd>{metrics.max_acceleration.toFixed(2)} m/s²</dd>
            </div>
            <div>
              <dt>Max |jerk|</dt>
              <dd>{metrics.max_jerk.toFixed(2)} m/s³</dd>
            </div>
          </dl>
          <h3>Oracles</h3>
          <ul className="oracles" data-testid="oracle-results">
            {metrics.oracle_results.map((o) => (
              <li key={o.id} className={o.passed ? "pass" : "fail"}>
                <strong>{o.passed ? "PASS" : "FAIL"}</strong> {o.id}{" "}
                <span className="muted">({o.type})</span>
                <div className="muted">{o.message}</div>
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  );
}
