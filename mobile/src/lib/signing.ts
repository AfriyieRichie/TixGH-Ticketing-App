/**
 * Offline QR verification, mirroring backend/apps/tickets/signing.py:
 *   payload = "TX1:<code>:<sig>"
 *   sig     = base32( HMAC-SHA256(event_key, code) )[:12]
 * The event key comes from the scanner manifest, so forged QR codes are
 * rejected even with no network.
 */
import { sha256 } from "js-sha256";

const PREFIX = "TX1";
const B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base64UrlToBytes(b64: string): Uint8Array {
  const std = b64.replace(/-/g, "+").replace(/_/g, "/");
  const bin = globalThis.atob(std + "=".repeat((4 - (std.length % 4)) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

export function base32(bytes: Uint8Array): string {
  let bits = 0;
  let value = 0;
  let out = "";
  for (const b of bytes) {
    value = (value << 8) | b;
    bits += 8;
    while (bits >= 5) {
      out += B32[(value >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  if (bits > 0) out += B32[(value << (5 - bits)) & 31];
  return out;
}

export function signCode(keyB64: string, code: string): string {
  const mac = sha256.hmac.arrayBuffer(base64UrlToBytes(keyB64), code);
  return base32(new Uint8Array(mac)).slice(0, 12);
}

export type Parsed =
  | { kind: "qr"; code: string; signatureOk: boolean }
  | { kind: "typed"; code: string }
  | { kind: "garbage" };

export function parsePayload(raw: string, keyB64: string | null): Parsed {
  const s = (raw || "").trim();
  const parts = s.split(":");
  if (parts.length === 3 && parts[0] === PREFIX) {
    const [, code, sig] = parts;
    return { kind: "qr", code, signatureOk: !!keyB64 && signCode(keyB64, code) === sig };
  }
  if (parts.length === 1 && /^[A-Za-z0-9]{8,12}$/.test(s)) return { kind: "typed", code: s.toUpperCase() };
  return { kind: "garbage" };
}
