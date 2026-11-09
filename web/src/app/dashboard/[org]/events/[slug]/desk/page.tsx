"use client";

/**
 * Badge check-in desk (laptop + label printer).
 *
 * Phones admit people at the door; anyone admitted appears here within ~2 s
 * under "Ready to print". With auto-print on, each badge prints as it arrives.
 * The desk can also check people in itself: a USB QR scanner types into the
 * scan box (or type a ticket code / search a name).
 *
 * Tip for silent printing: start Chrome with --kiosk-printing and set the
 * label printer as default, so no print dialog appears.
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useOrg } from "@/components/dashboard/org";
import { Alert, Badge as Pill, Button, Field, Input, PageLoader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { timeOnly } from "@/lib/format";
import type { Badge } from "@/lib/types";

type DeskData = {
  event: { title: string; code: string; badges_enabled: boolean; width_mm: number; height_mm: number };
  badges: Badge[];
  stats: { people_in: number; people: number; checked_in: number; tickets: number };
};
type ScanReply = { result: string; message: string; ticket: { name: string; code: string } | null };

const POLL_MS = 2000;

export default function DeskPage() {
  const { slug } = useParams<{ slug: string }>();
  const { org, base, can } = useOrg();
  const { request } = useAuth();
  const api = `/scanner/events/${slug}/badges/`;

  const [data, setData] = useState<DeskData | null>(null);
  const [printed, setPrinted] = useState<Badge[]>([]);
  const [results, setResults] = useState<Badge[] | null>(null);
  const [error, setError] = useState("");
  const [auto, setAuto] = useState(false);
  const [printing, setPrinting] = useState<Badge | null>(null);
  const [editing, setEditing] = useState<Badge | null>(null);
  const [scanText, setScanText] = useState("");
  const [scanMsg, setScanMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const busy = useRef(false);

  const load = useCallback(async () => {
    try {
      setData(await request<DeskData>(api));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't reach the server.");
    }
  }, [request, api]);

  const loadPrinted = useCallback(async () => {
    const d = await request<DeskData>(`${api}?status=printed`).catch(() => null);
    if (d) setPrinted(d.badges);
  }, [request, api]);

  // Live queue.
  useEffect(() => {
    load();
    loadPrinted();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load, loadPrinted]);

  useEffect(() => {
    try { setAuto(localStorage.getItem("desk.auto") === "1"); } catch { /* ignore */ }
  }, []);
  const toggleAuto = (v: boolean) => {
    setAuto(v);
    try { localStorage.setItem("desk.auto", v ? "1" : "0"); } catch { /* ignore */ }
  };

  const print = useCallback(async (b: Badge) => {
    if (busy.current) return;
    busy.current = true;
    setPrinting(b);
    // Let React render the badge into the print area before opening the print dialog.
    await new Promise((r) => setTimeout(r, 150));
    window.print(); // blocks until the dialog closes (or returns at once with --kiosk-printing)
    try {
      await request(`${api}${b.code}/printed/`, { method: "POST" });
    } finally {
      setPrinting(null);
      busy.current = false;
      load();
      loadPrinted();
    }
  }, [request, api, load, loadPrinted]);

  // Auto-print the oldest waiting badge.
  useEffect(() => {
    const next = data?.badges[0];
    if (auto && next && !busy.current && !editing) print(next);
  }, [auto, data, editing, print]);

  async function scan(e: React.FormEvent) {
    e.preventDefault();
    const raw = scanText.trim();
    if (!raw) return;
    setScanText("");
    // A ticket QR or code: check them in. Anything else: search by name/organization.
    const looksLikeTicket = raw.startsWith("TX1:") || /^[A-Za-z0-9]{8,12}$/.test(raw);
    if (looksLikeTicket) {
      try {
        const r = await request<ScanReply>(`/scanner/events/${slug}/scan/`, { body: { raw, gate: "Badge desk" } });
        const ok = r.result === "ok" || r.result === "reentry";
        setScanMsg({ ok, text: `${r.ticket?.name ?? ""} ${ok ? "checked in" : `: ${r.message}`}`.trim() });
        setResults(null);
        load();
        return;
      } catch { /* fall through to search */ }
    }
    const d = await request<DeskData>(`${api}?q=${encodeURIComponent(raw)}`).catch(() => null);
    setResults(d?.badges ?? []);
    setScanMsg(null);
  }

  if (!data && !error) return <PageLoader />;
  const ev = data?.event;

  return (
    <div>
      <PrintStyles w={ev?.width_mm ?? 90} h={ev?.height_mm ?? 60} />
      <div className="no-print">
        <Link href={`${base}/events/${slug}`} className="text-sm font-semibold text-brand">← Event</Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold">Check-in desk</h1>
            <p className="text-zinc-600">{ev?.title} · {data?.stats.people_in ?? 0} inside · {data?.stats.checked_in ?? 0}/{data?.stats.tickets ?? 0} tickets checked in</p>
          </div>
          <label className="flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-4 py-2.5 font-semibold">
            <input type="checkbox" className="h-5 w-5 accent-brand" checked={auto} onChange={(e) => toggleAuto(e.target.checked)} />
            Auto-print new badges
          </label>
        </div>
        {error && <div className="mt-4"><Alert>{error}</Alert></div>}
        {ev && !ev.badges_enabled && (
          <div className="mt-4"><Alert kind="info">Badges are off for this event. Turn on &ldquo;Print name badges&rdquo; under Details.</Alert></div>
        )}

        <form onSubmit={scan} className="mt-6 flex gap-2">
          <Input autoFocus value={scanText} onChange={(e) => setScanText(e.target.value)}
            placeholder="Scan a ticket QR (USB scanner), type a ticket code, or search a name" className="text-lg" />
          <Button type="submit">Go</Button>
        </form>
        {scanMsg && <div className="mt-2"><Alert kind={scanMsg.ok ? "success" : "error"}>{scanMsg.text}</Alert></div>}

        {results && (
          <section className="mt-6">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="font-bold">Search results</h2>
              <button className="text-sm text-zinc-500" onClick={() => setResults(null)}>Clear</button>
            </div>
            <BadgeList badges={results} onPrint={print} onEdit={setEditing} printLabel="Print" empty="No one found." />
          </section>
        )}

        <section className="mt-6">
          <h2 className="mb-2 font-bold">Ready to print <Pill color="brand">{data?.badges.length ?? 0}</Pill></h2>
          <p className="mb-3 text-sm text-zinc-500">People admitted at the door appear here within seconds.</p>
          <BadgeList badges={data?.badges ?? []} onPrint={print} onEdit={setEditing} printLabel="Print" empty="Waiting for check-ins…" />
        </section>

        <section className="mt-8">
          <h2 className="mb-2 font-bold">Recently printed</h2>
          <BadgeList badges={printed} onPrint={print} onEdit={setEditing} printLabel="Reprint" empty="Nothing printed yet." />
        </section>

        <p className="mt-8 text-xs text-zinc-500">
          Tip: for one-click printing without the print dialog, open this page in Chrome started with
          <code className="mx-1 rounded bg-zinc-100 px-1">--kiosk-printing</code> and set your label printer as the default printer
          with a {ev?.width_mm}×{ev?.height_mm} mm label size.
        </p>
      </div>

      {/* Only this is printed */}
      <div id="badge-print">{printing ? <BadgeSticker b={printing} /> : null}</div>

      {editing && (
        <EditDialog badge={editing} canRole={can("manage_events")} api={api} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); loadPrinted(); }} orgSlug={org.slug} />
      )}
    </div>
  );
}

