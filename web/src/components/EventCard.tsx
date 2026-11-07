import Link from "next/link";

import { mediaUrl } from "@/lib/api";
import { dayBadge, eventDate, priceLabel } from "@/lib/format";
import type { EventCardData } from "@/lib/types";

const GRADIENTS = [
  "from-teal-600 to-emerald-500", "from-amber-500 to-orange-600", "from-rose-500 to-fuchsia-600",
  "from-sky-600 to-indigo-600", "from-lime-600 to-teal-600",
];

export function Cover({ src, title, className = "" }: { src: string | null; title: string; className?: string }) {
  const url = mediaUrl(src);
  if (url) return <img src={url} alt="" className={`h-full w-full object-cover ${className}`} loading="lazy" />;
  const g = GRADIENTS[title.length % GRADIENTS.length];
  return (
    <div className={`flex h-full w-full items-end bg-gradient-to-br ${g} p-4 ${className}`}>
      <span className="line-clamp-2 text-lg font-extrabold leading-tight text-white/90">{title}</span>
    </div>
  );
}

export function EventCard({ event }: { event: EventCardData }) {
  const { month, day } = dayBadge(event.start_at);
  return (
    <Link href={`/e/${event.slug}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-zinc-200 bg-white transition hover:-translate-y-0.5 hover:shadow-lg">
      <div className="relative aspect-[16/9] overflow-hidden">
        <Cover src={event.cover_image} title={event.title} className="transition group-hover:scale-105" />
        <div className="absolute left-3 top-3 rounded-lg bg-white px-2.5 py-1 text-center shadow">
          <div className="text-[10px] font-bold text-brand">{month}</div>
          <div className="text-lg font-extrabold leading-none">{day}</div>
        </div>
        {event.sold_out && <span className="absolute right-3 top-3 rounded-full bg-zinc-900 px-2.5 py-1 text-xs font-bold text-white">Sold out</span>}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-4">
        {event.category && <span className="text-xs font-semibold uppercase tracking-wide text-brand">{event.category.name}</span>}
        <h3 className="line-clamp-2 font-bold text-zinc-900 group-hover:text-brand">{event.title}</h3>
        <p className="text-sm text-zinc-600">{eventDate(event.start_at)}</p>
        <p className="text-sm text-zinc-600">{event.venue ? `${event.venue.name}, ${event.venue.city}` : "Online"}</p>
        <div className="mt-auto flex items-center justify-between pt-3">
          <span className="font-bold text-zinc-900">{priceLabel(event.price_from, event.is_free)}</span>
          <span className="truncate pl-2 text-xs text-zinc-500">
            {event.organizer.name}{event.organizer.is_verified && " ✓"}
          </span>
        </div>
      </div>
    </Link>
  );
}

export function EventGrid({ events }: { events: EventCardData[] }) {
  return (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {events.map((e) => <EventCard key={e.slug} event={e} />)}
    </div>
  );
}
