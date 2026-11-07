"use client";

import { useState } from "react";

import { Alert, Badge, Button, Field, Input, Select } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { cedis, fromLocalInput, toLocalInput } from "@/lib/format";
import type { OrgEvent, TicketType } from "@/lib/types";

import { useOrg } from "./org";

const STATUS: Record<string, [string, "green" | "yellow" | "gray" | "red"]> = {
  on_sale: ["On sale", "green"], scheduled: ["Scheduled", "yellow"], ended: ["Ended", "gray"],
  sold_out: ["Sold out", "red"], unavailable: ["Not live", "gray"],
};

const PRESETS = [
  { name: "Early Bird", hint: "Cheaper, limited quantity" }, { name: "Regular", hint: "" },
  { name: "VIP", hint: "" }, { name: "Table for 10", hint: "One ticket admits 10", admits: 10 },
];

export function TicketTypes({ event, onChange }: { event: OrgEvent; onChange: () => void }) {
  const [editing, setEditing] = useState<TicketType | "new" | null>(event.ticket_types.length ? null : "new");
  const locked = event.status === "cancelled";
  return (
    <div className="space-y-4">
      {event.ticket_types.map((t) => editing !== "new" && editing?.id === t.id ? (
        <TicketForm key={t.id} event={event} ticket={t} onDone={() => { setEditing(null); onChange(); }} />
      ) : (
        <div key={t.id} className="flex flex-wrap items-center gap-4 rounded-xl border border-zinc-200 bg-white p-4">
          <div className="min-w-0 flex-1">
            <p className="font-bold">{t.name} {t.visibility === "hidden" && <Badge>Hidden</Badge>} {!t.is_active && <Badge color="red">Off</Badge>}</p>
            <p className="text-sm text-zinc-600">
              {Number(t.price) === 0 ? "Free" : cedis(t.price)}
              {Number(t.price) > 0 && ` · buyer pays ${cedis(t.pricing.buyer_pays)} · you get ${cedis(t.pricing.organizer_receives)}`}
              {t.admits > 1 && ` · admits ${t.admits}`}
            </p>
          </div>
          <div className="text-right text-sm">
            <p className="font-semibold">{t.quantity_sold} / {t.quantity} sold</p>
            <Badge color={STATUS[t.sale_status][1]}>{STATUS[t.sale_status][0]}</Badge>
          </div>
          {!locked && <Button size="sm" variant="secondary" onClick={() => setEditing(t)}>Edit</Button>}
        </div>
      ))}
      {editing === "new" ? <TicketForm event={event} onDone={() => { setEditing(null); onChange(); }} onCancel={event.ticket_types.length ? () => setEditing(null) : undefined} />
        : !locked && <Button variant="secondary" onClick={() => setEditing("new")}>+ Add ticket type</Button>}
    </div>
  );
}

function TicketForm({ event, ticket, onDone, onCancel }: { event: OrgEvent; ticket?: TicketType; onDone: () => void; onCancel?: () => void }) {
  const { org } = useOrg();
  const { request } = useAuth();
  const [f, setF] = useState({
    name: ticket?.name ?? "", description: ticket?.description ?? "", price: ticket?.price ?? "",
    quantity: String(ticket?.quantity ?? 100), admits: String(ticket?.admits ?? 1),
    min_per_order: String(ticket?.min_per_order ?? 1), max_per_order: String(ticket?.max_per_order ?? 10),
    sales_start_at: toLocalInput(ticket?.sales_start_at), sales_end_at: toLocalInput(ticket?.sales_end_at),
    visibility: ticket?.visibility ?? "visible", is_active: ticket?.is_active ?? true,
  });
  const [more, setMore] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const base = `/organizations/${org.slug}/events/${event.slug}/ticket-types/`;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await request(ticket ? `${base}${ticket.id}/` : base, {
        method: ticket ? "PATCH" : "POST",
        body: {
          ...f, price: f.price || "0", quantity: Number(f.quantity), admits: Number(f.admits),
          min_per_order: Number(f.min_per_order), max_per_order: Number(f.max_per_order),
          sales_start_at: fromLocalInput(f.sales_start_at), sales_end_at: fromLocalInput(f.sales_end_at),
        },
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
      setBusy(false);
    }
  }
  async function remove() {
    if (!ticket || !confirm(`Delete "${ticket.name}"?`)) return;
    try {
      await request(`${base}${ticket.id}/`, { method: "DELETE" });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete.");
    }
  }

  return (
    <form onSubmit={save} className="space-y-4 rounded-xl border-2 border-brand/40 bg-white p-5">
      {!ticket && (
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button type="button" key={p.name} onClick={() => setF({ ...f, name: p.name, admits: String(p.admits ?? 1) })}
              className="rounded-full border border-zinc-300 px-3 py-1 text-xs font-semibold hover:border-brand">{p.name}</button>
          ))}
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Ticket name"><Input required value={f.name} onChange={set("name")} /></Field>
        <Field label="Price (GHS)" hint="0 for free"><Input type="number" min={0} step="0.01" value={f.price} onChange={set("price")} placeholder="0" /></Field>
        <Field label="Quantity available"><Input type="number" min={ticket?.quantity_sold || 1} required value={f.quantity} onChange={set("quantity")} /></Field>
      </div>
      <Field label="Description (optional)"><Input value={f.description} onChange={set("description")} placeholder="e.g. Includes a drink and front-row seating" /></Field>
      <button type="button" onClick={() => setMore(!more)} className="text-sm font-semibold text-brand">{more ? "Hide" : "Show"} advanced options</button>
      {more && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="People per ticket" hint="e.g. 10 for a table"><Input type="number" min={1} max={50} value={f.admits} onChange={set("admits")} /></Field>
          <Field label="Min per order"><Input type="number" min={1} value={f.min_per_order} onChange={set("min_per_order")} /></Field>
          <Field label="Max per order"><Input type="number" min={1} value={f.max_per_order} onChange={set("max_per_order")} /></Field>
          <Field label="Sales start" hint="Blank = when published"><Input type="datetime-local" value={f.sales_start_at} onChange={set("sales_start_at")} /></Field>
          <Field label="Sales end" hint="Blank = when event ends"><Input type="datetime-local" value={f.sales_end_at} onChange={set("sales_end_at")} /></Field>
          <Field label="Visibility" hint="Hidden tickets need an access code">
            <Select value={f.visibility} onChange={set("visibility")}>
              <option value="visible">Visible</option><option value="hidden">Hidden</option>
            </Select>
          </Field>
          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" className="h-4 w-4 accent-brand" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />
            Selling (untick to pause)
          </label>
        </div>
      )}
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={busy}>{ticket ? "Save" : "Add ticket"}</Button>
        {(ticket || onCancel) && <Button type="button" variant="ghost" onClick={ticket ? onDone : onCancel}>Cancel</Button>}
        {ticket && ticket.quantity_sold === 0 && <Button type="button" variant="ghost" className="ml-auto text-red-600" onClick={remove}>Delete</Button>}
      </div>
    </form>
  );
}
