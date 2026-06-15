import { useEffect, useState } from "react"
import type { AdapterResult, Charge, InmateRecord } from "@/api/types"
import { fetchDetail } from "@/api/detail"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

const STATUS_LABEL: Record<string, string> = {
  ok: "OK",
  no_results: "No results",
  error: "Error",
  timeout: "Timed out",
}

function statusVariant(s: string): "default" | "secondary" | "destructive" {
  if (s === "ok") return "default"
  if (s === "no_results") return "secondary"
  return "destructive" // error / timeout
}

function titleCase(id: string): string {
  return id.charAt(0).toUpperCase() + id.slice(1) + " County"
}

// A record's detail id (what /api/record/{source}/{id} takes). Today only Tarrant exposes one.
function detailId(rec: InmateRecord): string | null {
  const cid = (rec.raw as Record<string, unknown> | undefined)?.CID
  return typeof cid === "string" ? cid : null
}

const AUTO_PHOTO_CAP = 12 // auto-load profile photos for at most this many rows per source
const CONCURRENCY = 3 // bounded so we don't hammer the source

export function SourceCard({
  id,
  result,
  pending,
}: {
  id: string
  result?: AdapterResult
  pending: boolean
}) {
  const title = result?.display_name ?? titleCase(id)
  const records = result?.records ?? []

  // Per-record detail (photo + full charges), fetched on demand and cached by detail id.
  const [details, setDetails] = useState<Record<string, InmateRecord>>({})

  const requestDetail = async (rid: string) => {
    if (details[rid]) return
    const d = await fetchDetail(id, rid)
    if (d) setDetails((prev) => ({ ...prev, [rid]: d }))
  }

  // Search-time profile photos: auto-load detail for the first N rows that have a detail id.
  useEffect(() => {
    setDetails({})
    if (!result) return
    const ids = records.map(detailId).filter((x): x is string => !!x).slice(0, AUTO_PHOTO_CAP)
    if (ids.length === 0) return
    let cancelled = false
    let next = 0
    const worker = async () => {
      while (next < ids.length && !cancelled) {
        const rid = ids[next++]
        const d = await fetchDetail(id, rid)
        if (d && !cancelled) setDetails((prev) => ({ ...prev, [rid]: d }))
      }
    }
    void Promise.all(Array.from({ length: Math.min(CONCURRENCY, ids.length) }, worker))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result])

  return (
    <Card className="h-full">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">{title}</CardTitle>
          {result ? (
            <Badge variant={statusVariant(result.status)}>
              {STATUS_LABEL[result.status] ?? result.status}
            </Badge>
          ) : pending ? (
            <Badge variant="outline" className="animate-pulse">
              Searching…
            </Badge>
          ) : null}
        </div>
        {result && (
          <p className="text-muted-foreground text-xs">
            {records.length} record{records.length === 1 ? "" : "s"}
            {result.total != null && result.total !== records.length ? ` of ${result.total}` : ""}
            {" · "}
            {result.duration_ms} ms
          </p>
        )}
        {result?.partial && (
          <p className="text-xs font-medium text-amber-600">
            Showing the first {records.length} — add a first name to narrow (more exist).
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-2">
        {pending && !result && (
          <div className="space-y-2">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        )}
        {result?.status === "error" && (
          <p className="text-destructive text-sm">{result.error ?? "Source error"}</p>
        )}
        {result?.status === "ok" && records.length === 0 && (
          <p className="text-muted-foreground text-sm">No matches.</p>
        )}
        {records.map((rec, i) => {
          const rid = detailId(rec)
          return (
            <RecordRow
              key={i}
              rec={rec}
              detail={rid ? details[rid] : undefined}
              detailId={rid}
              onRequestDetail={requestDetail}
            />
          )
        })}
      </CardContent>
    </Card>
  )
}

function RecordRow({
  rec,
  detail,
  detailId,
  onRequestDetail,
}: {
  rec: InmateRecord
  detail?: InmateRecord
  detailId: string | null
  onRequestDetail: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const meta = [rec.year_of_birth ? `b. ${rec.year_of_birth}` : null, rec.sex]
    .filter(Boolean)
    .join(" · ")
  const photo = detail?.photo_base64
  const listCharges = rec.charges ?? []
  const detailCharges = detail?.charges ?? []
  // list-level charges show always (Dallas has them); "More details" swaps in the
  // richer detail charges (Tarrant's charges only exist at the detail level).
  const charges: Charge[] = open && detailCharges.length > 0 ? detailCharges : listCharges
  const loadingDetail = open && !!detailId && !detail
  const matched = rec.matched_on ?? []

  function toggle() {
    const next = !open
    setOpen(next)
    if (next && detailId && !detail) onRequestDetail(detailId)
  }

  return (
    <div className="rounded-md border p-3">
      <div className="flex gap-3">
        {photo && (
          <img
            src={`data:image/jpeg;base64,${photo}`}
            alt={`Booking photo — ${rec.name}`}
            className="h-16 w-12 shrink-0 rounded border object-cover"
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="text-sm font-medium">{rec.name}</div>
            <div className="flex shrink-0 gap-1">
              {matched.map((m, i) => (
                <Badge key={i} variant="outline" className="px-1.5 py-0 text-[10px] uppercase">
                  {m.type}
                </Badge>
              ))}
            </div>
          </div>
          {meta && <div className="text-muted-foreground mt-0.5 text-xs">{meta}</div>}

          {(charges.length > 0 || loadingDetail) && (
            <ul className="mt-2 space-y-1">
              {loadingDetail && (
                <li className="text-muted-foreground text-xs">Loading details…</li>
              )}
              {charges.map((c, i) => (
                <li key={i} className="flex flex-wrap items-center gap-1.5 text-sm">
                  <span>{c.offense ?? "—"}</span>
                  {c.disposition && (
                    <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                      {c.disposition}
                    </Badge>
                  )}
                  {c.case_no && <span className="text-muted-foreground text-xs">#{c.case_no}</span>}
                </li>
              ))}
            </ul>
          )}

          {detailId && (
            <Button
              variant="ghost"
              size="sm"
              className="mt-1 h-6 px-2 text-xs"
              onClick={toggle}
            >
              {open ? "Hide details" : "More details"}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