function BadgeList({ badges, onPrint, onEdit, printLabel, empty }: {
  badges: Badge[]; onPrint: (b: Badge) => void; onEdit: (b: Badge) => void; printLabel: string; empty: string;
}) {
  if (!badges.length) return <p className="rounded-xl border border-dashed border-zinc-300 bg-white p-6 text-center text-sm text-zinc-500">{empty}</p>;
  return (
    <div className="divide-y divide-zinc-100 overflow-hidden rounded-xl border border-zinc-200 bg-white">
      {badges.map((b) => (
        <div key={b.code} className="flex flex-wrap items-center gap-3 p-3">
          <div className="min-w-0 flex-1">
            <p className="font-bold">{b.name}</p>
            <p className="text-sm text-zinc-600">{[b.organization, b.job_title].filter(Boolean).join(" · ") || "—"}</p>
            <p className="text-xs text-zinc-500">
              <span className="font-semibold uppercase">{b.role}</span>
              {b.checked_in_at && ` · in at ${timeOnly(b.checked_in_at)}`}
              {b.print_count > 0 && ` · printed ${b.print_count}×`}
              {!b.share_contact && " · no contact QR"}
            </p>
          </div>
          <Button size="sm" variant="secondary" onClick={() => onEdit(b)}>Edit</Button>
          <Button size="sm" onClick={() => onPrint(b)}>{printLabel}</Button>
        </div>
      ))}
    </div>
  );
}

