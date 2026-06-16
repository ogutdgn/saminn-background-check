import { useEffect, useMemo, useRef, useState, type FormEvent } from "react"
import { Loader2, Search, ShieldCheck, X } from "lucide-react"
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

  // Discover the enabled sources (with display name + photo capability) so we can render a card
  // per source up front — no per-county knowledge baked into the UI.
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
    await search(
      { last: lastName, first: first.trim() || undefined, max_results: 25 },
      {
        onResult: (r) => setResults((prev) => ({ ...prev, [r.source]: r })),
        onDone: () => setSearching(false),
        onError: () => setSearching(false),
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
    <div className="bg-muted/30 min-h-screen">
      <header className="bg-background border-b">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-4">
          <div className="bg-primary text-primary-foreground flex size-9 items-center justify-center rounded-lg">
            <ShieldCheck className="size-5" />
          </div>
          <div className="min-w-0">
            <h1 className="font-heading text-lg leading-tight font-semibold">Background Search</h1>
            <p className="text-muted-foreground text-xs">The Samaritan Inn · intake</p>
          </div>
          {sources.length > 0 && (
            <div className="text-muted-foreground ml-auto hidden text-xs sm:block">
              {sources.length} public records {sources.length === 1 ? "source" : "sources"}
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        <form
          onSubmit={onSubmit}
          className="bg-background ring-foreground/5 rounded-xl border p-4 shadow-sm ring-1"
        >
          <div className="flex flex-wrap items-end gap-3">
            <div className="grid grow basis-40 gap-1.5">
              <label htmlFor="last" className="text-xs font-medium">
                Last name
              </label>
              <Input
                id="last"
                value={last}
                onChange={(e) => setLast(e.target.value)}
                placeholder="Smith"
                autoFocus
                autoComplete="off"
              />
            </div>
            <div className="grid grow basis-40 gap-1.5">
              <label htmlFor="first" className="text-xs font-medium">
                First name <span className="text-muted-foreground">(optional)</span>
              </label>
              <Input
                id="first"
                value={first}
                onChange={(e) => setFirst(e.target.value)}
                placeholder="John"
                autoComplete="off"
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={!last.trim() || searching} className="min-w-28">
                {searching ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
                {searching ? "Searching…" : "Search"}
              </Button>
              {(hasQuery || last || first) && (
                <Button type="button" variant="ghost" onClick={clearSearch}>
                  <X className="size-4" /> Clear
                </Button>
              )}
            </div>
          </div>
          <p className="text-muted-foreground mt-2.5 text-xs">
            Searches public Texas &amp; Oklahoma court and jail records by name — all sources at
            once. Results are <strong className="text-foreground/80">possible matches</strong> for a
            person to review.
          </p>
        </form>

        {healthError && (
          <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            Couldn't reach the search server. Make sure the backend is running, then reload.
          </div>
        )}

        {hasQuery && (
          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <div>
              Results for <span className="font-semibold">{queryLabel}</span>
            </div>
            <div className="text-muted-foreground flex items-center gap-1.5">
              {searching && <Loader2 className="size-3.5 animate-spin" />}
              <span>
                {summary.responded}/{sources.length} sources
              </span>
              <span aria-hidden>·</span>
              <span>
                <span className="text-foreground font-medium">
                  {summary.totalRecords.toLocaleString()}
                </span>{" "}
                {searching ? "matches so far" : "possible matches"}
              </span>
              {!searching && summary.elapsed > 0 && (
                <>
                  <span aria-hidden>·</span>
                  <span>{(summary.elapsed / 1000).toFixed(1)} s</span>
                </>
              )}
            </div>
            {!searching && summary.problems > 0 && (
              <span className="text-amber-700">
                {summary.problems} source{summary.problems === 1 ? "" : "s"} unavailable
              </span>
            )}
          </div>
        )}

        {hasQuery && sources.length > 0 && (
          <Results sources={sources} results={results} searching={searching} />
        )}

        {!hasQuery && sources.length > 0 && (
          <div className="mt-8 text-center">
            <p className="text-muted-foreground text-sm">
              Enter a last name above to search all {sources.length} sources at once.
            </p>
            <div className="mt-3 flex flex-wrap justify-center gap-1.5">
              {sources.map((s) => (
                <span
                  key={s.id}
                  className="text-muted-foreground bg-background inline-flex items-center rounded-full border px-2.5 py-1 text-xs"
                >
                  {s.display_name}
                </span>
              ))}
            </div>
          </div>
        )}
        {sources.length === 0 && !healthError && (
          <p className="text-muted-foreground mt-6 text-center text-sm">Loading sources…</p>
        )}
      </main>

      <footer className="mx-auto max-w-5xl px-4 pb-10">
        <div className="text-muted-foreground border-t pt-4 text-xs">
          Results are <strong className="text-foreground">possible matches</strong> for a person to
          review — never an automated decision. Confirm identity against more than a name before
          acting.
        </div>
      </footer>
    </div>
  )
}
