import { meaningfulDiff, type DiffEntry } from "../utils/jsonDiff";

interface JsonDiffProps {
  left: unknown;
  right: unknown;
  leftLabel?: string;
  rightLabel?: string;
}

function preview(v: unknown): string {
  if (v === undefined) return "—";
  try {
    const s = JSON.stringify(v);
    return s.length > 120 ? `${s.slice(0, 117)}…` : s;
  } catch {
    return String(v);
  }
}

export function JsonDiff({
  left,
  right,
  leftLabel = "Base",
  rightLabel = "Fine-tuned",
}: JsonDiffProps) {
  if (left == null && right == null) {
    return <p className="muted">No JSON to compare yet.</p>;
  }
  const entries: DiffEntry[] = meaningfulDiff(left ?? {}, right ?? {});
  if (entries.length === 0) {
    return (
      <p className="diff-identical" data-testid="json-diff-identical">
        Outputs are identical.
      </p>
    );
  }
  return (
    <div className="json-diff" data-testid="json-diff">
      <div className="diff-legend">
        <span className="diff-added">+ {rightLabel}</span>
        <span className="diff-removed">− {leftLabel}</span>
        <span className="diff-changed">~ changed</span>
      </div>
      <ul className="diff-list">
        {entries.slice(0, 80).map((e) => (
          <li key={`${e.kind}-${e.path}`} className={`diff-${e.kind}`}>
            <code className="diff-path">{e.path}</code>
            <span className="diff-vals">
              {e.kind !== "added" && (
                <span className="diff-left">{preview(e.left)}</span>
              )}
              {e.kind !== "removed" && (
                <span className="diff-right">{preview(e.right)}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {entries.length > 80 && (
        <p className="muted">Showing 80 of {entries.length} differences.</p>
      )}
    </div>
  );
}
