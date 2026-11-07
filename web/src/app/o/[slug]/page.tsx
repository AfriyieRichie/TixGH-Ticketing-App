import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { EventGrid } from "@/components/EventCard";
import { Empty } from "@/components/ui";
import { ApiError, apiFetch, mediaUrl } from "@/lib/api";
import { REGIONS } from "@/lib/format";
import type { EventCardData, Paginated } from "@/lib/types";

type PublicOrg = {
  name: string; slug: string; description: string; logo: string | null; website: string;
  instagram: string; x_handle: string; facebook: string; tiktok: string; region: string; city: string; is_verified: boolean;
};

async function getOrg(slug: string) {
  try {
    return await apiFetch<PublicOrg>(`/organizations/public/${slug}/`, { revalidate: 300 });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const org = await getOrg((await params).slug);
  return { title: org.name, description: org.description.slice(0, 160) };
}

export default async function OrganizerPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const [org, events] = await Promise.all([
    getOrg(slug),
    apiFetch<Paginated<EventCardData>>(`/events/?organizer=${slug}`, { revalidate: 60 }).catch(() => null),
  ]);
  const socials = [
    org.website && { label: "Website", href: org.website },
    org.instagram && { label: "Instagram", href: `https://instagram.com/${org.instagram.replace("@", "")}` },
    org.x_handle && { label: "X", href: `https://x.com/${org.x_handle.replace("@", "")}` },
    org.facebook && { label: "Facebook", href: org.facebook.startsWith("http") ? org.facebook : `https://facebook.com/${org.facebook}` },
    org.tiktok && { label: "TikTok", href: `https://tiktok.com/@${org.tiktok.replace("@", "")}` },
  ].filter(Boolean) as { label: string; href: string }[];
  const logo = mediaUrl(org.logo);

  return (
    <main className="mx-auto max-w-6xl px-4 py-10">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
        <div className="grid h-24 w-24 shrink-0 place-items-center overflow-hidden rounded-2xl bg-brand text-3xl font-extrabold text-white">
          {logo ? <img src={logo} alt="" className="h-full w-full object-cover" /> : org.name[0]}
        </div>
        <div>
          <h1 className="text-3xl font-extrabold">
            {org.name} {org.is_verified && <span className="text-brand" title="Verified organizer">✓</span>}
          </h1>
          <p className="text-zinc-600">{[org.city, REGIONS[org.region]].filter(Boolean).join(", ")}</p>
          <div className="mt-2 flex flex-wrap gap-3 text-sm">
            {socials.map((s) => <a key={s.label} href={s.href} target="_blank" rel="noreferrer" className="font-semibold text-brand hover:underline">{s.label}</a>)}
          </div>
        </div>
      </div>
      {org.description && <p className="mt-6 max-w-3xl whitespace-pre-line text-zinc-700">{org.description}</p>}
      <h2 className="mb-4 mt-10 text-xl font-bold">Upcoming events</h2>
      {events?.results.length ? <EventGrid events={events.results} /> : <Empty title="No upcoming events right now" />}
    </main>
  );
}
