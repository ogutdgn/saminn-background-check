import type { AdapterResult, InmateRecord } from "@/api/types"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
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
        {records.map((rec, i) => (
          <RecordRow key={i} rec={rec} />
        ))}
      </CardContent>
    </Card>
  )
}

function RecordRow({ rec }: { rec: InmateRecord }) {
  const meta = [rec.year_of_birth ? `b. ${rec.year_of_birth}` : null, rec.sex]
    .filter(Boolean)
    .join(" · ")
  const charges = rec.charges ?? []
  const matched = rec.matched_on ?? []

  return (
    <div className="rounded-md border p-3">
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
    </div>
  )
}
