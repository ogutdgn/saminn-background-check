import { useEffect, useMemo, useRef, useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  FileText,
  ImageOff,
  Loader2,
  Scale,
  SearchX,
  Shield,
  X,
} from "lucide-react"
import type { AdapterResult, Charge, InmateRecord } from "@/api/types"
import { fetchDetail } from "@/api/detail"
import { cn } from "@/lib/utils"
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

export interface SourceMeta {
  id: string
  display_name: string
  transport: string
  has_photos: boolean
  portal_url?: string | null
}

type Tone = "ok" | "muted" | "warn" | "danger"
const STATUS: Record<string, { label: string; tone: Tone; Icon: typeof CheckCircle2 }> = {
  ok: { label: "Match found", tone: "ok", Icon: CheckCircle2 },
  no_results: { label: "No matches", tone: "muted", Icon: SearchX },
  error: { label: "Source error", tone: "danger", Icon: AlertTriangle },
  timeout: { label: "Timed out", tone: "warn", Icon: Clock },
}
const TONE_TEXT: Record<Tone, string> = {
  ok: "text-emerald-600",
  muted: "text-slate-400",
  warn: "text-amber-500",
  danger: "text-red-500",
}

const SOURCE_KIND: Record<string, string> = {
  tarrant: "Sheriff jail roster · TX",
  dallas: "Criminal court records · TX",
  hunt: "Sheriff jail roster · TX",
  odcr: "Statewide court records · OK",
  denton: "Criminal court records · TX",
  denton_dc: "District Court felonies · TX",
  collin: "Criminal court records · TX",
}
const SOURCE_SHORT: Record<string, string> = {
  tarrant: "Tarrant · TX",
  dallas: "Dallas · TX",
  hunt: "Hunt · TX",
  odcr: "ODCR · OK",
  denton: "Denton JP · TX",
  denton_dc: "Denton DC · TX",
  collin: "Collin · TX",
}

// jail = booking/custody sources; court = court record sources
const SOURCE_TYPE: Record<string, "jail" | "court"> = {
  tarrant: "jail",
  hunt: "jail",
  dallas: "court",
  denton: "court",
  denton_dc: "court",
  odcr: "court",
  collin: "court",
}

// Per-source tint for the source chip
const SOURCE_TINT: Record<string, string> = {
  tarrant: "border-amber-200 bg-amber-50 text-amber-800",
  dallas: "border-violet-200 bg-violet-50 text-violet-700",
  hunt: "border-orange-200 bg-orange-50 text-orange-800",
  odcr: "border-sky-200 bg-sky-50 text-sky-700",
  denton: "border-rose-200 bg-rose-50 text-rose-700",
  denton_dc: "border-pink-200 bg-pink-50 text-pink-700",
  collin: "border-emerald-200 bg-emerald-50 text-emerald-700",
}

// Left border color for rows: amber for jail, indigo for court
const ROW_BORDER: Record<string, string> = {
  tarrant: "border-l-amber-400",
  hunt: "border-l-amber-400",
  dallas: "border-l-indigo-400",
  denton: "border-l-indigo-400",
  denton_dc: "border-l-indigo-500",
  odcr: "border-l-sky-400",
  collin: "border-l-indigo-400",
}

function tint(id: string) {
  return SOURCE_TINT[id] ?? "border-zinc-200 bg-zinc-50 text-zinc-600"
}
function rowBorder(id: string) {
  return ROW_BORDER[id] ?? "border-l-slate-300"
}
function shortName(s: SourceMeta) {
  return SOURCE_SHORT[s.id] ?? s.display_name
}
function sourceType(id: string): "jail" | "court" {
  return SOURCE_TYPE[id] ?? "court"
}

// Extract charge severity from offense/disposition text
function chargeSeverity(charge: Charge): "felony" | "misdemeanor" | null {
  const text = `${charge.offense ?? ""} ${charge.disposition ?? ""}`.toLowerCase()
  if (text.includes("felony")) return "felony"
  if (text.includes("misdemeanor")) return "misdemeanor"
  return null
}

