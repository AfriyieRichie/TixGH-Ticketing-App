"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { statusBadge, useOrg } from "@/components/dashboard/org";
import { Cover } from "@/components/EventCard";
import { ButtonLink, Empty, PageLoader } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { eventDate } from "@/lib/format";
import type { OrgEvent, Paginated } from "@/lib/types";

const TABS = [["upcoming", "Upcoming"], ["draft", "Drafts"], ["past", "Past"], ["", "All"]] as const;

export default function EventsPage() {
  const { org, base, can } = useOrg();
  const { request } = useAuth();
  const [tab, setTab] = useState<string>("upcoming");
  const [events, setEvents] = useState<OrgEvent[] | null>(null);

  useEffect(() => {
    setEvents(null);
    const q = tab === "draft" ? "status=draft" : tab ? `when=${tab}` : "";
    request<Paginated<OrgEvent>>(`/organizations/${org.slug}/events/?${q}`).then((r) => setEvents(r.results));
  }, [request, org.slug, tab]);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">Events</h1>
        {can("manage_events") && <ButtonLink href={`${base}/events/new`}>+ Create event</ButtonLink>}
      </div>
      <div className="mt-4 flex gap-2">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold ${tab === v ? "bg-zinc-900 text-white" : "border border-zinc-300 bg-white"}`}>{l}</button>
        ))}
      </div>
      <div className="mt-6 space-y-3">
        {events === null ? <PageLoader /> : events.length === 0 ? (
          <Empty title="No events here yet">{can("manage_events") && <Link href={`${base}/events/new`} className="font-semibold text-brand">Create your first event →</Link>}</Empty>
        ) : events.map((ev) => {
          const sold = ev.ticket_types.reduce((s, t) => s + t.quantity_sold, 0);
          const cap = ev.ticket_types.reduce((s, t) => s + t.quantity, 0);
          return (
            <Link key={ev.slug} href={`${base}/events/${ev.slug}`}
              className="flex items-center gap-4 rounded-xl border border-zinc-200 bg-white p-3 hover:border-brand">
              <div className="hidden h-16 w-28 shrink-0 overflow-hidden rounded-lg sm:block"><Cover src={ev.cover_image} title={ev.title} /></div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-bold">{ev.title}</p>
                <p className="text-sm text-zinc-600">{eventDate(ev.start_at, { year: true })}{ev.venue_detail && ` · ${ev.venue_detail.name}`}</p>
              </div>
              <div className="text-right">
                {statusBadge(ev)}
                <p className="mt-1 text-sm text-zinc-600">{sold}/{cap} sold</p>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
