const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 })
const num = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 3 })

const blank = (v: unknown) => v == null || v === ''

export const rupee = (v: unknown) =>
  typeof v === 'number' && isFinite(v) ? '₹' + inr.format(v) : blank(v) ? '—' : String(v)
export const units = (v: unknown) =>
  typeof v === 'number' && isFinite(v) ? num.format(v) : blank(v) ? '—' : String(v)

export const compact = (v: number) => {
  const a = Math.abs(v)
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`
  return rupee(v)
}

export function download(name: string, mime: string, data: BlobPart) {
  const url = URL.createObjectURL(new Blob([data], { type: mime }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  URL.revokeObjectURL(url)
}

export function b64ToBytes(b64: string) {
  const bin = atob(b64)
  return Uint8Array.from(bin, (c) => c.charCodeAt(0))
}
