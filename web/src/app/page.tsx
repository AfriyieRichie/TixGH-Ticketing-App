import Link from "next/link";

import { EventGrid } from "@/components/EventCard";
import { SearchBar } from "@/components/SearchBar";
import { Empty } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import type { Category, EventCardData, Paginated } from "@/lib/types";

export const revalidate = 60;

async function load() {
  const safe = <T,>(p: Promise<T>, fallback: T) => p.catch(() => fallback);
  const empty: Paginated<EventCardData> = { count: 0, next: null, previous: null, results: [] };
  const [featured, weekend, upcoming, categories] = await Promise.all([
    safe(apiFetch<Paginated<EventCardData>>("/events/?featured=true", { revalidate: 60 }), empty),
    safe(apiFetch<Paginated<EventCardData>>("/events/?when=this_weekend", { revalidate: 60 }), empty),
    safe(apiFetch<Paginated<EventCardData>>("/events/", { revalidate: 60 }), empty),
    safe(apiFetch<Category[]>("/categories/", { revalidate: 3600 }), []),
  ]);
  return { featured: featured.results, weekend: weekend.results, upcoming: upcoming.results, categories };
}

const CITIES = [
  { name: "Accra", region: "greater_accra" }, { name: "Kumasi", region: "ashanti" },
  { name: "Takoradi", region: "western" }, { name: "Tamale", region: "northern" },
  { name: "Cape Coast", region: "central" }, { name: "Ho", region: "volta" },
];

export default async function Home() {
  const { featured, weekend, upcoming, categories } = await load();
  return (
    <main>
      <section className="bg-gradient-to-br from-brand-dark via-brand to-emerald-600 text-white">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:py-24">
          <h1 className="max-w-2xl text-4xl font-extrabold leading-tight sm:text-5xl">
            Find your next event in Ghana
          </h1>
          <p className="mt-4 max-w-xl text-lg text-white/85">
            Concerts, conferences, church programs, comedy and more. Pay with MoMo or card and get your ticket by SMS.
          </p>
          <div className="mt-8 max-w-2xl"><SearchBar /></div>
          <div className="mt-6 flex flex-wrap gap-2">
            {CITIES.map((c) => (
              <Link key={c.name} href={`/events?city=${encodeURIComponent(c.name)}`}
                className="rounded-full bg-white/15 px-3 py-1 text-sm font-medium hover:bg-white/25">
                {c.name}
              </Link>
            ))}
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-6xl space-y-14 px-4 py-12">
        <section>
          <h2 className="mb-4 text-xl font-bold">Browse by category</h2>
          <div className="flex gap-2 overflow-x-auto pb-2">
            {categories.map((c) => (
              <Link key={c.slug} href={`/events?category=${c.slug}`}
                className="shrink-0 rounded-full border border-zinc-300 bg-white px-4 py-2 text-sm font-medium hover:border-brand hover:text-brand">
                {c.name}
              </Link>
            ))}
          </div>
        </section>

        {featured.length > 0 && (
          <Section title="Featured events" href="/events?featured=true"><EventGrid events={featured.slice(0, 6)} /></Section>
        )}
        {weekend.length > 0 && (
          <Section title="This weekend" href="/events?when=this_weekend"><EventGrid events={weekend.slice(0, 6)} /></Section>
        )}
        <Section title="Upcoming events" href="/events">
          {upcoming.length ? <EventGrid events={upcoming.slice(0, 9)} /> : (
            <Empty title="No upcoming events yet">Check back soon, or <Link href="/dashboard" className="text-brand underline">list your own event</Link>.</Empty>
          )}
        </Section>

        <section className="grid items-center gap-6 rounded-2xl bg-zinc-900 p-8 text-white sm:grid-cols-[1fr_auto] sm:p-12">
          <div>
            <h2 className="text-2xl font-bold">Organizing an event?</h2>
            <p className="mt-2 text-zinc-300">
              Sell tickets in minutes. Get paid straight to your MoMo or bank account, scan tickets at the gate, and see sales live.
              Free events are free.
            </p>
          </div>
          <Link href="/dashboard" className="rounded-lg bg-accent px-6 py-3 text-center font-bold text-zinc-900 hover:bg-amber-400">
            Start selling
          </Link>
        </section>
      </div>
    </main>
  );
}

function Section({ title, href, children }: { title: string; href: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-4 flex items-end justify-between">
        <h2 className="text-xl font-bold">{title}</h2>
        <Link href={href} className="text-sm font-semibold text-brand hover:underline">See all →</Link>
      </div>
      {children}
    </section>
  );
}
