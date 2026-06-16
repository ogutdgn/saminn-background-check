import { useEffect, useMemo, useRef, useState } from "react"
import {
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  ImageOff,
  Loader2,
  Scale,
  SearchX,
  TriangleAlert,
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

/** What the UI knows about an enabled source (from /api/health). */
export interface SourceMeta {
  id: string
  display_name: string
  transport: string
  has_photos: boolean
}

type Tone = "ok" | "muted" | "warn" | "danger"
const STATUS: Record<string, { label: string; tone: Tone; Icon: typeof CheckCircle2 }> = {
  ok: { label: "Match found", tone: "ok", Icon: CheckCircle2 },
  no_results: { label: "No matches", tone: "muted", Icon: SearchX },
  error: { label: "Source error", tone: "danger", Icon: TriangleAlert },
  timeout: { label: "Timed out", tone: "warn", Icon: Clock },
}
const TONE_TEXT: Record<Tone, string> = {
  ok: "text-emerald-600",
  muted: "text-zinc-500",
  warn: "text-amber-600",
  danger: "text-red-600",
}

// Display-only flavor (the architecture allows per-source display copy).
const SOURCE_KIND: Record<string, string> = {
  tarrant: "Sheriff jail roster · TX",
  dallas: "Criminal court records · TX",
  hunt: "Sheriff jail roster · TX",
  odcr: "Statewide court records · OK",
  denton: "Criminal court records · TX",
}
const SOURCE_SHORT: Record<string, string> = {
  tarrant: "Tarrant · TX",
  dallas: "Dallas · TX",
  hunt: "Hunt · TX",
  odcr: "ODCR · OK",
  denton: "Denton · TX",
}
// A stable per-source tint for the row chip (text/border only — distinct from status tones).
const SOURCE_TINT: Record<string, string> = {
  tarrant: "border-blue-200 bg-blue-50 text-blue-700",
  dallas: "border-violet-200 bg-violet-50 text-violet-700",
  hunt: "border-teal-200 bg-teal-50 text-teal-700",
  odcr: "border-orange-200 bg-orange-50 text-orange-700",
  denton: "border-rose-200 bg-rose-50 text-rose-700",
}
function tint(id: string) {
  return SOURCE_TINT[id] ?? "border-zinc-200 bg-zinc-50 text-zinc-600"
}
function shortName(s: SourceMeta) {
  return SOURCE_SHORT[s.id] ?? s.display_name
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
  const detailReq = useRef(0) // monotonic id so a stale detail fetch can't clobber the open dialog

  // filters / sort
  const [off, setOff] = useState<Set<string>>(new Set()) // disabled source ids
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
        (minYear == null || (rec.year_of_birth ? Number(rec.year_of_birth) >= minYear : false)),
    )
    return sortRows(rows, sort, order)
  }, [merged, off, sex, photoOnly, minYear, sort, order])

  // reset paging when the view shrinks/changes shape
  useEffect(() => setVisible(INITIAL_VISIBLE), [off, sex, photoOnly, minYear, sort])

  // auto-load mugshots for the first N visible photo-capable rows (re-runs when that set changes)
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
    return () => {
      cancelled = true
    }
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
    // Guard the shared dialog flags against an out-of-order resolve: if a newer open/retry started
    // while this fetch was in flight, drop this result so it can't clobber the current dialog.
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

  // per-source notices (partial / error / timeout) — surfaced once, not per row
  const notices = sources
    .map((s) => ({ s, r: results[s.id] }))
    .filter(({ r }) => r && (r.partial || r.status === "error" || r.status === "timeout"))

  // The stream is done when searching ends — even if it errored mid-way and some sources never
  // reported (don't require every source to have a result, or the empty state would never show).
  const allDone = !searching && sources.length > 0
  const noneMatched = allDone && merged.length === 0

  return (
    <>
      {/* sticky control bar */}
      <div className="bg-background/95 sticky top-0 z-20 -mx-4 mt-4 border-b px-4 py-2.5 backdrop-blur">
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

        <div className="text-muted-foreground mt-2 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
          <label className="flex items-center gap-1.5">
            <span>Sort</span>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as Sort)}
              className="border-input bg-background h-7 rounded-md border px-1.5 text-xs"
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
              ["M", "M"],
              ["F", "F"],
            ]}
          />

          <label className="border-input flex items-center gap-1 rounded-md border px-1.5 py-1">
            <span>Born ≥</span>
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
                "border-input h-7 rounded-md border px-2",
                photoOnly && "border-foreground/30 bg-muted text-foreground",
              )}
            >
              With photo
            </button>
          )}

          <span className="ml-auto">
            Showing <span className="text-foreground font-medium">{view.length.toLocaleString()}</span>{" "}
            of {merged.length.toLocaleString()}
          </span>
          {filtersActive && (
            <button
              type="button"
              onClick={clearFilters}
              className="hover:text-foreground inline-flex items-center gap-1 underline-offset-2 hover:underline"
            >
              <X className="size-3" /> Clear filters
            </button>
          )}
        </div>
      </div>

      {/* per-source notices */}
      {notices.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {notices.map(({ s, r }) => (
            <Notice key={s.id} source={s} result={r!} onRetry={() => {}} />
          ))}
        </div>
      )}

      {/* the unified list */}
      <div className="mt-3 space-y-2">
        {searching && merged.length === 0 && (
          <>
            <Skeleton className="h-[68px] w-full rounded-lg" />
            <Skeleton className="h-[68px] w-full rounded-lg" />
            <Skeleton className="h-[68px] w-full rounded-lg" />
          </>
        )}

        {noneMatched && (
          <p className="text-muted-foreground py-10 text-center text-sm">
            No matching records across {sources.length} sources.
          </p>
        )}

        {view.length === 0 && merged.length > 0 && (
          <p className="text-muted-foreground py-8 text-center text-sm">
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
            <UnifiedRow
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
            <span className="text-muted-foreground ml-1">
              ({(view.length - visible).toLocaleString()} hidden)
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

  return (
    <button
      type="button"
      onClick={onToggle}
      title={`${SOURCE_KIND[source.id] ?? ""} — click to ${off ? "include" : "hide"}`}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
        off ? "bg-muted/40 text-muted-foreground opacity-60" : "bg-background",
      )}
    >
      {!result && searching ? (
        <Loader2 className="text-muted-foreground size-3 animate-spin" />
      ) : status ? (
        <status.Icon className={cn("size-3", off ? "text-muted-foreground" : TONE_TEXT[status.tone])} />
      ) : (
        <span className="bg-muted-foreground/40 size-1.5 rounded-full" />
      )}
      <span className={cn("font-medium", off && "line-through")}>{source.display_name}</span>
      {countText && <span className="text-muted-foreground tabular-nums">{countText}</span>}
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
    <div className="border-input inline-flex overflow-hidden rounded-md border">
      {options.map(([v, label], i) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={cn(
            "h-7 px-2",
            i > 0 && "border-input border-l",
            value === v ? "bg-muted text-foreground font-medium" : "hover:bg-muted/50",
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
        "flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-xs",
        isProblem ? "border-red-200 bg-red-50 text-red-700" : "border-amber-200 bg-amber-50 text-amber-800",
      )}
    >
      <TriangleAlert className="mt-px size-3.5 shrink-0" />
      <span>
        <span className="font-medium">{source.display_name}:</span>{" "}
        {result.status === "timeout"
          ? "the source was too slow to respond — other sources are unaffected. Try again."
          : result.status === "error"
            ? (result.error ?? "this source returned an error.")
            : `showing the first ${(result.records?.length ?? 0).toLocaleString()} — add a first name to narrow (more exist).`}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------

function UnifiedRow({
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
  const matchedNote = isOther && matched?.detail ? `matched on ${matched.type}: ${matched.detail}` : null
  const c0 = (rec.charges ?? [])[0]
  const moreCharges = (rec.charges?.length ?? 0) - 1

  const inner = (
    <div className="flex items-center gap-3">
      <RowThumb source={source} photo={photo} fetched={fetched} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold">{rec.name}</span>
          {isOther && (
            <Badge variant="outline" className="text-muted-foreground shrink-0 text-[10px] uppercase">
              {matched!.type}
            </Badge>
          )}
        </div>
        {(meta || matchedNote) && (
          <div className="text-muted-foreground truncate text-xs">
            {[meta, matchedNote].filter(Boolean).join(" · ")}
          </div>
        )}
        {c0 && (
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 truncate text-xs">
            <span className="text-foreground/90">{c0.offense ?? "—"}</span>
            {c0.disposition && (
              <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                {c0.disposition}
              </Badge>
            )}
            {c0.case_no && <span className="text-muted-foreground">#{c0.case_no}</span>}
            {moreCharges > 0 && <span className="text-muted-foreground">+{moreCharges} more</span>}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge variant="outline" className={cn("border text-[10px]", tint(source.id))}>
          {shortName(source)}
        </Badge>
        {hasDetail && (
          <ChevronRight className="text-muted-foreground/60 size-4 transition-transform group-hover/row:translate-x-0.5" />
        )}
      </div>
    </div>
  )

  if (!hasDetail) return <div className="rounded-lg border p-3">{inner}</div>
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

function RowThumb({
  source,
  photo,
  fetched,
}: {
  source: SourceMeta
  photo?: string | null
  fetched: boolean
}) {
  if (source.has_photos) return <PhotoSlot photo={photo} fetched={fetched} size="sm" />
  return (
    <div className="bg-muted/50 text-muted-foreground flex h-16 w-12 shrink-0 flex-col items-center justify-center gap-1 rounded-md border">
      <Scale className="size-4 opacity-60" />
      <span className="text-[8px] leading-none">Court</span>
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
  denton: "Denton County · Tyler Public Access · Case Detail",
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

function sortRows(rows: Row[], sort: Sort, order: Record<string, number>): Row[] {
  const arr = [...rows]
  const byName = (a: Row, b: Row) => a.rec.name.localeCompare(b.rec.name)
  const bySource = (a: Row, b: Row) => (order[a.source.id] ?? 0) - (order[b.source.id] ?? 0)
  const yr = (r: Row) => (r.rec.year_of_birth ? Number(r.rec.year_of_birth) : null)
  const byYear = (a: Row, b: Row, dir: "asc" | "desc") => {
    const ya = yr(a)
    const yb = yr(b)
    if (ya == null && yb == null) return 0
    if (ya == null) return 1 // nulls last
    if (yb == null) return -1
    return dir === "desc" ? yb - ya : ya - yb
  }
  const rank = (r: Row) => TYPE_RANK[r.rec.matched_on?.[0]?.type ?? "name"] ?? 2

  if (sort === "name") arr.sort(byName)
  else if (sort === "year_desc") arr.sort((a, b) => byYear(a, b, "desc") || byName(a, b))
  else if (sort === "year_asc") arr.sort((a, b) => byYear(a, b, "asc") || byName(a, b))
  else if (sort === "source") arr.sort((a, b) => bySource(a, b) || byName(a, b))
  else arr.sort((a, b) => rank(a) - rank(b) || bySource(a, b) || byName(a, b)) // relevance
  return arr
}