const INITIAL_VISIBLE = 25
const VISIBLE_STEP = 50
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
function sexLabel(sex?: string | null): string | null {
  if (!sex) return null
  return { M: "Male", F: "Female", U: "Unknown" }[sex] ?? sex
}

type Row = { rec: InmateRecord; source: SourceMeta; key: string }
type Sort = "relevance" | "name" | "year_desc" | "year_asc" | "source"
const TYPE_RANK: Record<string, number> = { name: 0, alias: 1, other: 2, attorney: 3 }

// ---------------------------------------------------------------------------

export function Results({
  sources,
  results,
  searching,
}: {
  sources: SourceMeta[]
  results: Record<string, AdapterResult>
  searching: boolean
}) {
  const [details, setDetails] = useState<Record<string, InmateRecord>>({})
  const [openRec, setOpenRec] = useState<Row | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [detailError, setDetailError] = useState(false)
  const [visible, setVisible] = useState(INITIAL_VISIBLE)
  const detailReq = useRef(0)

  const [off, setOff] = useState<Set<string>>(new Set())
  const [sort, setSort] = useState<Sort>("relevance")
  const [sex, setSex] = useState<"all" | "M" | "F">("all")
  const [photoOnly, setPhotoOnly] = useState(false)
  const [minYear, setMinYear] = useState<number | null>(null)

  const order = useMemo(() => {
    const m: Record<string, number> = {}
    sources.forEach((s, i) => (m[s.id] = i))
    return m
  }, [sources])
  const anyPhotos = sources.some((s) => s.has_photos)

  const merged = useMemo(() => {
    const out: Row[] = []
    for (const s of sources) {
      const recs = results[s.id]?.records ?? []
      recs.forEach((rec, i) => out.push({ rec, source: s, key: `${s.id}:${i}` }))
    }
    return out
  }, [sources, results])

  const view = useMemo(() => {
    const rows = merged.filter(
      ({ rec, source }) =>
        !off.has(source.id) &&
        (sex === "all" || rec.sex === sex) &&
        (!photoOnly || source.has_photos) &&
        (minYear == null || Number(rec.year_of_birth) === minYear),
    )
    return sortRows(rows, sort, order)
  }, [merged, off, sex, photoOnly, minYear, sort, order])

  useEffect(() => setVisible(INITIAL_VISIBLE), [off, sex, photoOnly, minYear, sort])

  const photoTargets = useMemo(
    () =>
      view
        .filter((r) => r.source.has_photos && detailId(r.rec))
        .slice(0, AUTO_PHOTO_CAP)
        .map((r) => ({ source: r.source.id, did: detailId(r.rec)!, ck: `${r.source.id}:${detailId(r.rec)}` })),
    [view],
  )
  const photoSig = photoTargets.map((t) => t.ck).join("|")
  useEffect(() => {
    const todo = photoTargets.filter((t) => !details[t.ck])
    if (!todo.length) return
    let cancelled = false
    let next = 0
    const worker = async () => {
      while (next < todo.length && !cancelled) {
        const t = todo[next++]
        const d = await fetchDetail(t.source, t.did)
        if (d && !cancelled) setDetails((prev) => ({ ...prev, [t.ck]: d }))
      }
    }
    void Promise.all(Array.from({ length: Math.min(CONCURRENCY, todo.length) }, worker))
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [photoSig])

  async function openDetail(row: Row) {
    setOpenRec(row)
    setDetailError(false)
    const did = detailId(row.rec)
    const ck = did ? `${row.source.id}:${did}` : null
    if (ck && !details[ck]) await loadDetail(row.source.id, did!, ck)
  }
  async function loadDetail(source: string, did: string, ck: string) {
    const reqId = ++detailReq.current
    setLoadingDetail(true)
    setDetailError(false)
    const d = await fetchDetail(source, did)
    if (detailReq.current !== reqId) return
    if (d) setDetails((prev) => ({ ...prev, [ck]: d }))
    else setDetailError(true)
    setLoadingDetail(false)
  }

  const openDid = openRec ? detailId(openRec.rec) : null
  const openCk = openRec && openDid ? `${openRec.source.id}:${openDid}` : null
  const openDetailRec = openCk ? details[openCk] : undefined

  const filtersActive = off.size > 0 || sex !== "all" || photoOnly || minYear != null
  function clearFilters() {
    setOff(new Set())
    setSex("all")
    setPhotoOnly(false)
    setMinYear(null)
  }
  function toggleSource(id: string) {
    setOff((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  const notices = sources
    .map((s) => ({ s, r: results[s.id] }))
    .filter(({ r }) => r && (r.partial || r.status === "error" || r.status === "timeout"))

  const allDone = !searching && sources.length > 0
  const noneMatched = allDone && merged.length === 0

  return (
    <>
      {/* Sticky control bar */}
      <div className="sticky top-0 z-20 -mx-4 mt-4 border-b bg-card/95 px-4 py-2.5 shadow-sm backdrop-blur">
        {/* Source chips */}
        <div className="flex flex-wrap items-center gap-1.5">
          {sources.map((s) => (
            <SourceChip
              key={s.id}
              source={s}
              result={results[s.id]}
              searching={searching}
              off={off.has(s.id)}
              onToggle={() => toggleSource(s.id)}
            />
          ))}
        </div>

        {/* Filter / sort bar */}
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs text-muted-foreground">
          <label className="flex items-center gap-1.5">
            <span className="uppercase tracking-wide text-[10px] font-semibold">Sort</span>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as Sort)}
              className="h-7 rounded border border-input bg-background px-1.5 text-xs"
            >
              <option value="relevance">Best match</option>
              <option value="name">Name A–Z</option>
              <option value="year_desc">Birth year (newest)</option>
              <option value="year_asc">Birth year (oldest)</option>
              <option value="source">Source</option>
            </select>
          </label>

          <Segmented
            value={sex}
            onChange={(v) => setSex(v as "all" | "M" | "F")}
            options={[
              ["all", "Any sex"],
              ["M", "Male"],
              ["F", "Female"],
            ]}
          />

          <label className="flex items-center gap-1 rounded border border-input px-1.5 py-1">
            <span className="text-[10px] uppercase tracking-wide font-semibold">Born</span>
            <input
              type="number"
              inputMode="numeric"
              placeholder="year"
              value={minYear ?? ""}
              onChange={(e) => setMinYear(e.target.value ? Number(e.target.value) : null)}
              className="w-14 bg-transparent text-xs outline-none"
            />
          </label>

          {anyPhotos && (
            <button
              type="button"
              onClick={() => setPhotoOnly((v) => !v)}
              className={cn(
                "h-7 rounded border border-input px-2 text-xs",
                photoOnly && "border-primary/40 bg-primary/10 text-primary font-medium",
              )}
            >
              With photo
            </button>
          )}

          <span className="ml-auto text-xs">
            <span className="font-semibold text-foreground">{view.length.toLocaleString()}</span>
            {" "}of {merged.length.toLocaleString()} shown
          </span>
          {filtersActive && (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex items-center gap-1 hover:text-foreground hover:underline underline-offset-2"
            >
              <X className="size-3" /> Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Per-source notices */}
      {notices.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {notices.map(({ s, r }) => (
            <Notice key={s.id} source={s} result={r!} onRetry={() => {}} />
          ))}
        </div>
      )}

      {/* Result list */}
      <div className="mt-3 space-y-2">
        {searching && merged.length === 0 && (
          <>
            <Skeleton className="h-[76px] w-full rounded-lg" />
            <Skeleton className="h-[76px] w-full rounded-lg" />
            <Skeleton className="h-[76px] w-full rounded-lg" />
          </>
        )}

        {noneMatched && (
          <div className="py-12 text-center">
            <SearchX className="mx-auto mb-2 size-8 text-muted-foreground/40" />
            <p className="text-sm font-medium">No records found</p>
            <p className="mt-1 text-xs text-muted-foreground">
              No matching records across {sources.length} sources.
            </p>
          </div>
        )}

        {view.length === 0 && merged.length > 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No records match the current filters.{" "}
            <button onClick={clearFilters} className="text-foreground underline underline-offset-2">
              Clear filters
            </button>
          </p>
        )}

        {view.slice(0, visible).map((row) => {
          const did = detailId(row.rec)
          const photo = did ? details[`${row.source.id}:${did}`]?.photo_base64 : undefined
          const fetched = !!(did && details[`${row.source.id}:${did}`])
          return (
            <RecordRow
              key={row.key}
              row={row}
              photo={photo}
              fetched={fetched}
              onOpen={() => openDetail(row)}
            />
          )
        })}

        {view.length > visible && (
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => setVisible((v) => v + VISIBLE_STEP)}
          >
            Show {Math.min(VISIBLE_STEP, view.length - visible).toLocaleString()} more
            <span className="ml-1 text-muted-foreground">
              ({(view.length - visible).toLocaleString()} remaining)
            </span>
          </Button>
        )}
      </div>

      <Dialog open={!!openRec} onOpenChange={(o) => !o && setOpenRec(null)}>
        <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-4xl lg:max-w-5xl">
          {openRec && (
            <RecordDetail
              rec={openRec.rec}
              detail={openDetailRec}
              loading={loadingDetail}
              error={detailError}
              onRetry={() => openDid && openCk && loadDetail(openRec.source.id, openDid, openCk)}
              hasPhotos={openRec.source.has_photos}
              sourceTitle={openRec.source.display_name}
              sourceId={openRec.source.id}
              portalUrl={openRec.source.portal_url}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}

// ---------------------------------------------------------------------------

function SourceChip({
  source,
  result,
  searching,
  off,
  onToggle,
}: {
  source: SourceMeta
  result?: AdapterResult
  searching: boolean
  off: boolean
  onToggle: () => void
}) {
  const status = result ? (STATUS[result.status] ?? STATUS.error) : null
  const count = result?.records?.length ?? 0
  const countText = result
    ? result.status === "ok"
      ? result.partial
        ? `${count.toLocaleString()}+`
        : count.toLocaleString()
      : result.status === "no_results"
        ? "0"
        : "—"
    : ""

  const isJail = sourceType(source.id) === "jail"

  return (
    <button
      type="button"
      onClick={onToggle}
      title={`${SOURCE_KIND[source.id] ?? ""} — click to ${off ? "show" : "hide"}`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition-colors",
        off ? "bg-muted/30 text-muted-foreground opacity-50" : "bg-card",
        !off && isJail ? "border-amber-200" : !off ? "border-indigo-200" : "",
      )}
    >
      {!result && searching ? (
        <Loader2 className="size-3 animate-spin text-muted-foreground" />
      ) : status ? (
        <status.Icon className={cn("size-3", off ? "text-muted-foreground" : TONE_TEXT[status.tone])} />
      ) : (
        <span className="size-1.5 rounded-full bg-muted-foreground/30" />
      )}
      <span className={cn("font-medium", off && "line-through")}>{source.display_name}</span>
      {countText && (
        <span className={cn(
          "rounded px-1 py-0.5 text-[10px] font-semibold tabular-nums",
          result?.status === "ok" && !off ? "bg-primary/10 text-primary" : "text-muted-foreground"
        )}>
          {countText}
        </span>
      )}
    </button>
  )
}

function Segmented({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: [string, string][]
}) {
  return (
    <div className="inline-flex overflow-hidden rounded border border-input">
      {options.map(([v, label], i) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={cn(
            "h-7 px-2 text-xs",
            i > 0 && "border-l border-input",
            value === v ? "bg-muted font-medium text-foreground" : "hover:bg-muted/50",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

function Notice({
  source,
  result,
}: {
  source: SourceMeta
  result: AdapterResult
  onRetry: () => void
}) {
  const isProblem = result.status === "error" || result.status === "timeout"
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded border px-2.5 py-1.5 text-xs",
        isProblem
          ? "border-red-200 bg-red-50 text-red-700"
          : "border-amber-200 bg-amber-50 text-amber-800",
      )}
    >
      <AlertTriangle className="mt-px size-3.5 shrink-0" />
      <span>
        <span className="font-semibold">{source.display_name}:</span>{" "}
        {result.status === "timeout"
          ? "source timed out — other sources unaffected."
          : result.status === "error"
            ? (result.error || "source returned an error.")
            : `showing first ${(result.records?.length ?? 0).toLocaleString()} results — add a first name to narrow.`}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------

function RecordRow({
  row,
  photo,
  fetched,
  onOpen,
}: {
  row: Row
  photo?: string | null
  fetched: boolean
  onOpen: () => void
}) {
  const { rec, source } = row
  const hasDetail = !!detailId(rec)
  const matched = rec.matched_on?.[0]
  const isOther = matched && matched.type !== "name"
  const meta = [rec.year_of_birth ? `b. ${rec.year_of_birth}` : null, sexLabel(rec.sex)]
    .filter(Boolean)
    .join(" · ")
  const c0 = (rec.charges ?? [])[0]
  const moreCharges = (rec.charges?.length ?? 0) - 1
  const severity = c0 ? chargeSeverity(c0) : null
  const isJail = sourceType(source.id) === "jail"

  const inner = (
    <div className="flex items-stretch gap-3">
      {/* Left accent border via a div rather than border-l to avoid layout shift */}
      <div className={cn("w-1 shrink-0 rounded-full", isJail ? "bg-amber-400" : "bg-indigo-400")} />

      <RowThumb source={source} photo={photo} fetched={fetched} />

      <div className="min-w-0 flex-1 py-0.5">
        {/* Name + match type */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold leading-tight tracking-tight truncate">{rec.name}</span>
          {isOther && (
            <Badge variant="outline" className="shrink-0 text-[9px] uppercase text-muted-foreground">
              {matched!.type}
            </Badge>
          )}
        </div>

        {/* DOB / sex */}
        {meta && (
          <div className="mt-0.5 text-[11px] text-muted-foreground">{meta}</div>
        )}

        {/* Primary charge */}
        {c0 && (
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {severity === "felony" && (
              <span className="inline-flex items-center rounded border border-red-200 bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-700">
                Felony
              </span>
            )}
            {severity === "misdemeanor" && (
              <span className="inline-flex items-center rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                Misd.
              </span>
            )}
            <span className="text-xs font-semibold text-foreground/90 truncate">
              {c0.offense ?? "—"}
            </span>
            {moreCharges > 0 && (
              <span className="text-[11px] text-muted-foreground">+{moreCharges} more</span>
            )}
          </div>
        )}

        {/* Disposition + case # */}
        {c0 && (c0.disposition || c0.case_no) && (
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            {c0.disposition && (
              <span className="text-[11px] text-muted-foreground truncate">{c0.disposition}</span>
            )}
            {c0.case_no && (
              <span className="text-[11px] text-muted-foreground/70 font-mono">#{c0.case_no}</span>
            )}
          </div>
        )}
      </div>

      {/* Source badge + chevron */}
      <div className="flex shrink-0 flex-col items-end justify-between gap-1 py-0.5">
        <Badge variant="outline" className={cn("text-[10px] font-medium border", tint(source.id))}>
          {shortName(source)}
        </Badge>
        {hasDetail && (
          <ChevronRight className="size-4 text-muted-foreground/40 transition-transform group-hover/row:translate-x-0.5" />
        )}
      </div>
    </div>
  )

  const base = "rounded-lg border bg-card p-3 shadow-sm"
  if (!hasDetail) return <div className={base}>{inner}</div>
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        base,
        "group/row block w-full text-left transition-colors hover:border-primary/30 hover:bg-primary/[0.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
      )}
    >
      {inner}
    </button>
  )
}

function RowThumb({
  source,
  photo,
  fetched,
}: {
  source: SourceMeta
  photo?: string | null
  fetched: boolean
}) {
  const isJail = sourceType(source.id) === "jail"
  if (source.has_photos) return <PhotoSlot photo={photo} fetched={fetched} size="sm" />
  return (
    <div className={cn(
      "flex h-16 w-12 shrink-0 flex-col items-center justify-center gap-1 rounded border",
      isJail ? "bg-amber-50 border-amber-100 text-amber-400" : "bg-indigo-50 border-indigo-100 text-indigo-400"
    )}>
      {isJail ? <Shield className="size-4" /> : <Scale className="size-4" />}
      <span className="text-[8px] leading-none font-semibold uppercase tracking-wide opacity-70">
        {isJail ? "Jail" : "Court"}
      </span>
    </div>
  )
}

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
        className={cn(box, "shrink-0 rounded border object-cover")}
      />
    )
  }
  return (
    <div className={cn(box, "flex shrink-0 flex-col items-center justify-center gap-1 rounded border bg-muted text-muted-foreground")}>
      {loading ? (
        <Loader2 className="size-5 animate-spin" />
      ) : fetched ? (
        <>
          <ImageOff className="size-4" />
          <span className="text-[9px] leading-none">No image</span>
        </>
      ) : (
        <ImageOff className="size-4 opacity-30" />
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
  sourceId,
  portalUrl,
}: {
  rec: InmateRecord
  detail?: InmateRecord
  loading: boolean
  error: boolean
  onRetry: () => void
  hasPhotos: boolean
  sourceTitle: string
  sourceId: string
  portalUrl?: string | null
}) {
  const name = detail?.name || rec.name
  const photo = detail?.photo_base64
  const yob = detail?.year_of_birth ?? rec.year_of_birth
  const sex = detail?.sex ?? rec.sex
  const charges: Charge[] = (detail?.charges?.length ? detail.charges : rec.charges) ?? []
  const sheet = rawText(detail, "detail_text")
  const meta = [yob ? `b. ${yob}` : null, sexLabel(sex)].filter(Boolean).join(" · ")
  const showPortrait = hasPhotos || !!photo || (!loading && !!detail)
  const deepLink = detail?.source_url || rec.source_url
  const caseRef =
    charges.map((c) => c.case_no).find(Boolean) ||
    rawText(detail, "case_no") ||
    rawText(rec, "case_no")
  const isJail = sourceType(sourceId) === "jail"

  return (
    <>
      <DialogHeader className="pb-2 border-b">
        <div className="flex items-start gap-3">
          <div className={cn(
            "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded",
            isJail ? "bg-amber-100 text-amber-600" : "bg-indigo-100 text-indigo-600"
          )}>
            {isJail ? <Shield className="size-4" /> : <Scale className="size-4" />}
          </div>
          <div>
            <DialogTitle className="text-lg font-bold">{name}</DialogTitle>
            <DialogDescription className="flex items-center gap-2 mt-0.5">
              <span>{sourceTitle}</span>
              {meta && <><span aria-hidden>·</span><span>{meta}</span></>}
              <Badge variant="outline" className={cn("ml-1 text-[10px]", tint(sourceId))}>
                {isJail ? "Jail Record" : "Court Record"}
              </Badge>
            </DialogDescription>
          </div>
        </div>
      </DialogHeader>

      <div className="flex gap-5 pt-1">
        {showPortrait && <PhotoSlot photo={photo} loading={loading} fetched={!!detail} size="lg" />}

        <div className="min-w-0 flex-1 space-y-4">
          {/* Charges section */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <FileText className="size-3.5 text-muted-foreground" />
              <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
                Charges
              </span>
            </div>
            {loading && charges.length === 0 && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading details…
              </p>
            )}
            {!loading && !error && charges.length === 0 && (
              <p className="text-sm text-muted-foreground">No charges listed.</p>
            )}
            <ul className="space-y-2">
              {charges.map((c, i) => {
                const sev = chargeSeverity(c)
                return (
                  <li key={i} className="rounded border bg-muted/30 px-3 py-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {sev === "felony" && (
                        <span className="rounded border border-red-200 bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-700">
                          Felony
                        </span>
                      )}
                      {sev === "misdemeanor" && (
                        <span className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                          Misdemeanor
                        </span>
                      )}
                      <span className="text-sm font-semibold">{c.offense ?? "—"}</span>
                    </div>
                    {(c.disposition || c.case_no) && (
                      <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                        {c.disposition && <span>{c.disposition}</span>}
                        {c.case_no && <span className="font-mono">#{c.case_no}</span>}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>

          {/* Source / link section */}
          <div className="border-t pt-3">
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              Source
            </div>
            {deepLink ? (
              <a
                href={deepLink}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline"
              >
                Open this record on {sourceTitle} <ExternalLink className="size-3" />
              </a>
            ) : portalUrl ? (
              <div className="space-y-1 text-xs">
                <a
                  href={portalUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
                >
                  Open {sourceTitle} portal <ExternalLink className="size-3" />
                </a>
                <p className="text-muted-foreground">
                  This source requires a live session to deep-link
                  {caseRef ? (
                    <> — search for <span className="font-mono font-medium text-foreground">#{caseRef}</span> there</>
                  ) : null}.
                </p>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No public link available for this source.</p>
            )}
          </div>
        </div>
      </div>

      {error && !detail && (
        <div className="mt-2 flex flex-wrap items-center gap-3 rounded border border-red-200 bg-red-50 p-3 text-sm">
          <AlertTriangle className="size-4 shrink-0 text-red-500" />
          <span className="text-red-700 flex-1">
            Couldn't load the full record — the source site didn't respond.
          </span>
          <Button variant="outline" size="sm" className="h-7" onClick={onRetry}>
            Retry
          </Button>
        </div>
      )}

      {loading && !sheet && !hasPhotos && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Fetching case sheet from source…
          <span className="text-xs">(can take 10–15s)</span>
        </div>
      )}

      {sheet && <CaseSheet text={sheet} source={rec.source} sourceTitle={sourceTitle} />}
    </>
  )
}

const CASE_SHEET_HEADERS: Record<string, string> = {
  dallas: "Dallas County · Felony & Misdemeanor Courts · Case Information",
  odcr: "Oklahoma · On Demand Court Records · Case Record",
  denton: "Denton County · Tyler Public Access · JP & County Criminal",
  denton_dc: "Denton County · Tyler Public Access · District Court",
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
    <div className="mt-3">
      <div className="mb-1.5 flex items-center gap-2">
        <FileText className="size-3.5 text-muted-foreground" />
        <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          Court Case Sheet
        </span>
      </div>
      <div className="overflow-hidden rounded border border-slate-200 shadow-sm">
        <div className="border-b border-slate-200 bg-slate-100 px-3 py-1.5 text-center text-[10px] font-semibold uppercase tracking-widest text-slate-600">
          {header}
        </div>
        <pre
          className="max-h-[55vh] overflow-auto bg-[#fafaf8] px-4 py-3 text-[11px] leading-relaxed whitespace-pre text-slate-700"
          style={{ fontFamily: '"Courier New", Courier, ui-monospace, monospace' }}
        >
          {body}
        </pre>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

function sortRows(rows: Row[], sort: Sort, order: Record<string, number>): Row[] {
  const arr = [...rows]
  const byName = (a: Row, b: Row) => a.rec.name.localeCompare(b.rec.name)
  const bySource = (a: Row, b: Row) => (order[a.source.id] ?? 0) - (order[b.source.id] ?? 0)
  const yr = (r: Row) => (r.rec.year_of_birth ? Number(r.rec.year_of_birth) : null)
  const byYear = (a: Row, b: Row, dir: "asc" | "desc") => {
    const ya = yr(a)
    const yb = yr(b)
    if (ya == null && yb == null) return 0
    if (ya == null) return 1
    if (yb == null) return -1
    return dir === "desc" ? yb - ya : ya - yb
  }
  const rank = (r: Row) => TYPE_RANK[r.rec.matched_on?.[0]?.type ?? "name"] ?? 2

  if (sort === "name") arr.sort(byName)
  else if (sort === "year_desc") arr.sort((a, b) => byYear(a, b, "desc") || byName(a, b))
  else if (sort === "year_asc") arr.sort((a, b) => byYear(a, b, "asc") || byName(a, b))
  else if (sort === "source") arr.sort((a, b) => bySource(a, b) || byName(a, b))
  else arr.sort((a, b) => rank(a) - rank(b) || bySource(a, b) || byName(a, b))
  return arr
}
