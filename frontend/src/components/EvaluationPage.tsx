import type { EvaluationSummary } from "../types/scenario";

interface EvaluationPageProps {
  summary: EvaluationSummary | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

const METRIC_KEYS = [
  ["json_parse_rate", "JSON parse"],
  ["schema_valid_rate", "Schema valid"],
  ["physical_validity_rate", "Physical validity"],
  ["scenario_family_accuracy", "Scenario family"],
  ["hazard_activation_rate", "Hazard activation"],
  ["oracle_correctness", "Oracle correctness"],
  ["impossible_request_rejection_accuracy", "Rejection accuracy"],
] as const;

function fmtRate(v: unknown): string {
  if (typeof v !== "number" || Number.isNaN(v)) return " - ";
  return `${(v * 100).toFixed(1)}%`;
}

function fmtLatency(metrics: Record<string, unknown> | undefined): string {
  const lat = metrics?.latency as { mean_s?: number } | undefined;
  if (!lat || lat.mean_s == null) return " - ";
  return `${lat.mean_s.toFixed(2)} s`;
}

export function EvaluationPage({
  summary,
  loading,
  error,
  onRefresh,
}: EvaluationPageProps) {
  return (
    <div className="eval-page" data-testid="evaluation-page">
      <header className="eval-header">
        <div>
          <h2>Measured evaluation</h2>
          <p className="muted">
            Only real measurements from offline evaluation artifacts. Missing files
            show as unavailable  -  never as invented scores.
          </p>
        </div>
        <button type="button" className="btn-ghost" onClick={onRefresh} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {error && (
        <div className="status-banner tone-error" role="alert">
          {error}
        </div>
      )}

      {!summary?.available && !loading && (
        <div className="empty-eval" data-testid="eval-empty">
          <p>No measured base/fine-tuned evaluation files found yet.</p>
          <p className="muted">
            Run <code>scripts/run_baseline.py</code> and{" "}
            <code>scripts/evaluate_model.py --mode fine-tuned</code>, then{" "}
            <code>scripts/compare_models.py</code>.
          </p>
        </div>
      )}

      {summary?.methodology && (
        <section className="eval-method">
          <h3>Methodology</h3>
          <dl className="kv">
            <div>
              <dt>Test set</dt>
              <dd>{summary.methodology.test_set ?? " - "}</dd>
            </div>
            <div>
              <dt>Size</dt>
              <dd>{summary.methodology.test_set_size ?? " - "}</dd>
            </div>
            <div>
              <dt>Temperature</dt>
              <dd>{summary.methodology.temperature ?? " - "}</dd>
            </div>
            <div>
              <dt>Protocol</dt>
              <dd>{summary.methodology.protocol ?? " - "}</dd>
            </div>
          </dl>
          {summary.methodology.notes && (
            <p className="muted">{summary.methodology.notes}</p>
          )}
        </section>
      )}

      {summary?.available && (
        <div className="eval-grid">
          <EvalColumn title="Base" block={summary.base} />
          <EvalColumn title="Fine-tuned" block={summary.fine_tuned} />
        </div>
      )}

      {summary?.comparison && (
        <section className="eval-compare">
          <h3>Comparison artifact</h3>
          <pre className="json-block">
            {JSON.stringify(summary.comparison, null, 2)}
          </pre>
        </section>
      )}
    </div>
  );
}

function EvalColumn({
  title,
  block,
}: {
  title: string;
  block: EvaluationSummary["base"];
}) {
  if (!block) {
    return (
      <section className="eval-col">
        <h3>{title}</h3>
        <p className="muted">No measured file.</p>
      </section>
    );
  }
  const metrics = block.metrics ?? {};
  return (
    <section className="eval-col" data-testid={`eval-col-${title.toLowerCase()}`}>
      <h3>{title}</h3>
      <p className="mono-sm">{block.model}</p>
      <p className="muted">
        n={block.n ?? (metrics.n as number | undefined) ?? " - "} ·{" "}
        {block.created_at ?? " - "}
      </p>
      <table className="metric-table">
        <tbody>
          {METRIC_KEYS.map(([key, label]) => (
            <tr key={key}>
              <th>{label}</th>
              <td>{fmtRate(metrics[key])}</td>
            </tr>
          ))}
          <tr>
            <th>Mean latency</th>
            <td>{fmtLatency(metrics)}</td>
          </tr>
          <tr>
            <th>Total tokens</th>
            <td>
              {(
                metrics.token_use as { total_tokens?: number } | undefined
              )?.total_tokens ?? " - "}
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}