/** The sticker itself, sized in mm so it matches the label stock. */
function BadgeSticker({ b }: { b: Badge }) {
  return (
    <div className="badge">
      <div className="badge-text">
        <div className="badge-name">{b.name}</div>
        {b.organization && <div className="badge-org">{b.organization}</div>}
        {b.job_title && <div className="badge-title">{b.job_title}</div>}
        <div className="badge-role">{b.role}</div>
      </div>
      {b.qr && (
        <div className="badge-qr">
          <QRCodeSVG value={b.qr} level="M" style={{ width: "100%", height: "auto" }} />
        </div>
      )}
      {b.event_code && <div className="badge-code">{b.event_code}</div>}
    </div>
  );
}

function PrintStyles({ w, h }: { w: number; h: number }) {
  return (
    <style>{`
      #badge-print { display: none; }
      @media print {
        @page { size: ${w}mm ${h}mm; margin: 0; }
        html, body { background: #fff !important; margin: 0 !important; }
        body * { visibility: hidden !important; }
        #badge-print, #badge-print * { visibility: visible !important; }
        #badge-print { display: block !important; position: fixed; left: 0; top: 0; }
        .no-print { display: none !important; }
      }
      .badge { width: ${w}mm; height: ${h}mm; box-sizing: border-box; padding: 3mm; display: flex; gap: 2mm;
        align-items: center; position: relative; color: #000; font-family: Arial, Helvetica, sans-serif; }
      .badge-text { flex: 1; min-width: 0; text-align: center; }
      .badge-name { font-size: ${Math.round(h * 0.16)}pt; font-weight: 800; line-height: 1.05; text-transform: uppercase; }
      .badge-org { font-size: ${Math.round(h * 0.11)}pt; margin-top: 1.2mm; }
      .badge-title { font-size: ${Math.round(h * 0.09)}pt; color: #333; }
      .badge-role { font-size: ${Math.round(h * 0.12)}pt; font-weight: 800; margin-top: 1.5mm; text-transform: uppercase; letter-spacing: 0.5pt; }
      .badge-qr { width: ${Math.round(Math.min(h * 0.62, w * 0.36))}mm; flex-shrink: 0; }
      .badge-code { position: absolute; bottom: 1.5mm; right: 3mm; font-size: 6pt; font-weight: 700; }
    `}</style>
  );
}

function EditDialog({ badge, canRole, api, onClose, onSaved }: {
  badge: Badge; canRole: boolean; api: string; onClose: () => void; onSaved: () => void; orgSlug: string;
}) {
  const { request } = useAuth();
  const [f, setF] = useState({
    attendee_name: badge.name, attendee_organization: badge.organization, attendee_job_title: badge.job_title,
    badge_role: badge.role,
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const body: Record<string, string> = { attendee_name: f.attendee_name, attendee_organization: f.attendee_organization,
        attendee_job_title: f.attendee_job_title };
      if (canRole && f.badge_role !== badge.role) body.badge_role = f.badge_role;
      await request(`${api}${badge.code}/`, { method: "PATCH", body });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save.");
      setSaving(false);
    }
  }
  return (
    <div className="no-print fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={onClose}>
      <form onSubmit={save} onClick={(e) => e.stopPropagation()} className="w-full max-w-md space-y-3 rounded-xl bg-white p-6">
        <h2 className="text-lg font-bold">Edit badge</h2>
        <Field label="Name on badge"><Input required value={f.attendee_name} onChange={(e) => setF({ ...f, attendee_name: e.target.value })} /></Field>
        <Field label="Organization"><Input value={f.attendee_organization} onChange={(e) => setF({ ...f, attendee_organization: e.target.value })} /></Field>
        <Field label="Job title"><Input value={f.attendee_job_title} onChange={(e) => setF({ ...f, attendee_job_title: e.target.value })} /></Field>
        <Field label="Role" hint={canRole ? "e.g. Delegate, Speaker, Facilitator, Usher" : "Only event managers can change roles"}>
          <Input disabled={!canRole} value={f.badge_role} onChange={(e) => setF({ ...f, badge_role: e.target.value })} />
        </Field>
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Button type="button" variant="secondary" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button type="submit" className="flex-1" loading={saving}>Save</Button>
        </div>
      </form>
    </div>
  );
}
