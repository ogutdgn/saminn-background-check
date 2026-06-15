import { useEffect, useState } from "react"
import { ImageOff, Loader2 } from "lucide-react"
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
const IMAGE_SOURCES = new Set(["tarrant", "hunt"])
const AUTO_PHOTO_CAP = 12
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

/** Fixed-size image slot: photo, spinner while loading, "No image" once confirmed none,
 *  or a faint placeholder when the photo simply hasn't been fetched yet. */
function PhotoSlot({
  photo,
  loading,
  fetched,
  size,
}: {
  photo?: string | null
  loading?: boolean
  fetched?: boolean // true once detail was fetched (so "no photo" really means none)
  size: "sm" | "lg"
}) {
  const box = size === "lg" ? "h-40 w-32" : "h-16 w-12"
  if (photo) {
    return (
      <img
        src={photoSrc(photo)}
        alt="Booking photo"
        className={`${box} shrink-0 rounded border object-cover`}
      />
    )
  }
  return (
    <div
      className={`bg-muted text-muted-foreground flex ${box} shrink-0 flex-col items-center justify-center gap-1 rounded border`}
    >
      {loading ? (
        <Loader2 className="h-5 w-5 animate-spin" />
      ) : fetched ? (
        <>
          <ImageOff className="h-4 w-4" />
          <span className="text-[9px] leading-none">No image</span>
        </>
      ) : (
        <ImageOff className="h-4 w-4 opacity-40" />
      )}
    </div>
  )
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
  const imageSource = IMAGE_SOURCES.has(id)

  const [details, setDetails] = useState<Record<string, InmateRecord>>({})
  const [openRec, setOpenRec] = useState<InmateRecord | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [detailError, setDetailError] = useState(false)

  useEffect(() => {
    setDetails({})
    setOpenRec(null)
    if (!result || !imageSource) return
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

  async function loadDetail(rid: string) {
    setLoadingDetail(true)
    setDetailError(false)
    const d = await fetchDetail(id, rid)
    if (d) setDetails((prev) => ({ ...prev, [rid]: d }))
    else setDetailError(true)
    setLoadingDetail(false)
  }

  async function openDetail(rec: InmateRecord) {
    setOpenRec(rec)
    setDetailError(false)
    const rid = detailId(rec)
    if (rid && !details[rid]) await loadDetail(rid)
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
              <Badge variant="outline" className="gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
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
                fetched={!!(rid && details[rid])}
                showPhoto={imageSource}
                hasDetail={!!rid}
                onOpen={() => openDetail(rec)}
              />
            )
          })}
        </CardContent>
      </Card>

      <Dialog open={!!openRec} onOpenChange={(o) => !o && setOpenRec(null)}>
        <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-4xl lg:max-w-5xl">
          {openRec && (
            <DetailView
              rec={openRec}
              detail={openDetailRec}
              loading={loadingDetail}
              error={detailError}
              onRetry={() => openId && loadDetail(openId)}
              imageSource={imageSource}
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
  fetched,
  showPhoto,
  hasDetail,
  onOpen,
}: {
  rec: InmateRecord
  photo?: string | null
  fetched: boolean
  showPhoto: boolean
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
        {showPhoto && <PhotoSlot photo={photo} fetched={fetched} size="sm" />}
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
  error,
  onRetry,
  imageSource,
  sourceTitle,
}: {
  rec: InmateRecord
  detail?: InmateRecord
  loading: boolean
  error: boolean
  onRetry: () => void
  imageSource: boolean
  sourceTitle: string
}) {
  const name = detail?.name || rec.name
  const photo = detail?.photo_base64
  const yob = detail?.year_of_birth ?? rec.year_of_birth
  const sex = detail?.sex ?? rec.sex
  const charges: Charge[] = (detail?.charges?.length ? detail.charges : rec.charges) ?? []
  const sheet = rawText(detail, "detail_text")
  const meta = [yob ? `b. ${yob}` : null, sex].filter(Boolean).join(" · ")
  // show the portrait slot for image sources, or once we've fetched detail (so "No image" is true)
  const showPortrait = imageSource || !!photo || (!loading && !!detail)

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
        {showPortrait && <PhotoSlot photo={photo} loading={loading} fetched={!!detail} size="lg" />}

        <div className="min-w-0 flex-1 space-y-2">
          <div className="text-sm font-medium">Charges</div>
          {loading && charges.length === 0 && (
            <p className="text-muted-foreground flex items-center gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading details…
            </p>
          )}
          {!loading && !error && charges.length === 0 && (
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

      {error && !detail && (
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
          <span className="text-destructive">
            Couldn't load the full record — the county site is slow or didn't respond.
          </span>
          <Button variant="outline" size="sm" className="h-7" onClick={onRetry}>
            Retry
          </Button>
        </div>
      )}
      {loading && !sheet && !imageSource && (
        <div className="text-muted-foreground mt-3 flex flex-wrap items-center gap-2 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" /> Fetching the court case sheet…
          <span className="text-xs">(the county site is slow — this can take 10–15s)</span>
        </div>
      )}
      {sheet && <CaseSheet text={sheet} />}
    </>
  )
}

/** Render the court case sheet to look like the real document, not plain text. */
function CaseSheet({ text }: { text: string }) {
  // drop the leading title line — we put it in the document header bar instead
  const body = text.replace(/^Dallas County[^\n]*\n/i, "")
  return (
    <div className="mt-3">
      <div className="mb-1 text-sm font-medium">Court case sheet</div>
      <div className="overflow-hidden rounded-md border border-zinc-300 shadow-sm">
        <div className="border-b border-zinc-300 bg-zinc-100 px-3 py-1.5 text-center text-[10px] font-semibold tracking-wide text-zinc-700 uppercase">
          Dallas County · Felony &amp; Misdemeanor Courts · Case Information
        </div>
        <pre
          className="max-h-[60vh] overflow-auto bg-[#fcfbf6] px-4 py-3 text-[11px] leading-[1.5] whitespace-pre text-zinc-800"
          style={{ fontFamily: '"Courier New", Courier, ui-monospace, monospace' }}
        >
          {body}
        </pre>
      </div>
    </div>
  )
}
