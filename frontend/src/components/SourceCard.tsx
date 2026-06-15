import { useEffect, useState } from "react"
import {
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  ImageOff,
  Loader2,
  SearchX,
  TriangleAlert,
} from "lucide-react"
import type { AdapterResult, Charge, InmateRecord } from "@/api/types"
import { fetchDetail } from "@/api/detail"
import { cn } from "@/lib/utils"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
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

/** What the UI knows about an enabled source (from /api/health) — no per-county hardcoding. */
export interface SourceMeta {
  id: string
  display_name: string
  transport: string
  has_photos: boolean
}

// Display-only flavor (the architecture allows per-source *display* copy). Falls back gracefully.
const SOURCE_KIND: Record<string, string> = {
  tarrant: "Sheriff jail roster · TX",
  dallas: "Criminal court records · TX",
  hunt: "Sheriff jail roster · TX",
  odcr: "Statewide court records · OK",
}
function sourceKind(s: SourceMeta): string {
  return SOURCE_KIND[s.id] ?? (s.has_photos ? "Jail roster" : "Court records")
}

type Tone = "ok" | "muted" | "warn" | "danger"

const STATUS: Record<string, { label: string; tone: Tone; Icon: typeof CheckCircle2 }> = {
  ok: { label: "Match found", tone: "ok", Icon: CheckCircle2 },
  no_results: { label: "No matches", tone: "muted", Icon: SearchX },
  error: { label: "Source error", tone: "danger", Icon: TriangleAlert },
  timeout: { label: "Timed out", tone: "warn", Icon: Clock },
}

const TONE_BADGE: Record<Tone, string> = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-700",
  muted: "border-zinc-200 bg-zinc-100 text-zinc-600",
  warn: "border-amber-200 bg-amber-50 text-amber-700",
  danger: "border-red-200 bg-red-50 text-red-700",
}

const INITIAL_VISIBLE = 8
const VISIBLE_STEP = 25
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

// ---------------------------------------------------------------------------

