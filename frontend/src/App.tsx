import { useEffect, useMemo, useRef, useState, type FormEvent } from "react"
import { AlertTriangle, Loader2, Search, ShieldCheck, X } from "lucide-react"
import type { AdapterResult } from "@/api/types"
import { search } from "@/api/search"
import { Results, type SourceMeta } from "@/components/Results"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

export default function App() {
  const [sources, setSources] = useState<SourceMeta[]>([])
  const [healthError, setHealthError] = useState(false)
  const [results, setResults] = useState<Record<string, AdapterResult>>({})
  const [searching, setSearching] = useState(false)
  const [submitted, setSubmitted] = useState<{ last: string; first: string } | null>(null)
  const [last, setLast] = useState("")
  const [first, setFirst] = useState("")
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => setSources(d.sources ?? []))
      .catch(() => setHealthError(true))
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const lastName = last.trim()
    if (!lastName) return
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    setResults({})
    setSubmitted({ last: lastName, first: first.trim() })
    setSearching(true)
    const active = () => abortRef.current === ac
    await search(
      { last: lastName, first: first.trim() || undefined, max_results: 25 },
      {
        onResult: (r) => active() && setResults((prev) => ({ ...prev, [r.source]: r })),
        onDone: () => active() && setSearching(false),
        onError: () => active() && setSearching(false),
      },
      ac.signal,
    )
  }

  function clearSearch() {
    abortRef.current?.abort()
    setResults({})
    setSubmitted(null)
    setSearching(false)
    setLast("")
    setFirst("")
  }

  const summary = useMemo(() => {
    const done = Object.values(results)
    return {
      responded: done.length,
      totalRecords: done.reduce((n, r) => n + (r.records?.length ?? 0), 0),
      problems: done.filter((r) => r.status === "error" || r.status === "timeout").length,
      elapsed: done.reduce((m, r) => Math.max(m, r.duration_ms), 0),
    }
  }, [results])

  const hasQuery = !!submitted
  const queryLabel = submitted ? [submitted.last, submitted.first].filter(Boolean).join(", ") : ""

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      {/* Header */}
      <header className="bg-primary text-primary-foreground shadow-md">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <ShieldCheck className="size-6 shrink-0 opacity-90" />
          <div className="min-w-0">
            <h1 className="text-sm font-semibold leading-tight tracking-wide uppercase">
              Criminal Background Search
            </h1>
            <p className="text-[11px] opacity-50 leading-none mt-0.5">
              The Samaritan Inn · Intake · Confidential
            </p>
          </div>
          {sources.length > 0 && (
            <div className="ml-auto flex items-center gap-1.5 text-xs opacity-60 shrink-0">
              <span>{sources.length} sources</span>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        {/* Search form */}
        <div className="bg-card rounded-lg border shadow-sm">
          <div className="border-b px-4 py-2.5">
            <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Subject Name Search
            </p>
          </div>
          <form onSubmit={onSubmit} className="px-4 py-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="grid grow basis-44 gap-1.5">
                <label htmlFor="last" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Last Name
                </label>
                <Input
                  id="last"
                  value={last}
                  onChange={(e) => setLast(e.target.value)}
                  placeholder="e.g. Smith"
                  autoFocus
                  autoComplete="off"
                  className="font-medium"
                />
              </div>
              <div className="grid grow basis-44 gap-1.5">
                <label htmlFor="first" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  First Name <span className="normal-case font-normal">(optional)</span>
                </label>
                <Input
                  id="first"
                  value={first}
                  onChange={(e) => setFirst(e.target.value)}
                  placeholder="e.g. John"
                  autoComplete="off"
                  className="font-medium"
                />
              </div>
              <div className="flex gap-2">
                <Button type="submit" disabled={!last.trim() || searching} className="min-w-32 gap-2">
                  {searching ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
                  {searching ? "Searching…" : "Run Check"}
                </Button>
                {(hasQuery || last || first) && (
                  <Button type="button" variant="ghost" onClick={clearSearch} className="gap-1">
                    <X className="size-4" /> Clear
                  </Button>
                )}
              </div>
            </div>
            <p className="mt-3 text-[11px] text-muted-foreground leading-relaxed">
              Searches public Texas &amp; Oklahoma court and jail records simultaneously across{" "}
              {sources.length > 0 ? sources.length : "all"} sources.{" "}
              <strong className="text-foreground/70">Results are possible matches</strong> — confirm
              identity before acting.
            </p>
          </form>
        </div>

        {/* Disclaimer */}
        <div className="mt-4 flex gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
          <AlertTriangle className="mt-px size-4 shrink-0 text-amber-500" />
          <p className="leading-relaxed">
            <span className="font-semibold">For review purposes only.</span> These results are
            aggregated from public county sources and may be incomplete, outdated, or refer to a
            different individual with the same name. All matches must be independently verified
            against the official website of the relevant county before any decision is made.
          </p>
        </div>

        {healthError && (
          <div className="mt-4 flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
            <AlertTriangle className="size-4 shrink-0" />
            Cannot reach the search server. Make sure the backend is running, then reload.
          </div>
        )}

        {/* Results summary bar */}
        {hasQuery && (
          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1">
            <div className="text-sm font-semibold">
              {queryLabel}
            </div>
            <div className="text-muted-foreground flex items-center gap-1.5 text-sm">
              {searching && <Loader2 className="size-3.5 animate-spin" />}
              <span>{summary.responded}/{sources.length} sources</span>
              <span aria-hidden>·</span>
              <span>
                <span className="font-semibold text-foreground">
                  {summary.totalRecords.toLocaleString()}
                </span>{" "}
                {searching ? "records so far" : "possible matches"}
              </span>
              {!searching && summary.elapsed > 0 && (
                <>
                  <span aria-hidden>·</span>
                  <span>{(summary.elapsed / 1000).toFixed(1)}s</span>
                </>
              )}
            </div>
            {!searching && summary.problems > 0 && (
              <span className="flex items-center gap-1 text-sm text-amber-700">
                <AlertTriangle className="size-3.5" />
                {summary.problems} source{summary.problems === 1 ? "" : "s"} unavailable
              </span>
            )}
          </div>
        )}

        {hasQuery && sources.length > 0 && (
          <Results sources={sources} results={results} searching={searching} />
        )}

        {/* Pre-search empty state */}
        {!hasQuery && sources.length > 0 && (
          <div className="mt-10 text-center">
            <p className="text-sm text-muted-foreground">
              Enter a subject's last name above to search all {sources.length} sources simultaneously.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {sources.map((s) => (
                <span
                  key={s.id}
                  className="inline-flex items-center rounded border bg-card px-2.5 py-1 text-[11px] text-muted-foreground"
                >
                  {s.display_name}
                </span>
              ))}
            </div>
          </div>
        )}

        {sources.length === 0 && !healthError && (
          <p className="mt-6 text-center text-sm text-muted-foreground">Connecting to sources…</p>
        )}
      </main>

      <footer className="mx-auto max-w-5xl px-4 pb-10">
        <div className="border-t pt-4 text-[11px] text-muted-foreground leading-relaxed">
          <strong className="text-foreground/70">IMPORTANT:</strong> All results are{" "}
          <strong className="text-foreground/70">possible matches</strong> and require human review
          for identity confirmation — never an automated decision. Confirm identity against more than a
          name before acting.
        </div>
      </footer>
    </div>
  )
}
