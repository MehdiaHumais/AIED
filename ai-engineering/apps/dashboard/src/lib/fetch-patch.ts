const API_BASE = process.env.NEXT_PUBLIC_API_URL || ""

if (typeof window !== "undefined" && API_BASE) {
  const originalFetch = window.fetch.bind(window)
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === "string" && input.startsWith("/api/")) {
      input = `${API_BASE}${input}`
    } else if (input instanceof URL && input.pathname.startsWith("/api/")) {
      input = `${API_BASE}${input.pathname}${input.search}`
    } else if (input instanceof Request && "url" in input) {
      const r = input as Request
      if (r.url.startsWith("/api/")) {
        return originalFetch(`${API_BASE}${r.url}`, r)
      }
    }
    return originalFetch(input, init)
  }
}

export {}