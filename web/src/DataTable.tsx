import { useMemo, useState, type ReactNode } from 'react'
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { Row } from './types'

export interface Col {
  key: string
  label: string
  numeric?: boolean
  render?: (v: any, row: Row) => ReactNode
}

export const ViewBadge = ({ v }: { v: string }) => {
  const k = String(v || '').toUpperCase()
  return <span className={`badge ${['BUY', 'ADD', 'HOLD', 'TRIM', 'SELL'].includes(k) ? `b-${k}` : 'b-NC'}`}>{v || 'Not Covered'}</span>
}

export default function DataTable({ rows, cols, empty, maxHeight = 520 }: { rows: Row[]; cols: Col[]; empty: string; maxHeight?: number }) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null)
  const sorted = useMemo(() => {
    if (!sort) return rows
    const { key, dir } = sort
    return [...rows].sort((a, b) => {
      const x = a[key], y = b[key]
      if (x == null) return 1
      if (y == null) return -1
      return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))) * dir
    })
  }, [rows, sort])

  if (!rows.length) return <div className="text-muted-foreground py-12 text-center text-sm text-[var(--subtle)]">{empty}</div>

  return (
    <div className="overflow-auto rounded-[10px] border border-[var(--border)] bg-[var(--surface)]" style={{ maxHeight }}>
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-[var(--surface-2)]">
          <TableRow>
            {cols.map((c) => {
              const active = sort?.key === c.key
              const Icon = !active ? ChevronsUpDown : sort!.dir === 1 ? ArrowUp : ArrowDown
              return (
                <TableHead
                  key={c.key}
                  aria-sort={active ? (sort!.dir === 1 ? 'ascending' : 'descending') : 'none'}
                  className={cn('text-[var(--subtle)] cursor-pointer text-[11px] font-semibold uppercase tracking-wider whitespace-nowrap select-none', c.numeric && 'text-right')}
                  onClick={() => setSort((s) => (s?.key === c.key ? { key: c.key, dir: s.dir === 1 ? -1 : 1 } : { key: c.key, dir: 1 }))}
                >
                  <span className={cn('inline-flex items-center gap-1', c.numeric && 'flex-row-reverse')}>
                    {c.label}
                    <Icon className={cn('size-3', active ? 'text-foreground' : 'opacity-40')} />
                  </span>
                </TableHead>
              )
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((r, i) => (
            <TableRow key={i}>
              {cols.map((c) => (
                <TableCell key={c.key} className={cn('align-top', c.numeric && 'tnum text-right')}>
                  {c.render ? c.render(r[c.key], r) : (r[c.key] ?? '—')}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
