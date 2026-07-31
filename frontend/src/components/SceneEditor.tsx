interface SceneEditorProps {
  value: string;
  onChange: (value: string) => void;
  parseError: string | null;
}

export function SceneEditor({ value, onChange, parseError }: SceneEditorProps) {
  return (
    <section className="scene-editor" data-testid="scene-editor">
      <header>
        <h3>Structured seed scene</h3>
        {parseError ? (
          <span className="pill fail">invalid JSON</span>
        ) : (
          <span className="pill ok">valid JSON</span>
        )}
      </header>
      <textarea
        className="scene-json"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        aria-label="Scenario JSON editor"
        data-testid="scene-json"
      />
      {parseError && (
        <p className="compile-error" role="alert">
          {parseError}
        </p>
      )}
    </section>
  );
}
