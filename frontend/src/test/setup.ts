/// <reference types="vitest" />
import "@testing-library/jest-dom/vitest";

// jsdom has no IntersectionObserver, which the scenario list uses to page in
// more results as you scroll. Stub it so components mount; tests that need to
// exercise paging drive it through the keyboard path instead.
if (!("IntersectionObserver" in globalThis)) {
  class StubIntersectionObserver implements IntersectionObserver {
    readonly root: Element | Document | null = null;
    readonly rootMargin: string = "";
    readonly thresholds: ReadonlyArray<number> = [];
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  }
  globalThis.IntersectionObserver =
    StubIntersectionObserver as unknown as typeof IntersectionObserver;
}
