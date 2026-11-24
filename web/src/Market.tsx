import { useEffect, useMemo, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, ExternalLink, RefreshCw } from 'lucide-react'
import DataTable, { ViewBadge, type Col } from './DataTable'
import { rupee } from './format'
import type { Result, Row } from './types'

export interface Quote {
  isin: string
  symbol: string | null
  price: number | null
  prev_close?: number | null
  change?: number | null
  change_pct?: number | null
  year_high?: number | null
  year_low?: number | null
  market_cap?: number | null
  live_value?: number | null
  day_pnl?: number | null
}
/** End-of-day NAV for a mutual fund (funds don't trade intraday). */
export interface MfNav {
  isin: string
  symbol: string | null
  nav: number | null
  prev_nav?: number | null
  nav_date?: string
  change?: number | null
  change_pct?: number | null
}
export interface Index { symbol: string; name: string; price: number | null; change: number | null; change_pct: number | null; spark: number[] }
export interface NewsItem { title: string; publisher?: string; url?: string; time?: string; symbol: string }

export interface Market {
  loading: boolean
  error: boolean
  indices: Index[]
  quotes: Record<string, Quote>
  mfNavs: Record<string, MfNav>
  news: NewsItem[]
  dayPnl: number
  dayPnlPct: number | null
  liveTotal: number
  asOf: Date | null
  refresh: () => void
}

const num = (v: unknown) => (typeof v === 'number' && isFinite(v) ? v : null)

export function useMarket(res: Result): Market {
  const [state, setState] = useState<Omit<Market, 'refresh' | 'dayPnl' | 'dayPnlPct' | 'liveTotal'>>({
    loading: true, error: false, indices: [], quotes: {}, mfNavs: {}, news: [], asOf: null,
  })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let dead = false
    setState((s) => ({ ...s, loading: true, error: false }))
    const hold = (res.demat || [])
      .filter((d) => d.isin)
      .map((d) => ({ isin: d.isin, name: d.name, units: num(d.units), ticker: d.advisory_ticker && d.advisory_ticker !== 'N/A' ? d.advisory_ticker : '' }))
    const mfIsins = [...new Set((res.mf || []).map((f) => String(f.isin || '').toUpperCase()).filter(Boolean))]
    ;(async () => {
      try {
        const [ov, q, mf] = await Promise.all([
          fetch('/api/market/overview').then((r) => r.json()).catch(() => []),
          fetch('/api/market/holdings', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ holdings: hold }) }).then((r) => r.json()).catch(() => []),
          mfIsins.length
            ? fetch('/api/market/mf', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ isins: mfIsins }) }).then((r) => r.json()).catch(() => [])
            : Promise.resolve([]),
        ])
        if (dead) return
        const quotes: Record<string, Quote> = {}
        if (Array.isArray(q)) {
          for (const x of q as Quote[]) if (x && x.isin) quotes[x.isin] = x
        }
        const mfNavs: Record<string, MfNav> = {}
        if (Array.isArray(mf)) {
          for (const x of mf as MfNav[]) if (x && x.isin) mfNavs[x.isin.toUpperCase()] = x
        }
        setState({ loading: false, error: false, indices: Array.isArray(ov) ? ov : [], quotes, mfNavs, news: [], asOf: new Date() })
        // news for the 5 biggest holdings + Nifty
        const top = [...(res.demat || [])].filter((d) => num(d.value)).sort((a, b) => b.value - a.value)
          .map((d) => quotes[d.isin]?.symbol).filter(Boolean).slice(0, 5) as string[]
        const n = await fetch(`/api/market/news?symbols=${encodeURIComponent(['^NSEI', ...top].join(','))}`).then((r) => r.json()).catch(() => [])
        if (!dead) setState((s) => ({ ...s, news: Array.isArray(n) ? n : [] }))
      } catch (err) {
        console.error('useMarket error:', err)
        if (!dead) setState((s) => ({ ...s, loading: false, error: true }))
      }
    })()
    return () => { dead = true }
  }, [res, tick])

  const { dayPnl, liveTotal, prevTotal } = useMemo(() => {
    let p = 0, live = 0, prev = 0
    for (const d of res.demat || []) {
      const q = state.quotes[d.isin]
      if (q?.live_value != null) { live += q.live_value; prev += q.live_value - (q.day_pnl ?? 0) }
      if (q?.day_pnl != null) p += q.day_pnl
    }
    return { dayPnl: p, liveTotal: live, prevTotal: prev }
  }, [res, state.quotes])

  return { ...state, dayPnl, liveTotal, dayPnlPct: prevTotal ? (dayPnl / prevTotal) * 100 : null, refresh: () => setTick((t) => t + 1) }
}

export const signCls = (v: number | null | undefined) => (v == null || !isFinite(v) ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '')
export const pct = (v: number | null | undefined) => (v == null || !isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`)
const signed = (v: number | null | undefined) => (v == null || !isFinite(v) ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${rupee(Math.abs(v))}`)
export { signed }

