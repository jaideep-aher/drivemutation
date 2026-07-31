/** Structured path-level JSON diff (no external deps). */

export type DiffKind = "added" | "removed" | "changed" | "unchanged";

export interface DiffEntry {
  path: string;
  kind: DiffKind;
  left?: unknown;
  right?: unknown;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function diffJson(
  left: unknown,
  right: unknown,
  path = "$",
): DiffEntry[] {
  if (Object.is(left, right)) {
    return [{ path, kind: "unchanged", left, right }];
  }
  if (left === undefined) {
    return [{ path, kind: "added", right }];
  }
  if (right === undefined) {
    return [{ path, kind: "removed", left }];
  }
  if (Array.isArray(left) && Array.isArray(right)) {
    const n = Math.max(left.length, right.length);
    const out: DiffEntry[] = [];
    for (let i = 0; i < n; i++) {
      out.push(...diffJson(left[i], right[i], `${path}[${i}]`));
    }
    return out;
  }
  if (isObject(left) && isObject(right)) {
    const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
    const out: DiffEntry[] = [];
    for (const key of [...keys].sort()) {
      out.push(...diffJson(left[key], right[key], `${path}.${key}`));
    }
    return out;
  }
  return [{ path, kind: "changed", left, right }];
}

export function meaningfulDiff(left: unknown, right: unknown): DiffEntry[] {
  return diffJson(left, right).filter((e) => e.kind !== "unchanged");
}