export function SourceCard({
  source,
  result,
  pending,
}: {
  source: SourceMeta
  result?: AdapterResult
  pending: boolean
}) {
  const { id, display_name: title, has_photos: hasPhotos } = source
  const records = result?.records ?? []

  const [details, setDetails] = useState<Record<string, InmateRecord>>({})
  const [openRec, setOpenRec] = useState<InmateRecord | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [detailError, setDetailError] = useState(false)
  const [visible, setVisible] = useState(INITIAL_VISIBLE)

  // Auto-load the first N mugshots for image sources, so staff get a visual identity scan.
  useEffect(() => {
    setDetails({})
    setOpenRec(null)
    setVisible(INITIAL_VISIBLE)
    if (!result || !hasPhotos) return
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
  const status = result ? (STATUS[result.status] ?? STATUS.error) : null

  return (
    <>
      <Card className="h-full">
        <CardHeader className="gap-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate font-heading text-base font-semibold">{title}</div>
              <div className="text-muted-foreground mt-0.5 text-xs">{sourceKind(source)}</div>
            </div>
            {status ? (
              <Badge
                className={cn("shrink-0 gap-1 border font-medium", TONE_BADGE[status.tone])}
                variant="outline"
              >
                <status.Icon className="size-3" />
                {status.label}
              </Badge>
            ) : pending ? (
              <Badge variant="outline" className="text-muted-foreground shrink-0 gap-1">
                <Loader2 className="size-3 animate-spin" />
                Searching
              </Badge>
            ) : null}
          </div>

          {result && (
            <div className="text-muted-foreground mt-2 flex items-center gap-1.5 text-xs">
              <span className="text-foreground font-medium">{records.length.toLocaleString()}</span>
              <span>
                {records.length === 1 ? "record" : "records"}
                {result.total != null && result.total > records.length
                  ? ` of ${result.total.toLocaleString()}`
                  : ""}
              </span>
              <span aria-hidden>·</span>
              <span>{formatMs(result.duration_ms)}</span>
            </div>
          )}
        </CardHeader>

        <CardContent className="space-y-2">
          {/* pending */}
          {pending && !result && (
            <div className="space-y-2">
              <Skeleton className="h-[68px] w-full rounded-lg" />
              <Skeleton className="h-[68px] w-full rounded-lg" />
            </div>
          )}

          {/* partial note */}
          {result?.partial && (
            <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-800">
              <TriangleAlert className="mt-px size-3.5 shrink-0" />
              <span>
                Showing the first {records.length.toLocaleString()} — add a first name to narrow
                (more exist).
              </span>
            </div>
          )}

          {/* error / timeout */}
          {result && (result.status === "error" || result.status === "timeout") && (
            <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-2 text-xs text-red-700">
              <TriangleAlert className="mt-px size-3.5 shrink-0" />
              <span>
                {result.status === "timeout"
                  ? "The source was too slow to respond. Try again — other sources are unaffected."
                  : (result.error ?? "This source returned an error.")}
              </span>
            </div>
          )}

          {/* no matches */}
          {result?.status === "no_results" && (
            <p className="text-muted-foreground py-2 text-center text-sm">
              No matching records.
            </p>
          )}
          {result?.status === "ok" && records.length === 0 && (
            <p className="text-muted-foreground py-2 text-center text-sm">No matching records.</p>
          )}

          {/* records */}
          {records.slice(0, visible).map((rec, i) => {
            const rid = detailId(rec)
            return (
              <RecordRow
                key={i}
                rec={rec}
                photo={rid ? details[rid]?.photo_base64 : undefined}
                fetched={!!(rid && details[rid])}
                showPhoto={hasPhotos}
                hasDetail={!!rid}
                onOpen={() => openDetail(rec)}
              />
            )
          })}

          {records.length > visible && (
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => setVisible((v) => v + VISIBLE_STEP)}
            >
              Show {Math.min(VISIBLE_STEP, records.length - visible)} more
              <span className="text-muted-foreground ml-1">
                ({(records.length - visible).toLocaleString()} hidden)
              </span>
            </Button>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!openRec} onOpenChange={(o) => !o && setOpenRec(null)}>
        <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-4xl lg:max-w-5xl">
          {openRec && (
            <RecordDetail
              rec={openRec}
              detail={openDetailRec}
              loading={loadingDetail}
              error={detailError}
              onRetry={() => openId && loadDetail(openId)}
              hasPhotos={hasPhotos}
              sourceTitle={title}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

// ---------------------------------------------------------------------------

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
  const meta = [rec.year_of_birth ? `b. ${rec.year_of_birth}` : null, sexLabel(rec.sex)]
    .filter(Boolean)
    .join(" · ")
  const charges = rec.charges ?? []
  const matched = rec.matched_on ?? []
  const role = matched[0]?.detail

  const inner = (
    <div className="flex gap-3">
      {showPhoto && <PhotoSlot photo={photo} fetched={fetched} size="sm" />}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="truncate text-sm font-semibold">{rec.name}</div>
          {matched.map((m, i) => (
            <Badge
              key={i}
              variant="outline"
              className="text-muted-foreground shrink-0 text-[10px] uppercase"
              title={m.detail ?? undefined}
            >
              {m.type}
            </Badge>
          ))}
        </div>
        {(meta || role) && (
          <div className="text-muted-foreground mt-0.5 truncate text-xs">
            {[meta, role].filter(Boolean).join(" · ")}
          </div>
        )}
        {charges.length > 0 && (
          <ul className="mt-1.5 space-y-1">
            {charges.slice(0, 2).map((c, i) => (
              <li key={i} className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-foreground">{c.offense ?? "—"}</span>
                {c.disposition && (
                  <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                    {c.disposition}
                  </Badge>
                )}
                {c.case_no && <span className="text-muted-foreground">#{c.case_no}</span>}
              </li>
            ))}
            {charges.length > 2 && (
              <li className="text-muted-foreground text-xs">+{charges.length - 2} more</li>
            )}
          </ul>
        )}
      </div>
      {hasDetail && (
        <ChevronRight className="text-muted-foreground/60 mt-0.5 size-4 shrink-0 self-center transition-transform group-hover/row:translate-x-0.5" />
      )}
    </div>
  )

  if (!hasDetail) {
    return <div className="rounded-lg border p-3">{inner}</div>
  }
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group/row hover:border-foreground/20 hover:bg-muted/40 focus-visible:ring-ring/50 block w-full rounded-lg border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none"
    >
      {inner}
    </button>
  )
}

/** Fixed-size image slot: photo, spinner while loading, "No image" once confirmed none, or a faint
 *  placeholder when the photo simply hasn't been fetched yet. */
function PhotoSlot({
  photo,
  loading,
  fetched,
  size,
}: {
  photo?: string | null
  loading?: boolean
  fetched?: boolean
  size: "sm" | "lg"
}) {
  const box = size === "lg" ? "h-44 w-36" : "h-16 w-12"
  if (photo) {
    return (
      <img
        src={photoSrc(photo)}
        alt="Booking photo"
        className={`${box} shrink-0 rounded-md border object-cover`}
      />
    )
  }
  return (
    <div
      className={`bg-muted text-muted-foreground flex ${box} shrink-0 flex-col items-center justify-center gap-1 rounded-md border`}
    >
      {loading ? (
        <Loader2 className="size-5 animate-spin" />
      ) : fetched ? (
        <>
          <ImageOff className="size-4" />
          <span className="text-[9px] leading-none">No image</span>
        </>
      ) : (
        <ImageOff className="size-4 opacity-40" />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------

function RecordDetail({
  rec,
  detail,
  loading,
  error,
  onRetry,
  hasPhotos,
  sourceTitle,
}: {
  rec: InmateRecord
  detail?: InmateRecord
  loading: boolean
  error: boolean
  onRetry: () => void
  hasPhotos: boolean
  sourceTitle: string
}) {
  const name = detail?.name || rec.name
  const photo = detail?.photo_base64
  const yob = detail?.year_of_birth ?? rec.year_of_birth
  const sex = detail?.sex ?? rec.sex
  const charges: Charge[] = (detail?.charges?.length ? detail.charges : rec.charges) ?? []
  const sheet = rawText(detail, "detail_text")
  const meta = [yob ? `b. ${yob}` : null, sexLabel(sex)].filter(Boolean).join(" · ")
  const showPortrait = hasPhotos || !!photo || (!loading && !!detail)

  return (
    <>
      <DialogHeader>
        <DialogTitle className="text-lg">{name}</DialogTitle>
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
              <Loader2 className="size-4 animate-spin" /> Loading details…
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
              className="text-primary inline-flex items-center gap-1 text-xs underline-offset-4 hover:underline"
            >
              Open the source record <ExternalLink className="size-3" />
            </a>
          )}
        </div>
      </div>

      {error && !detail && (
        <div className="mt-1 flex flex-wrap items-center gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm">
          <span className="text-red-700">
            Couldn't load the full record — the source site is slow or didn't respond.
          </span>
          <Button variant="outline" size="sm" className="h-7" onClick={onRetry}>
            Retry
          </Button>
        </div>
      )}
      {loading && !sheet && !hasPhotos && (
        <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin" /> Fetching the court case sheet…
          <span className="text-xs">(the source site is slow — this can take 10–15s)</span>
        </div>
      )}
      {sheet && <CaseSheet text={sheet} source={rec.source} sourceTitle={sourceTitle} />}
    </>
  )
}

const CASE_SHEET_HEADERS: Record<string, string> = {
  dallas: "Dallas County · Felony & Misdemeanor Courts · Case Information",
  odcr: "Oklahoma · On Demand Court Records · Case Record",
}

function CaseSheet({
  text,
  source,
  sourceTitle,
}: {
  text: string
  source: string
  sourceTitle: string
}) {
  const header = CASE_SHEET_HEADERS[source] ?? `${sourceTitle} · Case Record`
  const body = source === "dallas" ? text.replace(/^Dallas County[^\n]*\n/i, "") : text
  return (
    <div className="mt-1">
      <div className="mb-1 text-sm font-medium">Court case sheet</div>
      <div className="overflow-hidden rounded-md border border-zinc-300 shadow-sm">
        <div className="border-b border-zinc-300 bg-zinc-100 px-3 py-1.5 text-center text-[10px] font-semibold tracking-wide text-zinc-700 uppercase">
          {header}
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

// ---------------------------------------------------------------------------

function sexLabel(sex?: string | null): string | null {
  if (!sex) return null
  return { M: "Male", F: "Female", U: "Unknown" }[sex] ?? sex
}
function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`
}
