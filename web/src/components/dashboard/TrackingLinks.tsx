"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert, Badge, Button, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { cedis } from "@/lib/format";
import type { OrgEvent } from "@/lib/types";

import { useOrg } from "./org";

type Link = {
  id: number; code: string; label: string; commission_percent: string | null; is_active: boolean; clicks: number;
  orders: number; tickets: number; revenue: string; commission: string | null; url: string;
};

export function TrackingLinks({ event }: { event: OrgEvent }) {
  const { org } = useOrg();
  const { request } = useAuth();
  const base = `/organizations/${org.slug}/events/${event.slug}/tracking-links/`;
  const [links, setLinks] = useState<Link[]>([]);
  const [f, setF] = useState({ code: "", label: "", commission_percent: "" });
  const [error, setError] = useState("");
  const [copied, setCopied] = useState<number | null>(null);

  const load = useCallback(() => { request<Link[]>(base).then(setLinks).catch(() => {}); }, [request, base]);
  useEffect(load, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await request(base, { body: { ...f, commission_percent: f.commission_percent || null } });
      setF({ code: "", label: "", commission_percent: "" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create link.");
    }
  }
  async function toggle(l: Link) {
    await request(`${base}${l.id}/`, { method: "PATCH", body: { is_active: !l.is_active } });
    load();
  }
  function copy(l: Link) {
    navigator.clipboard?.writeText(l.url);
    setCopied(l.id);
    setTimeout(() => setCopied(null), 1500);
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-zinc-600">
        Give each promoter, influencer or channel its own link. Sales through it are counted here: useful for paying
        commission and seeing what works (Instagram vs WhatsApp vs radio).
      </p>
      {links.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
              <tr><th className="px-4 py-3">Link</th><th>Clicks</th><th>Orders</th><th>Tickets</th><th>Your earnings</th><th>Commission</th><th /></tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {links.map((l) => (
                <tr key={l.id} className={l.is_active ? "" : "opacity-50"}>
                  <td className="px-4 py-3">
                    <p className="font-semibold">{l.label} {!l.is_active && <Badge>Off</Badge>}</p>
                    <button onClick={() => copy(l)} className="font-mono text-xs text-brand hover:underline">
                      {copied === l.id ? "Copied ✓" : `?ref=${l.code} · copy link`}
                    </button>
                  </td>
                  <td>{l.clicks}</td>
                  <td>{l.orders}</td>
                  <td>{l.tickets}</td>
                  <td>{cedis(l.revenue)}</td>
                  <td>{l.commission ? `${cedis(l.commission)} (${Number(l.commission_percent)}%)` : "—"}</td>
                  <td className="pr-3 text-right">
                    <Button size="sm" variant="ghost" onClick={() => toggle(l)}>{l.is_active ? "Turn off" : "Turn on"}</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form onSubmit={add} className="space-y-4 rounded-xl border border-zinc-200 bg-white p-5">
        <h3 className="font-bold">New tracking link</h3>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Who / where" hint="e.g. Kofi (influencer), Instagram ads">
            <Input required value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
          </Field>
          <Field label="Link code" hint="Letters, numbers, dashes">
            <Input required pattern="[A-Za-z0-9_-]+" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} placeholder="kofi" />
          </Field>
          <Field label="Commission % (optional)">
            <Input type="number" min={0} max={100} step="0.5" value={f.commission_percent}
              onChange={(e) => setF({ ...f, commission_percent: e.target.value })} />
          </Field>
        </div>
        {error && <Alert>{error}</Alert>}
        <Button type="submit">Create link</Button>
      </form>
    </div>
  );
}
