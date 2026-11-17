export type Row = Record<string, any>
export interface Result {
  filename: string
  statement_period: { from?: string; to?: string }
  investor: { name: string; pan: string; details: string[][] }
  totals: { total_portfolio_value: number; demat_value: number; mf_value: number }
  demat: Row[]
  mf: Row[]
  transactions: Row[]
  categories: [string, number, number | string][]
  advisory: { holdings: Row[]; summary: Record<string, { count: number; value: number }> }
  enriched_json: unknown
  advisory_status: { loaded: boolean; count: number }
  exports: { xlsx: string; csv: string }
}
