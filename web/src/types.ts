export type Row = Record<string, any>
export interface Result {
  filename: string
  statement_period: { from?: string; to?: string }
  investor: { name: string; pan: string; details: (string | number)[][] }
  totals: { total_portfolio_value: number; demat_value: number; mf_value: number; nps_value?: number }
  demat: Row[]
  mf: Row[]
  transactions: Row[]
  categories: [string, number, number | string][]
  advisory: { holdings: Row[]; summary: Record<string, { count: number; value: number }> }
  enriched_json: unknown
  advisory_status: { loaded: boolean; count: number }
  exports: { xlsx: string; csv: string }
}

/** Response of POST /api/parse-multi: one consolidated result plus each member's own. */
export interface FamilyResult {
  family: Result
  members: Result[]
  warnings: string[]
}
