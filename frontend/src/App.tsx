import { useEffect, useRef, useState, type FormEvent } from "react"
import type { AdapterResult } from "@/api/types"
import { search } from "@/api/search"
import { SourceCard } from "@/components/SourceCard"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

export default function App() {
  const [sources, setSources] = useState<string[]>([])
  const [results, setResults] = useState<Record<string, AdapterResult>>({})
  const [searching, setSearching] = useState(false)
  const [last, setLast] = useState("")
  const [first, setFirst] = useState("")
  const abortRef = useRef<AbortController | null>(null)

  // discover which sources are live so we can show a card (pending) for each up front
  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => setSources(d.sources ?? []))
      .catch(() => setSources([]))
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const lastName = last.trim()
    if (!lastName) return
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    setResults({})
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

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Background Search</h1>
        <p className="text-muted-foreground text-sm">
          The Samaritan Inn intake · public records, streamed live · possible matches for human
          review.
        </p>
      </header>

      <form onSubmit={onSubmit} className="mb-6 flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <label className="text-xs font-medium" htmlFor="last">
            Last name
          </label>
          <Input
            id="last"
            value={last}
            onChange={(e) => setLast(e.target.value)}
            placeholder="Smith"
            className="w-48"
            autoFocus
          />
        </div>
        <div className="grid gap-1.5">
          <label className="text-xs font-medium" htmlFor="first">
            First name <span className="text-muted-foreground">(optional)</span>
          </label>
          <Input
            id="first"
            value={first}
            onChange={(e) => setFirst(e.target.value)}
            placeholder="John"
            className="w-48"
          />
        </div>
        <Button type="submit" disabled={!last.trim() || searching}>
          {searching ? "Searching…" : "Search"}
        </Button>
      </form>

      {sources.length === 0 ? (
        <p className="text-muted-foreground text-sm">No sources enabled.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {sources.map((id) => (
            <SourceCard key={id} id={id} result={results[id]} pending={searching} />
          ))}
        </div>
      )}

      <footer className="text-muted-foreground mt-8 border-t pt-4 text-xs">
        Results are <strong>possible matches</strong> for a person to review — never an automated
        decision. Confirm identity against more than a name before acting.
      </footer>
    </div>
  )
}
