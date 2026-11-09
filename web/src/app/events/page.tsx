import Link from "next/link";

import { EventGrid } from "@/components/EventCard";
import { SearchBar } from "@/components/SearchBar";
import { Empty } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { REGIONS } from "@/lib/format";
import type { Category, EventCardData, Paginated } from "@/lib/types";

export const metadata = { title: "Find events" };

type SP = Record<string, string | undefined>;
const FILTER_KEYS = ["q", "category", "region", "city", "when", "price", "format", "featured", "organizer", "sort", "page"];

const WHEN = [
  ["", "Any date"], ["today", "Today"], ["tomorrow", "Tomorrow"], ["this_weekend", "This weekend"],
  ["this_week", "This week"], ["next_7_days", "Next 7 days"], ["this_month", "This month"],
];
const PRICE = [["", "Any price"], ["free", "Free"], ["paid", "Paid"]];

function hrefWith(sp: SP, changes: SP) {
  const next = new URLSearchParams();
  for (const k of FILTER_KEYS) {
    const v = k in changes ? changes[k] : sp[k];
    if (v) next.set(k, v);
  }
  if (!("page" in changes)) next.delete("page");
  const s = next.toString();
  return s ? `/events?${s}` : "/events";
}

export default async function EventsPage({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const query = new URLSearchParams();
  for (const k of FILTER_KEYS) if (sp[k]) query.set(k, sp[k]!);
  const [data, categories] = await Promise.all([
    apiFetch<Paginated<EventCardData>>(`/events/?${query}`).catch(() => null),
    apiFetch<Category[]>("/categories/", { revalidate: 3600 }).catch(() => []),
  ]);
  const page = Number(sp.page ?? 1);

  const Chip = ({ k, v, label }: { k: string; v: string; label: string }) => {
    const active = (sp[k] ?? "") === v;
    return (
      <Link href={hrefWith(sp, { [k]: v || undefined })}
        className={`shrink-0 rounded-full border px-3 py-1.5 text-sm font-medium ${active ? "border-brand bg-brand text-white" : "border-zinc-300 bg-white hover:border-brand"}`}>
        {label}
      </Link>
    );
  };

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 max-w-2xl"><SearchBar initial={sp.q ?? ""} compact /></div>

      <div className="mb-3 flex gap-2 overflow-x-auto pb-1">{WHEN.map(([v, l]) => <Chip key={v} k="when" v={v} label={l} />)}</div>
      <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
        {PRICE.map(([v, l]) => <Chip key={v} k="price" v={v} label={l} />)}
        <span className="mx-1 w-px shrink-0 bg-zinc-300" />
        <Chip k="category" v="" label="All categories" />
        {categories.map((c) => <Chip key={c.slug} k="category" v={c.slug} label={c.name} />)}
      </div>
      <form action="/events" className="mb-6 flex flex-wrap items-center gap-2 text-sm">
        {FILTER_KEYS.filter((k) => k !== "region" && k !== "page" && sp[k]).map((k) => (
          <input key={k} type="hidden" name={k} value={sp[k]} />
        ))}
        <label htmlFor="region" className="text-zinc-600">Region:</label>
        <select id="region" name="region" defaultValue={sp.region ?? ""} className="rounded-lg border border-zinc-300 bg-white px-2 py-1.5">
          <option value="">All of Ghana</option>
          {Object.entries(REGIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <button className="rounded-lg border border-zinc-300 bg-white px-3 py-1.5 font-medium hover:border-brand">Apply</button>
        {query.toString() && <Link href="/events" className="text-brand hover:underline">Clear all</Link>}
      </form>

      {data === null ? (
        <Empty title="We couldn't load events">Please refresh the page in a moment.</Empty>
      ) : data.results.length === 0 ? (
        <Empty title="No events match your search">Try a different date, city or category.</Empty>
      ) : (
        <>
          <p className="mb-4 text-sm text-zinc-600">{data.count} event{data.count === 1 ? "" : "s"}</p>
          <EventGrid events={data.results} />
          <div className="mt-8 flex justify-center gap-3">
            {data.previous && <Link className="rounded-lg border bg-white px-4 py-2" href={hrefWith(sp, { page: String(page - 1) })}>← Previous</Link>}
            {data.next && <Link className="rounded-lg border bg-white px-4 py-2" href={hrefWith(sp, { page: String(page + 1) })}>Next →</Link>}
          </div>
        </>
      )}
    </main>
  );
}
