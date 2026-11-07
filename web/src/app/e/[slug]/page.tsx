import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Cover } from "@/components/EventCard";
import { TicketSelector } from "@/components/TicketSelector";
import { Badge } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import { eventDate, REGIONS, timeOnly } from "@/lib/format";
import type { EventDetail } from "@/lib/types";

async function getEvent(slug: string): Promise<EventDetail> {
  try {
    return await apiFetch<EventDetail>(`/events/${slug}/`, { revalidate: 30 });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const ev = await getEvent((await params).slug);
  return {
    title: ev.title,
    description: ev.summary || `${eventDate(ev.start_at)} · ${ev.venue?.name ?? "Online"}`,
    openGraph: { title: ev.title, description: ev.summary, images: ev.cover_image ? [ev.cover_image] : [] },
  };
}

const REFUND: Record<string, string> = {
  no_refunds: "No refunds", "1_day": "Refunds up to 1 day before the event",
  "7_days": "Refunds up to 7 days before the event", "30_days": "Refunds up to 30 days before the event",
};

export default async function EventPage({ params }: { params: Promise<{ slug: string }> }) {
  const ev = await getEvent((await params).slug);
  const v = ev.venue;
  const mapsUrl = v
    ? v.latitude && v.longitude
      ? `https://www.google.com/maps/search/?api=1&query=${v.latitude},${v.longitude}`
      : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${v.name}, ${v.city}, Ghana`)}`
    : null;
  const sameDay = new Date(ev.start_at).toDateString() === new Date(ev.end_at).toDateString();

  return (
    <main>
      <div className="relative h-56 overflow-hidden bg-zinc-900 sm:h-80">
        <div className="absolute inset-0 opacity-90"><Cover src={ev.cover_image} title={ev.title} /></div>
      </div>
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-8 lg:grid-cols-[1fr_380px]">
        <article className="min-w-0">
          {ev.status === "cancelled" && (
            <div className="mb-4 rounded-lg bg-red-50 p-4 text-red-800">
              <b>This event has been cancelled.</b> {ev.cancellation_reason}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {ev.category && <Badge color="brand">{ev.category.name}</Badge>}
            {ev.age_restriction > 0 && <Badge color="yellow">{ev.age_restriction}+</Badge>}
            {ev.format !== "in_person" && <Badge color="blue">{ev.format === "online" ? "Online" : "In person + online"}</Badge>}
          </div>
          <h1 className="mt-3 text-3xl font-extrabold leading-tight sm:text-4xl">{ev.title}</h1>
          {ev.summary && <p className="mt-2 text-lg text-zinc-600">{ev.summary}</p>}

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-zinc-200 bg-white p-4">
              <p className="text-sm font-semibold text-zinc-500">When</p>
              <p className="mt-1 font-semibold">{eventDate(ev.start_at, { year: true })}</p>
              <p className="text-sm text-zinc-600">
                Ends {sameDay ? timeOnly(ev.end_at) : eventDate(ev.end_at)}
              </p>
            </div>
            <div className="rounded-xl border border-zinc-200 bg-white p-4">
              <p className="text-sm font-semibold text-zinc-500">Where</p>
              {v ? (
                <>
                  <p className="mt-1 font-semibold">{v.name}</p>
                  <p className="text-sm text-zinc-600">{[v.address, v.city, REGIONS[v.region]].filter(Boolean).join(", ")}</p>
                  {v.digital_address && <p className="text-sm text-zinc-600">GPS: {v.digital_address}</p>}
                  {mapsUrl && <a href={mapsUrl} target="_blank" rel="noreferrer" className="text-sm font-semibold text-brand hover:underline">Open in Google Maps →</a>}
                </>
              ) : <p className="mt-1 font-semibold">Online: link sent with your ticket</p>}
            </div>
          </div>

          {ev.description && (
            <section className="mt-8">
              <h2 className="text-xl font-bold">About this event</h2>
              <div className="mt-3 whitespace-pre-line leading-relaxed text-zinc-700">{ev.description}</div>
            </section>
          )}
          {v?.directions && (
            <section className="mt-8">
              <h2 className="text-xl font-bold">Getting there</h2>
              <p className="mt-3 whitespace-pre-line text-zinc-700">{v.directions}</p>
            </section>
          )}
          <section className="mt-8">
            <h2 className="text-xl font-bold">Good to know</h2>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-zinc-700">
              <li>{REFUND[ev.refund_policy] ?? ev.refund_policy}. {ev.refund_policy_details}</li>
              <li>Tickets arrive by SMS{" "}and email with a QR code. No app needed.</li>
              {ev.allow_transfers && <li>You can send a ticket to a friend from &ldquo;My tickets&rdquo;.</li>}
              {ev.age_restriction > 0 && <li>Only for ages {ev.age_restriction} and over.</li>}
            </ul>
          </section>
          <section className="mt-8 rounded-xl border border-zinc-200 bg-white p-5">
            <p className="text-sm text-zinc-500">Organized by</p>
            <Link href={`/o/${ev.organizer.slug}`} className="text-lg font-bold hover:text-brand">
              {ev.organizer.name} {ev.organizer.is_verified && <span title="Verified organizer" className="text-brand">✓</span>}
            </Link>
            {ev.organizer_description && <p className="mt-2 line-clamp-3 text-sm text-zinc-600">{ev.organizer_description}</p>}
          </section>
        </article>

        <aside className="lg:sticky lg:top-20 lg:self-start">
          <TicketSelector event={ev} />
        </aside>
      </div>
    </main>
  );
}
