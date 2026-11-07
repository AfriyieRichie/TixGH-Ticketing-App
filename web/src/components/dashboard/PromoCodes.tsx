"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert, Badge, Button, Field, Input, Select } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { cedis, eventDate, fromLocalInput } from "@/lib/format";
import type { OrgEvent, PromoCode } from "@/lib/types";

import { useOrg } from "./org";

export function PromoCodes({ event }: { event: OrgEvent }) {
  const { org } = useOrg();
  const { request } = useAuth();
  const base = `/organizations/${org.slug}/events/${event.slug}/promo-codes/`;
  const [codes, setCodes] = useState<PromoCode[]>([]);
  const [f, setF] = useState({ code: "", discount_type: "percent", amount: "", max_uses: "", valid_until: "", ticket_types: [] as number[] });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => { request<PromoCode[]>(base).then(setCodes); }, [request, base]);
  useEffect(load, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await request(base, { body: {
        ...f, amount: f.discount_type === "none" ? "0" : f.amount || "0",
        max_uses: f.max_uses ? Number(f.max_uses) : null, valid_until: fromLocalInput(f.valid_until),
      } });
      setF({ code: "", discount_type: "percent", amount: "", max_uses: "", valid_until: "", ticket_types: [] });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create code.");
    } finally {
      setBusy(false);
    }
  }
  async function toggle(c: PromoCode) {
    await request(`${base}${c.id}/`, { method: "PATCH", body: { is_active: !c.is_active } });
    load();
  }

  const describe = (c: PromoCode) =>
    c.discount_type === "percent" ? `${Number(c.amount)}% off` : c.discount_type === "fixed" ? `${cedis(c.amount)} off` : "Access code";

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        {codes.length === 0 && <p className="text-sm text-zinc-500">No codes yet.</p>}
        {codes.map((c) => (
          <div key={c.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-zinc-200 bg-white p-4">
            <span className="font-mono text-lg font-bold">{c.code}</span>
            <Badge color="brand">{describe(c)}</Badge>
            {!c.is_active && <Badge color="red">Paused</Badge>}
            <span className="text-sm text-zinc-600">
              Used {c.times_used}{c.max_uses !== null && ` / ${c.max_uses}`}
              {c.valid_until && ` · until ${eventDate(c.valid_until)}`}
              {c.ticket_types.length > 0 && ` · ${c.ticket_types.map((id) => event.ticket_types.find((t) => t.id === id)?.name).join(", ")}`}
            </span>
            <Button size="sm" variant="secondary" className="ml-auto" onClick={() => toggle(c)}>{c.is_active ? "Pause" : "Resume"}</Button>
          </div>
        ))}
      </div>

      <form onSubmit={create} className="space-y-4 rounded-xl border border-zinc-200 bg-white p-5">
        <h3 className="font-bold">New code</h3>
        <div className="grid gap-4 sm:grid-cols-4">
          <Field label="Code"><Input required value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} placeholder="EARLY20" className="uppercase" /></Field>
          <Field label="Type">
            <Select value={f.discount_type} onChange={(e) => setF({ ...f, discount_type: e.target.value })}>
              <option value="percent">% off</option><option value="fixed">GHS off</option><option value="none">Access code only</option>
            </Select>
          </Field>
          {f.discount_type !== "none" && (
            <Field label={f.discount_type === "percent" ? "Percent" : "Amount (GHS)"}>
              <Input type="number" min={0} step="0.01" required value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} />
            </Field>
          )}
          <Field label="Max uses" hint="Blank = unlimited"><Input type="number" min={1} value={f.max_uses} onChange={(e) => setF({ ...f, max_uses: e.target.value })} /></Field>
          <Field label="Expires" hint="Optional"><Input type="datetime-local" value={f.valid_until} onChange={(e) => setF({ ...f, valid_until: e.target.value })} /></Field>
        </div>
        {event.ticket_types.length > 0 && (
          <div>
            <p className="mb-1 text-sm font-medium">Applies to <span className="font-normal text-zinc-500">(none ticked = all tickets; tick hidden tickets to unlock them with this code)</span></p>
            <div className="flex flex-wrap gap-3">
              {event.ticket_types.map((t) => (
                <label key={t.id} className="flex items-center gap-1.5 text-sm">
                  <input type="checkbox" className="accent-brand" checked={f.ticket_types.includes(t.id)}
                    onChange={(e) => setF({ ...f, ticket_types: e.target.checked ? [...f.ticket_types, t.id] : f.ticket_types.filter((x) => x !== t.id) })} />
                  {t.name}{t.visibility === "hidden" && " (hidden)"}
                </label>
              ))}
            </div>
          </div>
        )}
        {error && <Alert>{error}</Alert>}
        <Button type="submit" loading={busy}>Create code</Button>
      </form>
    </div>
  );
}
