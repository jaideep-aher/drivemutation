interface StatusBannerProps {
  code?: string | null;
  message?: string | null;
  tone?: "info" | "ok" | "warn" | "error";
  testId?: string;
}

const TONE_FROM_CODE: Record<string, StatusBannerProps["tone"]> = {
  fine_tuning_pending: "warn",
  fine_tuning_failed: "error",
  missing_model_config: "warn",
  missing_api_key: "warn",
  api_timeout: "error",
  api_error: "error",
  malformed_json: "error",
  schema_invalid: "error",
  physically_invalid: "error",
  physics_invalid: "error",
};

export function StatusBanner({
  code,
  message,
  tone,
  testId = "status-banner",
}: StatusBannerProps) {
  if (!code && !message) return null;
  const resolved =
    tone ??
    (code ? TONE_FROM_CODE[code] : undefined) ??
    (code ? "error" : "info");
  return (
    <div className={`status-banner tone-${resolved}`} role="status" data-testid={testId}>
      {code && <span className="status-code">{code}</span>}
      {message && <span className="status-msg">{message}</span>}
    </div>
  );
}
