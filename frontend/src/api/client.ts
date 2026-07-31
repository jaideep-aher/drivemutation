import type {
  CompileResponse,
  EvaluationSummary,
  ModelsStatus,
  PresetSummary,
  ScenarioSpec,
  SimulateResponse,
  ValidationIssue,
} from "../types/scenario";

const API_BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function fetchPresets(): Promise<PresetSummary[]> {
  return request("/api/presets");
}

export function fetchPreset(id: string): Promise<ScenarioSpec> {
  return request(`/api/presets/${id}`);
}

export function validateScenario(
  scenario: ScenarioSpec,
): Promise<{ valid: boolean; issues: ValidationIssue[] }> {
  return request("/api/validate", {
    method: "POST",
    body: JSON.stringify({ scenario }),
  });
}

export function simulateScenario(scenario: ScenarioSpec): Promise<SimulateResponse> {
  return request("/api/simulate", {
    method: "POST",
    body: JSON.stringify({ scenario }),
  });
}

export function fetchHealth(): Promise<{ status: string; deterministic: boolean }> {
  return request("/api/health");
}

export function compileBase(
  seed_scene: ScenarioSpec,
  testing_goal: string,
): Promise<CompileResponse> {
  return request("/api/compile/base", {
    method: "POST",
    body: JSON.stringify({ seed_scene, testing_goal, run_simulation: true }),
  });
}

export function compileFineTuned(
  seed_scene: ScenarioSpec,
  testing_goal: string,
): Promise<CompileResponse> {
  return request("/api/compile/fine-tuned", {
    method: "POST",
    body: JSON.stringify({ seed_scene, testing_goal, run_simulation: true }),
  });
}

export function fetchModelsStatus(): Promise<ModelsStatus> {
  return request("/api/models/status");
}

export function fetchEvaluationSummary(): Promise<EvaluationSummary> {
  return request("/api/evaluation/summary");
}
