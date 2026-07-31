import type { CompileResponse } from "../types/scenario";

interface CompilePanelProps {
  title: string;
  result: CompileResponse | null;
  loading?: boolean;
}

export function CompilePanel({ title, result, loading }: CompilePanelProps) {
  return (
    <section className="compile-panel" data-testid={`compile-panel-${title.toLowerCase().replace(/\s+/g, "-")}`}>
      <header>
        <h3>{title}</h3>
        {loading && <span className="pill loading">loading</span>}
        {!loading && result && (
          <span className={`pill ${result.ok ? "ok" : "fail"}`}>
            {result.ok ? "ok" : result.error_code ?? "failed"}
          </span>
        )}
      </header>
      {!result && !loading && <p className="muted">Not run yet.</p>}
      {result && (
        <div className="compile-body">
          <dl className="kv">
            <div>
              <dt>Model</dt>
              <dd>{result.model ?? "—"}</dd>
            </div>
            <div>
              <dt>Target</dt>
              <dd>{result.target_kind ?? "—"}</dd>
            </div>
            <div>
              <dt>Parse / schema / physics</dt>
              <dd>
                {result.json_parse_ok ? "Y" : "N"} /{" "}
                {result.schema_valid ? "Y" : "N"} /{" "}
                {result.physical_valid ? "Y" : "N"}
              </dd>
            </div>
            <div>
              <dt>Latency</dt>
              <dd>
                {result.latency_s != null ? `${result.latency_s.toFixed(2)} s` : "—"}
              </dd>
            </div>
            <div>
              <dt>Tokens</dt>
              <dd>{result.usage?.total_tokens ?? "—"}</dd>
            </div>
          </dl>
          {result.error && (
            <p className="compile-error" role="alert">
              {result.error}
            </p>
          )}
          {result.validation_issues.length > 0 && (
            <ul className="issue-list">
              {result.validation_issues.map((i, idx) => (
                <li key={`${i.code}-${idx}`}>
                  <strong>{i.code}</strong>: {i.message}
                </li>
              ))}
            </ul>
          )}
          <pre className="json-block" data-testid="compile-json">
            {result.parsed
              ? JSON.stringify(result.parsed, null, 2)
              : "(no parsed JSON)"}
          </pre>
        </div>
      )}
    </section>
  );
}
