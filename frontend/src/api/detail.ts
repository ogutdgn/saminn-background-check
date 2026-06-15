// On-demand record detail: GET /api/record/{source}/{id} -> hydrated InmateRecord
// (e.g. Tarrant CID -> mugshot + full charges; Dallas case number -> court case sheet).
// Dallas's server is slow (~5-15s), so we allow a long timeout but never hang forever.
import type { InmateRecord } from "./types"

export async function fetchDetail(source: string, id: string): Promise<InmateRecord | null> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 45000)
  try {
    const r = await fetch(`/api/record/${encodeURIComponent(source)}/${encodeURIComponent(id)}`, {
      signal: ctrl.signal,
    })
    if (!r.ok) return null
    return (await r.json()) as InmateRecord
  } catch {
    return null // network error, abort/timeout, or bad JSON
  } finally {
    clearTimeout(timer)
  }
}
