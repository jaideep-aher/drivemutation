import type { CompileResponse } from "../types/scenario";

interface CompilePanelProps {
  title: string;
  result: CompileResponse | null;
  loading?: boolean;
}

function plainStatus(result: CompileResponse): { label: string; detail: string } {
  if (result.ok && result.target_kind === "rejection") {
    return {
      label: "Rejected (valid)",
      detail: "Model correctly refused an impossible or contradictory ask.",
    };
  }
  if (result.ok && result.physical_valid) {
    return {
      label: "Compiled + simulated",
      detail: "Valid mutation. Playback below uses this when preferred.",
    };
  }
  if (result.ok && result.schema_valid && !result.physical_valid) {
    return {
      label: "Schema OK, physics failed",
      detail: result.error ?? "Output matched the schema but failed physics checks.",
    };
  }
  if (result.json_parse_ok && !result.schema_valid) {
    return {
      label: "Invalid shape",
      detail: "Returned JSON, but not our mutation/rejection schema.",
    };
  }
  if (!result.json_parse_ok) {
    return {
      label: "Bad output",
      detail: result.error ?? result.error_code ?? "Could not parse model output.",
    };
  }
  return {
    label: result.error_code ?? "Failed",
    detail: result.error ?? "Compile failed.",
  };
}

export function CompilePanel({ title, result, loading }: CompilePanelProps) {
  return (
    <section
      className="compile-panel"
      data-testid={`compile-panel-${title.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <header>
        <h3>{title}</h3>
        {loading && <span className="pill loading">calling OpenAI...</span>}
        {!loading && result && (
          <span className={`pill ${result.ok ? "ok" : "fail"}`}>
            {plainStatus(result).label}
          </span>
        )}
      </header>
      {!result && !loading && <p className="muted">Not run yet.</p>}
      {result && (
        <div className="compile-body">
          <p className="compile-plain" data-testid="compile-plain">
            {plainStatus(result).detail}
          </p>
          <p className="mono-sm muted">
            {result.latency_s != null ? `${result.latency_s.toFixed(1)}s` : "-"}
            {result.usage?.total_tokens != null
              ? ` · ${result.usage.total_tokens} tokens`
              : ""}
            {result.model ? ` · via OpenAI` : ""}
          </p>
          {result.validation_issues.length > 0 && (
            <details className="soft-details">
              <summary>Why it failed ({result.validation_issues.length})</summary>
              <ul className="issue-list">
                {result.validation_issues.slice(0, 3).map((i, idx) => (
                  <li key={`${i.code}-${idx}`}>
                    <strong>{i.code}</strong>: {i.message.slice(0, 180)}
                    {i.message.length > 180 ? "..." : ""}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <details className="soft-details">
            <summary>Raw JSON</summary>
            <pre className="json-block" data-testid="compile-json">
              {result.parsed
                ? JSON.stringify(result.parsed, null, 2)
                : "(no parsed JSON)"}
            </pre>
          </details>
        </div>
      )}
    </section>
  );
}
