"use client";

import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useState } from "react";

import { Cover } from "@/components/EventCard";
import { RequireAuth } from "@/components/RequireAuth";
import { Alert, Badge, Button, ButtonLink, Empty, Field, Input, PageLoader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import type { Paginated, WalletTicket } from "@/lib/types";

export default function Page() {
  return <RequireAuth><Wallet /></RequireAuth>;
}

function Wallet() {
  const { request } = useAuth();
  const [when, setWhen] = useState<"upcoming" | "past">("upcoming");
  const [tickets, setTickets] = useState<WalletTicket[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [transfer, setTransfer] = useState<WalletTicket | null>(null);
  const [notice, setNotice] = useState("");

  const load = useCallback(() => {
    setTickets(null);
    request<Paginated<WalletTicket>>(`/tickets/?when=${when}`).then((r) => setTickets(r.results)).catch(() => setTickets([]));
  }, [request, when]);
  useEffect(load, [load]);

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-3xl font-extrabold">My tickets</h1>
      <div className="mt-4 flex gap-2">
        {(["upcoming", "past"] as const).map((w) => (
          <button key={w} onClick={() => setWhen(w)}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold ${when === w ? "bg-brand text-white" : "border border-zinc-300 bg-white"}`}>
            {w === "upcoming" ? "Upcoming" : "Past"}
          </button>
        ))}
      </div>
      {notice && <div className="mt-4"><Alert kind="success">{notice}</Alert></div>}
      <div className="mt-6 space-y-4">
        {tickets === null ? <PageLoader /> : tickets.length === 0 ? (
          <Empty title={when === "upcoming" ? "No upcoming tickets" : "No past tickets"}>
            <Link href="/events" className="font-semibold text-brand">Find something to do →</Link>
          </Empty>
        ) : tickets.map((t) => (
          <div key={t.code} className="overflow-hidden rounded-xl border border-zinc-200 bg-white">
            <button className="flex w-full items-center gap-4 p-4 text-left" onClick={() => setOpen(open === t.code ? null : t.code)}>
              <div className="h-16 w-24 shrink-0 overflow-hidden rounded-lg"><Cover src={t.event.cover_image} title={t.event.title} /></div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-bold">{t.event.title}</p>
                <p className="text-sm text-zinc-600">{t.event.when}</p>
                <p className="text-sm text-zinc-600">{t.ticket_type_name}{t.attendee_name && ` · ${t.attendee_name}`}</p>
              </div>
              {t.status === "checked_in" ? <Badge color="yellow">Used</Badge>
                : t.event.status === "cancelled" ? <Badge color="red">Cancelled</Badge>
                : <span className="text-sm font-semibold text-brand">{open === t.code ? "Hide" : "Show QR"}</span>}
            </button>
            {open === t.code && (
              <div className="border-t border-zinc-100 p-5 text-center">
                {t.qr_payload ? (
                  <div className="mx-auto w-fit rounded-xl bg-white p-3 ring-1 ring-zinc-200"><QRCodeSVG value={t.qr_payload} size={220} level="M" /></div>
                ) : <p className="text-zinc-500">This ticket can no longer be used.</p>}
                <p className="mt-3 font-mono text-xl font-bold tracking-widest">{t.code}</p>
                <p className="text-sm text-zinc-600">{t.event.where}</p>
                {t.event.online_url && <a href={t.event.online_url} className="mt-2 block font-semibold text-brand" target="_blank" rel="noreferrer">Join online →</a>}
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  <ButtonLink href={`/e/${t.event.slug}`} variant="secondary" size="sm">Event details</ButtonLink>
                  <PdfButton code={t.code} />
                  {t.can_transfer && <Button size="sm" variant="secondary" onClick={() => setTransfer(t)}>Send to a friend</Button>}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      {transfer && (
        <TransferDialog ticket={transfer} onClose={() => setTransfer(null)}
          onDone={(to) => { setTransfer(null); setNotice(`Ticket sent to ${to}.`); load(); }} />
      )}
    </main>
  );
}

function PdfButton({ code }: { code: string }) {
  const { download } = useAuth();
  const [busy, setBusy] = useState(false);
  return (
    <Button size="sm" variant="secondary" loading={busy}
      onClick={async () => { setBusy(true); await download(`/tickets/${code}/pdf/`, `ticket-${code}.pdf`).catch(() => {}); setBusy(false); }}>
      PDF
    </Button>
  );
}

function TransferDialog({ ticket, onClose, onDone }: { ticket: WalletTicket; onClose: () => void; onDone: (to: string) => void }) {
  const { request } = useAuth();
  const [to, setTo] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await request<{ sent_to: string }>(`/tickets/${ticket.code}/transfer/`, { body: { to, name } });
      onDone(res.sent_to);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Transfer failed.");
      setBusy(false);
    }
  }
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={onClose}>
      <form onSubmit={submit} onClick={(e) => e.stopPropagation()} className="w-full max-w-sm space-y-4 rounded-xl bg-white p-6">
        <h2 className="text-lg font-bold">Send ticket to a friend</h2>
        <p className="text-sm text-zinc-600">{ticket.ticket_type_name} · {ticket.event.title}</p>
        <Field label="Their name"><Input required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Their phone or email" hint="We'll send them the ticket by SMS or email">
          <Input required value={to} onChange={(e) => setTo(e.target.value)} placeholder="024 123 4567" />
        </Field>
        <Alert kind="info">Once sent, your copy of this ticket (including screenshots) stops working.</Alert>
        {error && <Alert>{error}</Alert>}
        <div className="flex gap-2">
          <Button type="button" variant="secondary" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button type="submit" className="flex-1" loading={busy}>Send ticket</Button>
        </div>
      </form>
    </div>
  );
}
