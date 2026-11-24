import { useEffect, useRef, useState } from 'react'
import { useTheme } from 'next-themes'
import { AnimatePresence, motion } from 'motion/react'
import { toast } from 'sonner'
import { Bar, BarChart, Cell, LabelList, Pie, PieChart, XAxis, YAxis } from 'recharts'
import { AlertCircle, CheckCircle2, FileJson, FileSpreadsheet, FileText, Loader2, Moon, RotateCcw, Sun, UploadCloud } from 'lucide-react'

import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart'
import { Toaster } from '@/components/ui/sonner'

import { ErrorBoundary } from './ErrorBoundary'
import DataTable, { ViewBadge, type Col } from './DataTable'
import { CountUp, ease } from './motion'
import { b64ToBytes, compact, download, rupee, units } from './format'
import type { FamilyResult, Result, Row } from './types'
import { MarketStrip, MarketTab, dateFmt, navFmt, pct, signCls, signed, useMarket, withMfNav } from './Market'

const VIEWS = ['BUY', 'ADD', 'HOLD', 'TRIM', 'SELL', 'Not Covered']
const VIEW_COLOR: Record<string, string> = {
  BUY: '#15803d', ADD: '#0f766e', HOLD: '#d9a406', TRIM: '#c2410c', SELL: '#b91c1c', 'Not Covered': '#94a3b8',
}

const Wordmark = () => <span className="wordmark">CREST</span>

const Kpi = ({ label, value, sub, num, fmt, tone }: { label: string; value: string; sub?: string; num?: number; fmt?: (n: number) => string; tone?: string }) => (
  <div className="kpi">
    <div className="l">{label}</div>
    <div className={`v ${tone ?? ''}`}>{num != null && fmt ? <CountUp value={num} format={fmt} /> : value}</div>
    {sub && <div className="s">{sub}</div>}
  </div>
)

