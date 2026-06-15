// SSE client for POST /api/search. The browser's native EventSource is GET-only, so we
// POST with fetch() and parse the text/event-stream off the response body ourselves.
import type { AdapterResult, SearchQuery } from "./types"

export interface SearchHandlers {
  onResult: (r: AdapterResult) => void
  onDone?: () => void
  onError?: (e: unknown) => void
}

export async function search(
  query: SearchQuery,
  handlers: SearchHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let resp: Response
  try {
    resp = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(query),
      signal,
    })
  } catch (e) {
    handlers.onError?.(e)
    return
  }
  if (!resp.ok || !resp.body) {
    handlers.onError?.(new Error(`search failed (${resp.status})`))
    return
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ""
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      // events are separated by a blank line (SSE servers use CRLF or LF)
      let m: RegExpExecArray | null
      const boundary = /\r?\n\r?\n/
      while ((m = boundary.exec(buf)) !== null) {
        const block = buf.slice(0, m.index)
        buf = buf.slice(m.index + m[0].length)
        const evt = parseEvent(block)
        if (evt?.event === "result") {
          try {
            handlers.onResult(JSON.parse(evt.data) as AdapterResult)
          } catch {
            /* skip a malformed event rather than killing the stream */
          }
        }
      }
    }
  } catch (e) {
    handlers.onError?.(e)
  } finally {
    handlers.onDone?.()
  }
}

function parseEvent(block: string): { event: string; data: string } | null {
  let event = "message"
  let data = ""
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim()
    else if (line.startsWith("data:")) data += line.slice(5).trim()
  }
  return data ? { event, data } : null
}
