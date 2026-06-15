import { useEffect, useState } from "react"
import type { AdapterResult, Charge, InmateRecord } from "@/api/types"
import { fetchDetail } from "@/api/detail"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

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

// Sources whose detail includes a mugshot — auto-load it at search for the identity scan.
// (A display hint; ideally the backend advertises photo capability per source.)
const IMAGE_SOURCES = new Set(["tarrant"])
const AUTO_PHOTO_CAP = 12 // auto-load photos for at most this many rows per image source
const CONCURRENCY = 3

function detailId(rec: InmateRecord): string | null {
  const v = (rec.raw as Record<string, unknown> | undefined)?.detail_id
  return typeof v === "string" && v ? v : null
}

function rawText(rec: InmateRecord | undefined, key: string): string | null {
  const v = (rec?.raw as Record<string, unknown> | undefined)?.[key]
  return typeof v === "string" ? v : null
}

function photoSrc(p?: string | null): string | undefined {
  return p ? `data:image/jpeg;base64,${p}` : undefined
}

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

  const [details, setDetails] = useState<Record<string, InmateRecord>>({})
  const [openRec, setOpenRec] = useState<InmateRecord | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  // search-time profile photos for image sources (first N rows, bounded concurrency)
  useEffect(() => {
    setDetails({})
    setOpenRec(null)
    if (!result || !IMAGE_SOURCES.has(id)) return
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

  async function openDetail(rec: InmateRecord) {
    setOpenRec(rec)
    const rid = detailId(rec)
    if (rid && !details[rid]) {
      setLoadingDetail(true)
      const d = await fetchDetail(id, rid)
      if (d) setDetails((prev) => ({ ...prev, [rid]: d }))
      setLoadingDetail(false)
    }
  }

  const openId = openRec ? detailId(openRec) : null
  const openDetailRec = openId ? details[openId] : undefined

  return (
    <>
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
                photo={rid ? details[rid]?.photo_base64 : undefined}
                hasDetail={!!rid}
                onOpen={() => openDetail(rec)}
              />
            )
          })}
        </CardContent>
      </Card>

      <Dialog open={!!openRec} onOpenChange={(o) => !o && setOpenRec(null)}>
        <DialogContent className="max-h-[88vh] overflow-auto sm:max-w-2xl">
          {openRec && (
            <DetailView
              rec={openRec}
              detail={openDetailRec}
              loading={loadingDetail}
              sourceTitle={title}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

function RecordRow({
  rec,
  photo,
  hasDetail,
  onOpen,
}: {
  rec: InmateRecord
  photo?: string | null
  hasDetail: boolean
  onOpen: () => void
}) {
  const meta = [rec.year_of_birth ? `b. ${rec.year_of_birth}` : null, rec.sex]
    .filter(Boolean)
    .join(" · ")
  const charges = rec.charges ?? []
  const matched = rec.matched_on ?? []

  return (
    <div className="rounded-md border p-3">
      <div className="flex gap-3">
        {photo && (
          <img
            src={photoSrc(photo)}
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
          {charges.length > 0 && (
            <ul className="mt-2 space-y-1">
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
          {hasDetail && (
            <Button variant="ghost" size="sm" className="mt-1 h-6 px-2 text-xs" onClick={onOpen}>
              More details
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

function DetailView({
  rec,
  detail,
  loading,
  sourceTitle,
}: {
  rec: InmateRecord
  detail?: InmateRecord
  loading: boolean
  sourceTitle: string
}) {
  const name = detail?.name || rec.name
  const photo = detail?.photo_base64
  const yob = detail?.year_of_birth ?? rec.year_of_birth
  const sex = detail?.sex ?? rec.sex
  const charges: Charge[] = (detail?.charges?.length ? detail.charges : rec.charges) ?? []
  const sheet = rawText(detail, "detail_text")
  const meta = [yob ? `b. ${yob}` : null, sex].filter(Boolean).join(" · ")

  return (
    <>
      <DialogHeader>
        <DialogTitle>{name}</DialogTitle>
        <DialogDescription>
          {sourceTitle}
          {meta ? ` · ${meta}` : ""}
        </DialogDescription>
      </DialogHeader>

      <div className="flex gap-4">
        {photo ? (
          <img
            src={photoSrc(photo)}
            alt={`Booking photo — ${name}`}
            className="h-40 w-32 shrink-0 rounded border object-cover"
          />
        ) : loading ? (
          <Skeleton className="h-40 w-32 shrink-0 rounded" />
        ) : null}

        <div className="min-w-0 flex-1 space-y-2">
          <div className="text-sm font-medium">Charges</div>
          {loading && charges.length === 0 && (
            <p className="text-muted-foreground text-sm">Loading details…</p>
          )}
          {!loading && charges.length === 0 && (
            <p className="text-muted-foreground text-sm">No charges listed.</p>
          )}
          <ul className="space-y-1.5">
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
          {rec.source_url && (
            <a
              href={rec.source_url}
              target="_blank"
              rel="noreferrer"
              className="text-primary inline-block text-xs underline"
            >
              Open the source record ↗
            </a>
          )}
        </div>
      </div>

      {sheet && (
        <div className="mt-2">
          <div className="mb-1 text-sm font-medium">Court case sheet</div>
          <pre className="bg-muted max-h-72 overflow-auto rounded-md p-3 font-mono text-[11px] leading-snug whitespace-pre-wrap">
            {sheet}
          </pre>
        </div>
      )}
    </>
  )
}
