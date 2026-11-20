// Well-formed UTF-8 NDJSON frames for the Core protocol.
//
// JSON.stringify escapes a lone surrogate as "\udXXX", and the Core closes the whole Host session
// on such a frame (crates/ligamina-core/tests/host_session.rs). Lone surrogates in string values
// and object keys therefore become U+FFFD; valid pairs and all other text are left unchanged.

const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g

function wellFormed(text: string): string {
  return text.replace(LONE_SURROGATE, '�')
}

function replacer(_key: string, value: unknown): unknown {
  if (typeof value === 'string') return wellFormed(value)
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    const entries = Object.entries(value)
    if (entries.some(([key]) => wellFormed(key) !== key)) {
      return Object.fromEntries(entries.map(([key, item]) => [wellFormed(key), item]))
    }
  }
  return value
}

export function encodeFrame(packet: Record<string, unknown>): Buffer {
  return Buffer.from(`${JSON.stringify(packet, replacer)}\n`, 'utf8')
}
