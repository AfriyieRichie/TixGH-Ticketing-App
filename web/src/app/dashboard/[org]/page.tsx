"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Stat, useOrg } from "@/components/dashboard/org";
import { Alert, ButtonLink, Card, Empty, PageLoader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { cedis, eventDate } from "@/lib/format";


type Overview = {
  gross_sales: string; organizer_earnings: string; booking_fees: string; orders: number; tickets_sold: number;
  events: { upcoming: number; drafts: number; past: number };
  recent_orders: { reference: string; buyer_name: string; event: string; total: string; earnings: string; paid_at: string }[];
  top_events: { slug: string; title: string; earnings: string; orders: number }[];
  needs_review: number;
};

export default function OverviewPage() {
  const { org, base, can } = useOrg();
  const { request } = useAuth();
  const [data, setData] = useState<Overview | null>(null);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    request<Overview>(`/organizations/${org.slug}/overview/`).then(setData).catch(() => setDenied(true));
  }, [request, org.slug]);

  if (denied) return <Alert kind="info">Your role doesn&apos;t include sales data. Head to <Link href={`${base}/events`} className="underline">Events</Link>.</Alert>;
  if (!data) return <PageLoader />;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">Overview</h1>
        {can("manage_events") && <ButtonLink href={`${base}/events/new`}>+ Create event</ButtonLink>}
      </div>
      {data.needs_review > 0 && (
        <Alert>{data.needs_review} order(s) were paid but need review (e.g. sold out before payment completed). Our team will refund these buyers.</Alert>
      )}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Your earnings" value={cedis(data.organizer_earnings)} strong />
        <Stat label="Tickets sold" value={data.tickets_sold.toLocaleString()} />
        <Stat label="Orders" value={data.orders.toLocaleString()} />
        <Stat label="Upcoming events" value={String(data.events.upcoming)} sub={`${data.events.drafts} draft(s)`} />
      </div>
      <p className="-mt-4 text-xs text-zinc-500">
        Earnings are paid to your payout account automatically by our payment partner, usually the next business day.
        Gross sales incl. booking fees: {cedis(data.gross_sales)}.
      </p>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 font-bold">Recent orders</h2>
          {data.recent_orders.length === 0 ? <p className="text-sm text-zinc-500">No sales yet. Share your event link to get started.</p> : (
            <ul className="divide-y divide-zinc-100 text-sm">
              {data.recent_orders.map((o) => (
                <li key={o.reference} className="flex justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{o.buyer_name}</p>
                    <p className="truncate text-xs text-zinc-500">{o.event} · {eventDate(o.paid_at)}</p>
                  </div>
                  <span className="shrink-0 font-semibold">{cedis(o.earnings)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <h2 className="mb-3 font-bold">Top events</h2>
          {data.top_events.length === 0 ? <Empty title="No sales yet" /> : (
            <ul className="divide-y divide-zinc-100 text-sm">
              {data.top_events.map((e) => (
                <li key={e.slug} className="flex justify-between py-2">
                  <Link href={`${base}/events/${e.slug}`} className="truncate font-medium hover:text-brand">{e.title}</Link>
                  <span className="shrink-0 pl-2 font-semibold">{cedis(e.earnings)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
