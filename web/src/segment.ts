import type { Correction } from './api'

/** Split `content` into plain and flagged runs. Offsets are code points, so slice by those. */
export function segment(
  content: string,
  corrections: Correction[],
): { text: string; correction?: Correction }[] {
  const chars = Array.from(content)
  const sorted = [...corrections]
    .filter((c) => c.start >= 0 && c.end <= chars.length && c.start < c.end)
    .sort((a, b) => a.start - b.start)
  const parts: { text: string; correction?: Correction }[] = []
  let at = 0
  for (const c of sorted) {
    if (c.start < at) continue // overlapping spans are dropped by the server; be safe anyway
    if (c.start > at) parts.push({ text: chars.slice(at, c.start).join('') })
    parts.push({ text: chars.slice(c.start, c.end).join(''), correction: c })
    at = c.end
  }
  if (at < chars.length) parts.push({ text: chars.slice(at).join('') })
  return parts
}
