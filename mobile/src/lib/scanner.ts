/**
 * Gate scanner engine.
 *
 * - Keeps a copy of the event's ticket list on the phone (AsyncStorage), so
 *   scanning works with no network.
 * - Online: every scan is decided by the server (authoritative across gates).
 * - Offline (or server slow): decided on the phone using the cached list and
 *   the event's signing key, then queued and uploaded when back online. If the
 *   server later says another gate already admitted that ticket, it's reported
 *   as a duplicate alert.
 * - Every 15 s: upload queued scans, then download tickets changed since the
 *   last sync (new sales, transfers, other gates' check-ins).
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useCallback, useEffect, useRef, useState } from "react";

import { isNetworkError } from "./api";
import { useAuth } from "./auth";
import { parsePayload } from "./signing";
import type { Direction, ManifestTicket, ReentryPolicy, ScanResponse, Stats } from "./types";

const SYNC_EVERY_MS = 15_000;
const ONLINE_TIMEOUT_MS = 4_000;

type Manifest = {
  key: string;
  serverTime: string;
  event: { title: string; when: string; where: string; status: string; badges_enabled?: boolean } & Partial<ReentryPolicy>;
  tickets: Record<number, ManifestTicket>;
};

type QueuedScan = { client_id: string; raw: string; gate: string; scanned_at: string; direction: Direction; count?: number };

export type ScanOutcome = ScanResponse & { offline: boolean };
export type Alert = { id: string; text: string };

const mKey = (slug: string) => `scanner:manifest:${slug}`;
const qKey = (slug: string) => `scanner:queue:${slug}`;

export async function getDeviceId(): Promise<string> {
  let id = await AsyncStorage.getItem("scanner:device");
  if (!id) {
    id = `dev-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
    await AsyncStorage.setItem("scanner:device", id);
  }
  return id;
}

export async function getGate(): Promise<string> {
  return (await AsyncStorage.getItem("scanner:gate")) ?? "Main gate";
}
export async function setGate(g: string) {
  await AsyncStorage.setItem("scanner:gate", g);
}

function computeStats(m: Manifest | null): Stats {
  const all = Object.values(m?.tickets ?? {}).filter((t) => t.status !== "void");
  return {
    tickets: all.length,
    checked_in: all.filter((t) => (t.admitted ?? 0) > 0).length,
    people: all.reduce((s, t) => s + t.admits, 0),
    people_arrived: all.reduce((s, t) => s + (t.admitted ?? 0), 0),
    people_in: all.reduce((s, t) => s + (t.inside ?? 0), 0),
  };
}

function reentryProblem(ev: Manifest["event"], t: ManifestTicket, now: Date): string | null {
  if (!ev.reentry_allowed) return "No re-entry for this event";
  if (ev.reentry_cutoff_at && now >= new Date(ev.reentry_cutoff_at)) return "Re-entry has closed";
  if (ev.max_reentries != null && t.reentries >= ev.max_reentries) return `Re-entry limit reached (${ev.max_reentries})`;
  return null;
}

export function useScanner(slug: string) {
  const { request } = useAuth();
  const manifest = useRef<Manifest | null>(null);
  const queue = useRef<QueuedScan[]>([]);
  const syncing = useRef(false);
  const [ready, setReady] = useState(false);
  const [online, setOnline] = useState(true);
  const [stats, setStats] = useState<Stats>({ tickets: 0, checked_in: 0, people: 0, people_in: 0 });
  const [queued, setQueued] = useState(0);
  const [lastSync, setLastSync] = useState<Date | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState("");
  const [eventInfo, setEventInfo] = useState<Manifest["event"] | null>(null);

  const persist = useCallback(async () => {
    if (manifest.current) await AsyncStorage.setItem(mKey(slug), JSON.stringify(manifest.current));
    await AsyncStorage.setItem(qKey(slug), JSON.stringify(queue.current));
    setQueued(queue.current.length);
  }, [slug]);

  const upsert = (rows: ManifestTicket[]) => {
    if (!manifest.current) return;
    for (const r of rows) manifest.current.tickets[r.id] = r;
  };

  const findByCode = (code: string) =>
    Object.values(manifest.current?.tickets ?? {}).find((t) => t.code === code) ?? null;

  /** Upload queued offline scans, then pull changes. */
  const sync = useCallback(async () => {
    if (syncing.current) return;
    syncing.current = true;
    try {
      if (queue.current.length) {
        const batch = queue.current.slice(0, 200);
        const res = await request<{ results: (ScanResponse & { client_id: string })[] }>(
          `/scanner/events/${slug}/sync/`,
          { body: { device_id: await getDeviceId(), scans: batch }, timeoutMs: 20_000 },
        );
        const sent = new Set(batch.map((b) => b.client_id));
        queue.current = queue.current.filter((q) => !sent.has(q.client_id));
        const newAlerts: Alert[] = [];
        const byId = new Map(batch.map((b) => [b.client_id, b]));
        for (const r of res.results) {
          if (r.ticket) upsert([r.ticket]);
          const mine = byId.get(r.client_id);
          // If the network dropped after the server had already admitted this very scan,
          // the "duplicate" is our own earlier attempt at this gate, not a shared ticket.
          const sameScan = r.previous && mine && r.previous.gate === mine.gate &&
            Math.abs(new Date(r.previous.at).getTime() - new Date(mine.scanned_at).getTime()) < 30_000;
          if (r.result === "duplicate" && sameScan) continue;
          if (r.result === "duplicate") {
            const where = r.previous ? ` at ${r.previous.gate || "another gate"}` : "";
            newAlerts.push({ id: r.client_id, text: `${r.ticket?.code ?? "A ticket"} (${r.ticket?.name ?? ""}) was already admitted${where}. Possible shared ticket.` });
          } else if (r.result !== "ok") {
            newAlerts.push({ id: r.client_id, text: `Offline scan rejected by server: ${r.message}` });
          }
        }
        if (newAlerts.length) setAlerts((a) => [...newAlerts, ...a].slice(0, 20));
      }
      const since = manifest.current?.serverTime;
      const m = await request<{
        key: string; server_time: string; full: boolean; event: Manifest["event"]; tickets: ManifestTicket[];
      }>(`/scanner/events/${slug}/manifest/${since ? `?since=${encodeURIComponent(since)}` : ""}`, { timeoutMs: 30_000 });
      if (m.full || !manifest.current) {
        manifest.current = { key: m.key, serverTime: m.server_time, event: m.event, tickets: {} };
      }
      manifest.current.serverTime = m.server_time;
      manifest.current.event = m.event;
      upsert(m.tickets);
      setEventInfo(m.event);
      await persist();
      setOnline(true);
      setLastSync(new Date());
      setError("");
    } catch (e) {
      if (isNetworkError(e)) setOnline(false);
      else setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      syncing.current = false;
      setStats(computeStats(manifest.current));
    }
  }, [request, slug, persist]);

  // Load cached data, then sync on a timer.
  useEffect(() => {
    let alive = true;
    (async () => {
      const [m, q] = await Promise.all([AsyncStorage.getItem(mKey(slug)), AsyncStorage.getItem(qKey(slug))]);
      if (!alive) return;
      manifest.current = m ? JSON.parse(m) : null;
      queue.current = q ? JSON.parse(q) : [];
      setQueued(queue.current.length);
      setEventInfo(manifest.current?.event ?? null);
      setStats(computeStats(manifest.current));
      setReady(!!manifest.current);
      await sync();
      if (alive) setReady(!!manifest.current);
    })();
    const timer = setInterval(sync, SYNC_EVERY_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [slug, sync]);

  const lookup = (raw: string): ManifestTicket | null => {
    const parsed = parsePayload(raw, manifest.current?.key ?? null);
    return parsed.kind === "garbage" ? null : findByCode(parsed.code);
  };

  const decideOffline = (raw: string, gate: string, direction: Direction, count?: number): ScanOutcome => {
    const now = new Date();
    const iso = now.toISOString();
    const ev = manifest.current?.event;
    const parsed = parsePayload(raw, manifest.current?.key ?? null);
    const base = { scanned_at: iso, offline: true, ticket: null, direction } as const;
    const enqueue = () => queue.current.push({ client_id: `${Date.now()}-${Math.random()}`, raw, gate, scanned_at: iso, direction, count });
    if (parsed.kind === "garbage" || (parsed.kind === "qr" && !parsed.signatureOk)) {
      return { ...base, result: "invalid", message: "Not a valid ticket" };
    }
    const t = findByCode(parsed.code);
    if (!t) {
      if (parsed.kind === "qr") {
        // Genuine signature but not in our list yet (bought since the last sync).
        enqueue();
        return direction === "out"
          ? { ...base, result: "exit", message: "Exit recorded (will confirm on sync)" }
          : { ...base, result: "ok", message: "Admit (new ticket, will confirm on sync)" };
      }
      return { ...base, result: "invalid", message: "Code not found (offline). Ask them to show the QR." };
    }
    if (ev?.status === "cancelled") return { ...base, ticket: t, result: "event_cancelled", message: "This event was cancelled" };
    if (t.status === "void") return { ...base, ticket: t, result: "void", message: "Ticket cancelled or refunded" };

    if (direction === "out") {
      if (!t.inside) return { ...base, ticket: t, result: "not_inside", message: "This ticket isn't inside" };
      const n = Math.min(count ?? t.inside, t.inside);
      t.inside -= n;
      enqueue();
      return { ...base, ticket: t, people: n, result: "exit",
        message: (t.admits > 1 ? `Exit: ${n} of ${t.admits}` : "Exit recorded") + (ev?.reentry_allowed ? "" : ". No re-entry for this event") };
    }

    const neverIn = t.admits - t.admitted;
    const returning = t.admitted - t.inside;
    if (neverIn + returning === 0) {
      return { ...base, ticket: t, result: "duplicate", message: t.admits > 1 ? `All ${t.admits} already inside` : "Already inside",
        previous: t.checked_in_at ? { at: t.checked_in_at, gate: "" } : undefined };
    }
    const want = Math.min(count ?? (neverIn || returning), neverIn + returning);
    const fresh = Math.min(want, neverIn);
    let back = want - fresh;
    if (back && ev) {
      const problem = reentryProblem(ev, t, now);
      if (problem) {
        if (!fresh) return { ...base, ticket: t, result: "no_reentry", message: problem };
        back = 0;
      }
    }
    t.admitted += fresh;
    t.inside += fresh + back;
    if (back) t.reentries += 1;
    if (t.status !== "checked_in") {
      t.status = "checked_in";
      t.checked_in_at = iso;
    }
    enqueue();
    const result = back && !fresh ? "reentry" : "ok";
    const label = result === "reentry" ? "Welcome back" : "Admit";
    return { ...base, ticket: t, people: fresh + back, result, message: t.admits > 1 ? `${label}: ${fresh + back} of ${t.admits}` : label };
  };

  const scan = useCallback(async (raw: string, gate: string, direction: Direction = "in", count?: number): Promise<ScanOutcome> => {
    let outcome: ScanOutcome;
    try {
      const res = await request<ScanResponse>(`/scanner/events/${slug}/scan/`, {
        body: { raw, gate, direction, count, device_id: await getDeviceId() }, timeoutMs: ONLINE_TIMEOUT_MS,
      });
      if (res.ticket) upsert([res.ticket]);
      setOnline(true);
      outcome = { ...res, offline: false };
    } catch (e) {
      if (!isNetworkError(e)) throw e;
      setOnline(false);
      outcome = decideOffline(raw, gate, direction, count);
    }
    await persist();
    setStats(computeStats(manifest.current));
    return outcome;
  }, [request, slug, persist]); // eslint-disable-line react-hooks/exhaustive-deps

  const undo = useCallback(async (code: string) => {
    const res = await request<{ ticket: ManifestTicket }>(`/scanner/events/${slug}/undo/`, { body: { code } });
    upsert([res.ticket]);
    await persist();
    setStats(computeStats(manifest.current));
  }, [request, slug, persist]);

  return {
    ready, online, stats, queued, lastSync, alerts, error, eventInfo,
    scan, undo, sync, lookup, dismissAlert: (id: string) => setAlerts((a) => a.filter((x) => x.id !== id)),
  };
}
