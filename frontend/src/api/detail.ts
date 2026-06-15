// On-demand record detail: GET /api/record/{source}/{id} -> hydrated InmateRecord
// (e.g. Tarrant CID -> mugshot + full charges). Returns null if there's no detail / on error.
import type { InmateRecord } from "./types"

export async function fetchDetail(source: string, id: string): Promise<InmateRecord | null> {
  try {
    const r = await fetch(`/api/record/${encodeURIComponent(source)}/${encodeURIComponent(id)}`)
    if (!r.ok) return null
    return (await r.json()) as InmateRecord
  } catch {
    return null
  }
}