function Spark({ data, up }: { data?: number[]; up: boolean }) {
  if (!data || !Array.isArray(data) || data.length < 2) return <svg className="spark" />
  const w = 90, h = 28, min = Math.min(...data), max = Math.max(...data), r = max - min || 1
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - 2 - ((v - min) / r) * (h - 4)}`).join(' ')
  const c = up ? 'var(--buy)' : 'var(--sell)'
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-hidden>
      <polyline points={`0,${h} ${pts} ${w},${h}`} fill={c} opacity=".1" stroke="none" />
      <polyline points={pts} fill="none" stroke={c} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

export function MarketStrip({ m }: { m: Market }) {
  return (
    <section aria-label="Market today" className="marketwrap">
      <div className="mhead">
        <h2>Market today</h2>
        <span className="muted mmeta">
          {m.loading ? 'Loading live data…' : m.error ? 'Live data unavailable' : `Yahoo Finance · ${m.asOf?.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })} · may be delayed`}
          <button className="icon-link" onClick={m.refresh} aria-label="Refresh market data"><RefreshCw size={13} className={m.loading ? 'spin' : ''} /></button>
        </span>
      </div>
      <div className="mgrid">
        {(m.loading && !m.indices?.length ? Array.from({ length: 7 }) : (m.indices || [])).map((ix, i) =>
          ix ? (
            <div className="mcard" key={(ix as Index).symbol}>
              <div className="mname">{(ix as Index).name}</div>
              <div className="mprice tnum">{(ix as Index).price != null ? (ix as Index).price!.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'}</div>
              <div className={`mchg tnum ${signCls((ix as Index).change_pct)}`}>
                {(ix as Index).change_pct != null && ((ix as Index).change_pct! > 0 ? <ArrowUpRight size={13} /> : (ix as Index).change_pct! < 0 ? <ArrowDownRight size={13} /> : null)}
                {pct((ix as Index).change_pct)}
              </div>
              <Spark data={(ix as Index).spark} up={((ix as Index).change_pct ?? 0) >= 0} />
            </div>
          ) : <div className="mcard skel" key={i} />,
        )}
      </div>
    </section>
  )
}

const RangeBar = ({ q }: { q?: Quote }) => {
  if (!q || q.price == null || q.year_low == null || q.year_high == null || q.year_high === q.year_low) return <span className="muted">—</span>
  const p = Math.min(100, Math.max(0, ((q.price - q.year_low) / (q.year_high - q.year_low)) * 100))
  return (
    <div className="range" title={`52W low ${rupee(q.year_low)} · high ${rupee(q.year_high)}`}>
      <div className="range-bar"><span style={{ left: `${p}%` }} /></div>
      <div className="range-l tnum"><span>{q.year_low.toFixed(0)}</span><span>{q.year_high.toFixed(0)}</span></div>
    </div>
  )
}

function ago(t?: string) {
  if (!t) return ''
  const d = new Date(typeof t === 'number' ? (t as number) * 1000 : t)
  if (isNaN(+d)) return ''
  const h = (Date.now() - +d) / 36e5
  return h < 1 ? `${Math.max(1, Math.round(h * 60))}m ago` : h < 48 ? `${Math.round(h)}h ago` : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

/** Statement mutual fund rows plus latest NAV, NAV date, day change and current value. */
export function withMfNav(res: Result, navs: Record<string, MfNav> | undefined): Row[] {
  return (res.mf || []).map((f) => {
    const n = navs?.[String(f.isin || '').toUpperCase()]
    const u = typeof f.units === 'number' ? f.units : null
    const nav = n?.nav ?? null
    return {
      ...f, latest_nav: nav, nav_date: n?.nav_date ?? null, change_pct: n?.change_pct ?? null,
      day_pnl: u != null && n?.change != null ? u * n.change : null,
      current_value: u != null && nav != null ? u * nav : null,
    }
  })
}
export const navFmt = (v: number | null) => (v == null ? '—' : `₹${v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`)
export const dateFmt = (v: string | null) => (v ? new Date(v).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—')

export function MarketTab({ res, m }: { res: Result; m: Market }) {
  const rows: Row[] = useMemo(() => (res.demat || []).map((d) => {
    const q = m.quotes?.[d.isin]
    return { ...d, symbol: q?.symbol ?? null, ltp: q?.price ?? null, change_pct: q?.change_pct ?? null, day_pnl: q?.day_pnl ?? null, live_value: q?.live_value ?? null, _q: q }
  }), [res, m.quotes])
  const live = rows.filter((r) => r.ltp != null)
  const movers = [...live].filter((r) => r.change_pct != null).sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0))
  const gain = movers.slice(0, 3), lose = movers.slice(-3).reverse().filter((r) => r.change_pct < 0)
  const name = (v: string) => String(v ?? '').split('#')[0].trim()

  const mfRows = useMemo(() => withMfNav(res, m.mfNavs), [res, m.mfNavs])
  const mfCols: Col[] = [
    { key: 'scheme_name', label: 'Scheme', render: (v) => <span title={v}>{String(v ?? '').replace(/^[A-Z0-9]{2,6} - /, '')}</span> },
    ...(mfRows.some((r) => r.owner) ? [{ key: 'owner', label: 'Owner' } as Col] : []),
    { key: 'units', label: 'Units', numeric: true, render: (v) => (typeof v === 'number' ? v.toLocaleString('en-IN', { maximumFractionDigits: 3 }) : '—') },
    { key: 'latest_nav', label: 'Latest NAV', numeric: true, render: navFmt },
    { key: 'nav_date', label: 'NAV date', render: dateFmt },
    { key: 'change_pct', label: 'Day %', numeric: true, render: (v) => <span className={signCls(v)}>{pct(v)}</span> },
    { key: 'day_pnl', label: 'Day P&L', numeric: true, render: (v) => <span className={signCls(v)}>{signed(v)}</span> },
    { key: 'current_value', label: 'Current value', numeric: true, render: (v) => rupee(v) },
    { key: 'value', label: 'Statement value', numeric: true, render: (v) => rupee(v) },
  ]

  const cols: Col[] = [
    { key: 'name', label: 'Security', render: (v) => <span title={v}>{name(v)}</span> },
    { key: 'advisory_view', label: 'View', render: (v) => <ViewBadge v={v} /> },
    { key: 'ltp', label: 'LTP', numeric: true, render: (v) => rupee(v) },
    { key: 'change_pct', label: 'Day %', numeric: true, render: (v) => <span className={signCls(v)}>{pct(v)}</span> },
    { key: 'day_pnl', label: 'Day P&L', numeric: true, render: (v) => <span className={signCls(v)}>{signed(v)}</span> },
    { key: 'live_value', label: 'Live value', numeric: true, render: (v) => rupee(v) },
    { key: '_q', label: '52-week range', render: (_v, r) => <RangeBar q={r._q} /> },
    { key: 'symbol', label: 'Yahoo' },
  ]

  return (
    <div className="mtab">
      {live.length > 0 && (
        <div className="row">
          <div className="card">
            <h2>Top gainers</h2>
            {gain.map((r) => <MoverRow key={r.isin} r={r} name={name(r.name)} />)}
          </div>
          <div className="card">
            <h2>Top losers</h2>
            {lose.length ? lose.map((r) => <MoverRow key={r.isin} r={r} name={name(r.name)} />) : <p className="muted">No holdings are down today.</p>}
          </div>
        </div>
      )}

      <h2 style={{ margin: '22px 0 12px' }}>Holdings, live</h2>
      <DataTable rows={rows} cols={cols} empty={m.loading ? 'Fetching live prices…' : 'No live prices found.'} />
      <p className="muted" style={{ fontSize: 12, margin: '8px 0 0' }}>
        {live.length} of {rows.length} demat holdings matched to a Yahoo Finance symbol. Bonds, SGBs and delisted securities usually have no live quote.
      </p>

      <h2 style={{ margin: '26px 0 12px' }}>Mutual funds, latest NAV</h2>
      <DataTable rows={mfRows} cols={mfCols} empty={m.loading ? 'Fetching NAVs…' : 'No mutual funds in this statement.'} />
      <p className="muted" style={{ fontSize: 12, margin: '8px 0 0' }}>
        {mfRows.filter((r) => r.latest_nav != null).length} of {mfRows.length} funds matched on Yahoo Finance. Funds don&apos;t trade intraday: NAV is published once a day after market close, so each row shows its own NAV date. Day change compares with the previous NAV.
      </p>

      <h2 style={{ margin: '26px 0 12px' }}>Market &amp; holdings news</h2>
      <div className="card newslist">
        {m.news.length ? m.news.map((n, i) => (
          <a key={i} className="newsitem" href={n.url} target="_blank" rel="noreferrer noopener">
            <div>
              <div className="nt">{n.title}</div>
              <div className="muted nm">{n.publisher} · {ago(n.time)}{n.symbol && n.symbol !== '^NSEI' ? ` · ${n.symbol.replace(/\.(NS|BO)$/, '')}` : ''}</div>
            </div>
            <ExternalLink size={14} />
          </a>
        )) : <p className="muted" style={{ margin: 0 }}>{m.loading ? 'Loading headlines…' : 'No recent headlines.'}</p>}
      </div>
    </div>
  )
}

const MoverRow = ({ r, name }: { r: Row; name: string }) => (
  <div className="mover">
    <span className="mn" title={name}>{name}</span>
    <span className="tnum">{rupee(r.ltp)}</span>
    <span className={`tnum ${signCls(r.change_pct)}`}>{pct(r.change_pct)}</span>
  </div>
)
