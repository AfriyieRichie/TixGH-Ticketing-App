"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { EventForm } from "@/components/dashboard/EventForm";
import { useOrg } from "@/components/dashboard/org";

export default function NewEventPage() {
  const { base } = useOrg();
  const router = useRouter();
  return (
    <div className="max-w-3xl">
      <Link href={`${base}/events`} className="text-sm font-semibold text-brand">← Events</Link>
      <h1 className="mb-6 mt-2 text-2xl font-extrabold">Create an event</h1>
      <EventForm onSaved={(ev) => router.push(`${base}/events/${ev.slug}?tab=tickets`)} />
    </div>
  );
}
