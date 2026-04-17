if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    media: query,
    matches: false,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return false
    },
  })) as typeof window.matchMedia
}

if (!window.ResizeObserver) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }

  ;(window as typeof window & { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver = ResizeObserverStub
}
