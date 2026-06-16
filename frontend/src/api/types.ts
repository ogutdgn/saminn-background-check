// Contract types — re-exported from the OpenAPI-generated schema so they can't drift
// from the backend. Regenerate with `npm run gen:api` after the contract changes.
import type { components } from "./schema"

export type AdapterResult = components["schemas"]["AdapterResult"]
export type InmateRecord = components["schemas"]["InmateRecord"]
export type Charge = components["schemas"]["Charge"]
export type MatchInfo = components["schemas"]["MatchInfo"]
export type SearchQuery = components["schemas"]["SearchQuery"]
export type AdapterStatus = components["schemas"]["AdapterStatus"]
