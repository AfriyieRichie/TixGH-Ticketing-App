"use client";

import { useEffect, useState } from "react";

import { PageLoader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { cedis } from "@/lib/format";
import type { OrgEvent } from "@/lib/types";

import { Stat, useOrg } from "./org";

type Stats = {
  organizer_earnings: string; gross_sales: string; orders: number; tickets_sold: number; checked_in: number;
  capacity: number; pending_orders: number;
  ticket_types: { id: number; name: string; price: string; quantity: number; sold: number; checked_in: number; earnings: string }[];
  daily: { date: string; orders: number; earnings: string }[];
};

export function EventStats({ event }: { event: OrgEvent }) {
  const { org } = useOrg();
  const { request } = useAuth();
  const [s, setS] = useState<Stats | null>(null);
  const [denied, setDenied] = useState(false);
  useEffect(() => {
    request<Stats>(`/organizations/${org.slug}/events/${event.slug}/stats/`).then(setS).catch(() => setDenied(true));
  }, [request, org.slug, event.slug, event]);

  if (denied) return null;
  if (!s) return <PageLoader />;
  const pct = s.capacity ? Math.round((s.tickets_sold / s.capacity) * 100) : 0;
  const maxDay = Math.max(1, ...s.daily.map((d) => Number(d.earnings)));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Your earnings" value={cedis(s.organizer_earnings)} strong />
        <Stat label="Tickets sold" value={`${s.tickets_sold}`} sub={`${pct}% of ${s.capacity}`} />
        <Stat label="Orders" value={`${s.orders}`} sub={s.pending_orders ? `${s.pending_orders} paying now` : undefined} />
        <Stat label="Checked in" value={`${s.checked_in}`} sub={s.tickets_sold ? `${Math.round((s.checked_in / s.tickets_sold) * 100)}% of sold` : undefined} />
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white p-5">
        <h3 className="mb-3 font-bold">Sales by ticket type</h3>
        <div className="space-y-3">
          {s.ticket_types.map((t) => (
            <div key={t.id}>
              <div className="flex justify-between text-sm">
                <span className="font-medium">{t.name}</span>
                <span className="text-zinc-600">{t.sold}/{t.quantity} · {cedis(t.earnings)}</span>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-zinc-100">
                <div className="h-full rounded-full bg-brand" style={{ width: `${t.quantity ? (t.sold / t.quantity) * 100 : 0}%` }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {s.daily.length > 0 && (
        <div className="rounded-xl border border-zinc-200 bg-white p-5">
          <h3 className="mb-4 font-bold">Daily earnings (last 30 days)</h3>
          <div className="flex h-40 items-end gap-1">
            {s.daily.map((d) => (
              <div key={d.date} className="group relative flex-1">
                <div className="rounded-t bg-brand/80 hover:bg-brand" style={{ height: `${(Number(d.earnings) / maxDay) * 150}px`, minHeight: 2 }} />
                <div className="pointer-events-none absolute bottom-full left-1/2 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded bg-zinc-900 px-2 py-1 text-xs text-white group-hover:block">
                  {d.date}: {cedis(d.earnings)} ({d.orders} orders)
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