export default function App() {
  const { theme, setTheme } = useTheme()
  const [items, setItems] = useState<{ file: File; password: string }[]>([])
  const [adv, setAdv] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [single, setSingle] = useState<Result | null>(null)
  const [fam, setFam] = useState<FamilyResult | null>(null)
  const [sel, setSel] = useState(-1) // -1 = whole family, otherwise member index
  const [over, setOver] = useState(false)
  const [status, setStatus] = useState<{ loaded: boolean; count: number } | null>(null)
  const pdfRef = useRef<HTMLInputElement>(null)
  const advRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetch('/api/advisory/status').then((r) => r.json()).then(setStatus).catch(() => setStatus(null))
  }, [])

  const MAX_FILES = 10
  function addFiles(list: FileList | File[] | null) {
    if (!list) return
    const pdfs = Array.from(list).filter((f) => /\.pdf$/i.test(f.name) || f.type === 'application/pdf')
    if (!pdfs.length) return
    setItems((cur) => {
      const names = new Set(cur.map((i) => `${i.file.name}:${i.file.size}`))
      const fresh = pdfs.filter((f) => !names.has(`${f.name}:${f.size}`)).map((file) => ({ file, password: '' }))
      return [...cur, ...fresh].slice(0, MAX_FILES)
    })
  }

  async function parse() {
    if (!items.length) return
    setBusy(true); setError('')
    const fd = new FormData()
    const multi = items.length > 1
    if (multi) items.forEach((i) => { fd.append('pdfs', i.file); fd.append('passwords', i.password) })
    else { fd.append('pdf', items[0].file); fd.append('password', items[0].password) }
    if (adv) fd.append('advisory', adv)
    try {
      const r = await fetch(multi ? '/api/parse-multi' : '/api/parse', { method: 'POST', body: fd })
      const body = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(body.detail || `Request failed (${r.status})`)
      if (multi) { setFam(body); setSel(-1) } else setSingle(body)
      toast.success(multi ? `${items.length} statements consolidated` : 'Statement parsed')
    } catch (e) {
      const m = e instanceof Error ? e.message : 'Something went wrong.'
      setError(m); toast.error(m)
    } finally { setBusy(false) }
  }

  const res: Result | null = fam ? (sel < 0 ? fam.family : fam.members[sel] ?? fam.family) : single
  const reset = () => { setSingle(null); setFam(null); setSel(-1); setItems([]) }
  const advStatus = res?.advisory_status ?? status
  const dark = theme === 'dark'

  return (
    <>
      <header className="topbar">
        <div className="topbar-in">
          <Wordmark />
          <span className="tag">CAS Parser &amp; Equity Advisory</span>
          <span className="spacer" />
          <button className="icon-btn" onClick={() => setTheme(dark ? 'light' : 'dark')} aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}>
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>
      <Toaster position="bottom-right" />

      <main>
        <AnimatePresence mode="wait">
          {!res ? (
            <motion.div key="up" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} transition={{ duration: 0.35, ease }}>
              <h1 className="hero">Parse a statement</h1>
              <p className="muted lead">Upload a CDSL, NSDL, CAMS or KFintech CAS PDF, or several (one per family member) to see one consolidated portfolio. Holdings are cross-checked against the CREST equity advisory list. Nothing is stored on the server.</p>
              <div className="upload-grid">
                <motion.div
                  whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }} transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  className={`drop ${over ? 'over' : ''}`}
                  role="button" tabIndex={0}
                  onClick={() => pdfRef.current?.click()}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && pdfRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setOver(true) }}
                  onDragLeave={() => setOver(false)}
                  onDrop={(e) => { e.preventDefault(); setOver(false); addFiles(e.dataTransfer.files) }}
                >
                  <UploadCloud size={32} strokeWidth={1.5} color="var(--brand)" />
                  <div className="big">{items.length ? 'Add more statements' : 'Drop CAS PDFs here, or click to browse'}</div>
                  <div className="muted">One PDF per family member · up to {MAX_FILES} files · 25 MB each</div>
                  <input ref={pdfRef} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
                </motion.div>
                <div className="card">
                  {items.length === 0 && <div className="muted">No statements added yet.</div>}
                  {items.map((it, idx) => (
                    <div key={`${it.file.name}:${it.file.size}`} style={{ marginBottom: 16 }}>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                        <FileText size={15} />
                        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={it.file.name}>{it.file.name}</span>
                        <span className="muted">{(it.file.size / 1024).toFixed(0)} KB</span>
                        <button className="icon-btn" style={{ width: 28, height: 28, flexShrink: 0 }} aria-label={`Remove ${it.file.name}`} onClick={() => setItems((cur) => cur.filter((_, j) => j !== idx))}>×</button>
                      </div>
                      <input
                        type="password" autoComplete="off" placeholder="Password (leave blank if none)" aria-label={`Password for ${it.file.name}`}
                        value={it.password}
                        onChange={(e) => setItems((cur) => cur.map((c, j) => (j === idx ? { ...c, password: e.target.value } : c)))}
                        onKeyDown={(e) => e.key === 'Enter' && parse()}
                      />
                    </div>
                  ))}
                  <div style={{ margin: '16px 0 8px' }}>
                    <label className="field">Advisory database</label>
                    <span className={`chip ${advStatus?.loaded || adv ? 'ok' : ''}`}>
                      {adv ? adv.name : advStatus?.loaded ? `${advStatus.count} stocks loaded` : 'Not loaded'}
                    </span>{' '}
                    <button className="btn" style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => advRef.current?.click()}>Replace</button>
                    <input ref={advRef} type="file" accept=".xlsx" hidden onChange={(e) => setAdv(e.target.files?.[0] ?? null)} />
                  </div>
                  <motion.button whileTap={{ scale: 0.97 }} className={`btn primary ${busy ? 'shimmer' : ''}`} disabled={!items.length || busy} onClick={parse}>
                    {busy ? <><Loader2 size={16} className="spin" /> Parsing…</> : items.length > 1 ? `Parse & consolidate ${items.length} statements` : 'Parse statement'}
                  </motion.button>
                </div>
              </div>
              {error && <div className="alert" role="alert"><AlertCircle size={16} style={{ verticalAlign: -3 }} /> {error}</div>}
            </motion.div>
          ) : (
            <motion.div key="dash" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
              <ErrorBoundary>
                <Dashboard
                  res={res} onReset={reset}
                  owners={fam ? fam.members.map((m) => m.investor.name) : undefined}
                  sel={sel} onSel={setSel} warnings={fam?.warnings}
                />
              </ErrorBoundary>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </>
  )
}

