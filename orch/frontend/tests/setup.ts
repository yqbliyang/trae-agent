import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement ResizeObserver; stub it
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// @ts-expect-error jsdom global
globalThis.ResizeObserver = globalThis.ResizeObserver || ResizeObserverStub;

class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
  root = null;
  rootMargin = "";
  thresholds = [];
}
// @ts-expect-error jsdom global
globalThis.IntersectionObserver = globalThis.IntersectionObserver || IntersectionObserverStub;