function Dashboard({ res, onReset, owners, sel, onSel, warnings }: {
  res: Result; onReset: () => void
  owners?: string[]; sel: number; onSel: (i: number) => void; warnings?: string[]
}) {
  const [tab, setTab] = useState('advisory')
  const m = useMarket(res)
  const [filter, setFilter] = useState('All')
  const t = res.totals
  const rest = t.total_portfolio_value - t.demat_value - t.mf_value
  const other = rest > 1 ? rest : 0
  const alloc = [
    { name: 'Demat', value: t.demat_value, fill: '#1e3a8a' },
    { name: 'Mutual Funds', value: t.mf_value, fill: '#60a5fa' },
    ...(other > 0 ? [{ name: 'Other', value: other, fill: '#cbd5e1' }] : []),
  ].filter((d) => d.value > 0)
  const allocConfig = { value: { label: 'Value' } } satisfies ChartConfig
  const distConfig = { count: { label: 'Stocks' } } satisfies ChartConfig
  const period = res.statement_period.from ? `${res.statement_period.from} to ${res.statement_period.to}` : ''
  const holdings = res.advisory.holdings
  const summary = res.advisory.summary
  const dist = VIEWS.map((v) => ({ name: v, count: summary[v]?.count ?? 0, value: Number(summary[v]?.value ?? 0) }))
  const allocTotal = alloc.reduce((a, d) => a + d.value, 0) || 1
  const top = [...res.demat]
    .filter((d) => typeof d.value === 'number' && d.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)
    .map((d) => ({ name: String(d.name ?? '').split('#')[0].trim().replace(/ (LIMITED|LTD\.?)$/i, ''), value: d.value as number, view: d.advisory_view as string }))
  const topConfig = { value: { label: 'Value' } } satisfies ChartConfig
  const familyView = res.demat.some((d) => d.owner) || res.mf.some((d) => d.owner)
  const ownerByIsin: Record<string, string> = {}
  res.demat.forEach((d) => { if (d.owner) ownerByIsin[String(d.isin).toUpperCase()] = d.owner })
  const ownerCol: Col[] = familyView ? [{ key: 'owner', label: 'Owner' }] : []
  const withLive: Row[] = (holdings || []).map((h) => ({
    ...h, owner: ownerByIsin[String(h.isin).toUpperCase()] ?? '',
    ltp: m.quotes?.[h.isin]?.price ?? null, change_pct: m.quotes?.[h.isin]?.change_pct ?? null,
  }))
  const shown = filter === 'All' ? withLive : withLive.filter((h) => h.advisory_view === filter)

  const view = (v: string) => <ViewBadge v={v} />
  const secName = (v: string) => <span title={v}>{String(v ?? '—').split('#')[0].trim()}</span>

  const advCols: Col[] = [
    { key: 'demat_stock_name', label: 'Security (demat)', render: secName },
    ...ownerCol,
    { key: 'advisory_view', label: 'View', render: view },
    { key: 'advisory_ticker', label: 'Ticker' },
    { key: 'advisory_stock_name', label: 'Advisory security' },
    { key: 'units', label: 'Units', numeric: true, render: units },
    { key: 'ltp', label: 'LTP', numeric: true, render: rupee },
    { key: 'change_pct', label: 'Day %', numeric: true, render: (v) => <span className={signCls(v)}>{pct(v)}</span> },
    { key: 'value', label: 'Value', numeric: true, render: rupee },
    { key: 'isin', label: 'ISIN' },
    { key: 'match_type', label: 'Match' },
  ]
  const dematCols: Col[] = [
    { key: 'name', label: 'Security', render: secName },
    ...ownerCol,
    { key: 'advisory_view', label: 'View', render: view },
    { key: 'advisory_ticker', label: 'Ticker' },
    { key: 'units', label: 'Units', numeric: true, render: units },
    { key: 'value', label: 'Value', numeric: true, render: rupee },
    { key: 'category', label: 'Category' },
    { key: 'isin', label: 'ISIN' },
    { key: 'dp_name', label: 'DP' },
  ]
  const mfCols: Col[] = [
    { key: 'scheme_name', label: 'Scheme' },
    ...ownerCol,
    { key: 'amc', label: 'AMC' },
    { key: 'units', label: 'Units', numeric: true, render: units },
    { key: 'nav', label: 'Stmt NAV', numeric: true, render: rupee },
    { key: 'value', label: 'Stmt value', numeric: true, render: rupee },
    { key: 'cost', label: 'Cost', numeric: true, render: rupee },
    { key: 'latest_nav', label: 'Latest NAV', numeric: true, render: navFmt },
    { key: 'nav_date', label: 'NAV date', render: dateFmt },
    { key: 'change_pct', label: 'Day %', numeric: true, render: (v) => <span className={signCls(v)}>{pct(v)}</span> },
    { key: 'current_value', label: 'Current value', numeric: true, render: (v) => rupee(v) },
    { key: 'folio_number', label: 'Folio' },
  ]
  const txCols: Col[] = res.transactions[0]
    ? Object.keys(res.transactions[0]).map((k) => ({
        key: k, label: k.replace(/_/g, ' '),
        numeric: ['amount', 'nav', 'units', 'balance'].includes(k),
        render: k === 'amount' || k === 'nav' ? rupee : k === 'units' || k === 'balance' ? units : undefined,
      }))
    : []

  const base = res.filename || 'CAS_Report'
  const save = (label: string, name: string, mime: string, data: BlobPart) => { toast.success(`${label} downloaded`); download(name, mime, data) }
  const tabs = [
    ['advisory', 'Equity advisory'], ['market', 'Live market'], ['demat', 'Demat'], ['mf', 'Mutual funds'],
    ['txn', 'Transactions'], ['inv', 'Investor & summary'],
  ]

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h1>Portfolio overview</h1>
          <span className="chip ok"><CheckCircle2 size={14} /> Parsed {period && `· ${period}`}</span>{' '}
          <span className="chip">
            {owners && sel < 0 ? `Family · ${owners.length} members` : `${res.investor.name} · PAN ${res.investor.pan}`}
          </span>
        </div>
        <span className="spacer" />
        <button className="btn" onClick={onReset}><RotateCcw size={15} /> New statement</button>
      </div>

      {owners && (
        <div role="tablist" aria-label="Family member"
          style={{ display: 'flex', gap: 4, flexWrap: 'wrap', padding: 4, margin: '14px 0', width: 'fit-content', maxWidth: '100%', border: '1px solid var(--border)', borderRadius: 'var(--radius)', background: 'var(--surface)' }}>
          {[{ label: `Family (${owners.length})`, i: -1 }, ...owners.map((o, i) => ({ label: o, i }))].map((o) => (
            <button key={o.i} role="tab" aria-selected={sel === o.i}
              style={{
                padding: '7px 14px', border: 0, borderRadius: 6, cursor: 'pointer', font: 'inherit', fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap',
                background: sel === o.i ? 'var(--ink)' : 'transparent', color: sel === o.i ? 'var(--on-ink)' : 'inherit',
              }}
              onClick={() => onSel(o.i)}>
              {o.label}
            </button>
          ))}
        </div>
      )}
      {warnings?.map((w, i) => (
        <div key={i} role="status" style={{ margin: '0 0 12px', padding: '10px 14px', borderRadius: 'var(--radius)', fontSize: 13, background: 'rgba(217,164,6,.12)', border: '1px solid rgba(217,164,6,.45)' }}>
          <AlertCircle size={15} style={{ verticalAlign: -3, color: '#d9a406' }} /> {w}
        </div>
      ))}

      <div className="kpis">
        <Kpi label="Total portfolio value" value="" num={t.total_portfolio_value} fmt={rupee} sub={compact(t.total_portfolio_value)} />
        <Kpi label="Demat holdings" value="" num={t.demat_value} fmt={rupee} sub={`${res.demat.length} items`} />
        <Kpi label="Mutual funds" value="" num={t.mf_value} fmt={rupee} sub={`${res.mf.length} schemes`} />
        <Kpi label="Today's change" value={m.loading ? '…' : m.dayPnl ? signed(m.dayPnl) : '—'} tone={signCls(m.dayPnl)} sub={m.dayPnlPct != null ? `${pct(m.dayPnlPct)} on live demat equities` : m.loading ? 'Fetching live prices' : 'Live prices unavailable'} />
      </div>

      <MarketStrip m={m} />

      <div className="row">
        <div className="card">
          <h2>Allocation</h2>
          <div className="chart-split">
            <ChartContainer config={allocConfig} className="h-[220px] w-[220px]">
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent hideLabel nameKey="name" formatter={(v, n) => <span style={{ display: 'flex', width: '100%', justifyContent: 'space-between', gap: 16 }}><span>{n}</span><b className="tnum">{rupee(Number(v))}</b></span>} />} />
                <Pie data={alloc} dataKey="value" nameKey="name" innerRadius={72} outerRadius={104} cornerRadius={8} paddingAngle={4} stroke="none" startAngle={90} endAngle={-270}>
                  {alloc.map((d) => <Cell key={d.name} fill={d.fill} />)}
                </Pie>
                <text x="50%" y="46%" textAnchor="middle" dominantBaseline="middle" fill="var(--subtle)" style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase' }}>Total</text>
                <text x="50%" y="57%" textAnchor="middle" dominantBaseline="middle" fill="var(--text)" style={{ fontSize: 22, fontWeight: 700 }}>{compact(t.total_portfolio_value)}</text>
              </PieChart>
            </ChartContainer>
            <div className="legend">
              {alloc.map((d) => (
                <div className="legend-item" key={d.name}>
                  <span className="legend-dot" style={{ background: d.fill }} />
                  <span className="legend-name">{d.name}</span>
                  <span className="legend-pct tnum">{((d.value / allocTotal) * 100).toFixed(1)}%</span>
                  <span className="legend-val tnum">{rupee(d.value)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="card">
          <h2>Advisory view (stocks)</h2>
          <ChartContainer config={distConfig} className="h-[240px] w-full">
            <BarChart data={dist} layout="vertical" margin={{ left: 4, right: 36, top: 4, bottom: 4 }} barCategoryGap={10}>
              <YAxis dataKey="name" type="category" tickLine={false} axisLine={false} width={86} tick={{ fontSize: 12, fontWeight: 600 }} />
              <XAxis dataKey="count" type="number" hide domain={[0, 'dataMax']} />
              <ChartTooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltipContent hideLabel formatter={(v, _n, item) => <span style={{ display: 'flex', width: '100%', justifyContent: 'space-between', gap: 16 }}><span>{(item?.payload as any)?.name}: {String(v)}</span><b className="tnum">{rupee((item?.payload as any)?.value)}</b></span>} />} />
              <Bar dataKey="count" radius={[0, 8, 8, 0]} barSize={20} background={{ fill: 'var(--surface-2)', radius: 8 }}>
                {dist.map((d) => <Cell key={d.name} fill={VIEW_COLOR[d.name]} />)}
                <LabelList dataKey="count" position="right" style={{ fontSize: 12, fontWeight: 700, fill: 'var(--text)' }} />
              </Bar>
            </BarChart>
          </ChartContainer>
        </div>
      </div>

      {top.length > 0 && (
        <div className="row single">
          <div className="card">
            <h2>Top holdings by value</h2>
            <ChartContainer config={topConfig} className="w-full" style={{ height: top.length * 34 + 16 }}>
              <BarChart data={top} layout="vertical" margin={{ left: 4, right: 96, top: 4, bottom: 4 }} barCategoryGap={8}>
                <YAxis dataKey="name" type="category" tickLine={false} axisLine={false} width={190} tick={{ fontSize: 12 }} tickFormatter={(v: any) => { const s = String(v ?? ''); return s.length > 26 ? s.slice(0, 25) + '…' : s }} />
                <XAxis dataKey="value" type="number" hide />
                <ChartTooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltipContent hideLabel formatter={(v, _n, item) => <span style={{ display: 'flex', width: '100%', justifyContent: 'space-between', gap: 16 }}><span>{(item?.payload as any)?.name}</span><b className="tnum">{rupee(Number(v))}</b></span>} />} />
                <Bar dataKey="value" radius={[0, 8, 8, 0]} barSize={18} background={{ fill: 'var(--surface-2)', radius: 8 }}>
                  {top.map((d, i) => <Cell key={i} fill={VIEW_COLOR[d.view] ?? '#1e3a8a'} />)}
                  <LabelList dataKey="value" position="right" formatter={(v: any) => compact(Number(v))} style={{ fontSize: 12, fontWeight: 600, fill: 'var(--text)' }} />
                </Bar>
              </BarChart>
            </ChartContainer>
            <p className="muted" style={{ fontSize: 12, margin: '8px 0 0' }}>Bar color shows the CREST advisory view for each stock; blue means not covered or not an equity.</p>
          </div>
        </div>
      )}

      <div className="exports">
        <strong>Download</strong>
        <button className="btn" onClick={() => save('Excel', `${base}_with_advisory.xlsx`, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', b64ToBytes(res.exports.xlsx))}><FileSpreadsheet size={16} /> Excel</button>
        <button className="btn" onClick={() => save('CSV', `${base}_formatted.csv`, 'text/csv', b64ToBytes(res.exports.csv))}><FileText size={16} /> CSV</button>
        <button className="btn" onClick={() => save('JSON', `${base}_parsed.json`, 'application/json', JSON.stringify(res.enriched_json, null, 2))}><FileJson size={16} /> JSON</button>
      </div>

      <div className="tabs" role="tablist">
        {tabs.map(([k, l]) => (
          <button key={k} role="tab" className="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
            {l}
            {tab === k && <motion.span layoutId="tab-underline" className="tab-ul" transition={{ type: 'spring', stiffness: 500, damping: 40 }} />}
          </button>
        ))}
      </div>

      <motion.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease }}>
        {tab === 'advisory' && (
          <>
            <div className="sumgrid">
              {VIEWS.map((v) => (
                <div className="sum" key={v}>
                  <ViewBadge v={v} />
                  <div className="c">{summary[v]?.count ?? 0}</div>
                  <div className="m">{rupee(summary[v]?.value ?? 0)}</div>
                </div>
              ))}
            </div>
            <div className="filters">
              {['All', ...VIEWS].map((v) => (
                <button key={v} className="fbtn" aria-pressed={filter === v} onClick={() => setFilter(v)}>{v}</button>
              ))}
            </div>
            <DataTable rows={shown} cols={advCols} empty="No equity holdings found to cross-reference." />
          </>
        )}
        {tab === 'market' && <MarketTab res={res} m={m} />}
        {tab === 'demat' && <DataTable rows={res.demat} cols={dematCols} empty="No demat holdings in this statement." />}
        {tab === 'mf' && (
          <>
            <DataTable rows={withMfNav(res, m.mfNavs)} cols={mfCols} empty="No mutual fund holdings in this statement." />
            <p className="muted" style={{ fontSize: 12, margin: '8px 0 0' }}>
              &ldquo;Stmt&rdquo; columns are as of the statement date. Latest NAV is end-of-day from Yahoo Finance; each row shows its own NAV date.
            </p>
          </>
        )}
        {tab === 'txn' && <DataTable rows={res.transactions} cols={txCols} empty="No transactions in this statement period." />}
        {tab === 'inv' && (
          <div className="row">
            <div className="card">
              <h2>Investor details</h2>
              <div className="inv-grid">
                {res.investor.details.map(([f, v]) => (
                  <div className="inv-item" key={f}>
                    <span className="inv-lbl">{f}</span>
                    <span className="inv-val">{v || <span className="muted">—</span>}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="card">
              <h2>Portfolio breakdown</h2>
              <div className="breakdown-list">
                {res.categories.map(([c, v, n]) => {
                  const isTotal = c.toLowerCase().includes('total')
                  return (
                    <div className={`breakdown-row ${isTotal ? 'total' : ''}`} key={c}>
                      <span className="breakdown-name">{c}</span>
                      <span className="breakdown-count">{n !== '' && n != null ? `${n} ${n === 1 ? 'item' : 'items'}` : '—'}</span>
                      <span className="breakdown-val tnum">{rupee(v)}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </motion.div>
    </>
  )
}
