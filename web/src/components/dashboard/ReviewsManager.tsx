"use client";

import { useCallback, useEffect, useState } from "react";

import { Stars } from "@/components/growth/Reviews";
import { Button, Empty, Textarea } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { OrgEvent } from "@/lib/types";

import { useOrg } from "./org";

type Review = { id: number; rating: number; comment: string; author: string; organizer_reply: string; created_at: string };
type Data = { average: number | null; count: number; reviews: Review[] };

export function ReviewsManager({ event }: { event: OrgEvent }) {
  const { org } = useOrg();
  const { request } = useAuth();
  const [data, setData] = useState<Data | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});

  const load = useCallback(() => {
    apiFetch<Data>(`/events/${event.slug}/reviews/`).then(setData).catch(() => {});
  }, [event.slug]);
  useEffect(load, [load]);

  async function reply(r: Review) {
    await request(`/organizations/${org.slug}/events/${event.slug}/reviews/${r.id}/reply/`, {
      body: { reply: drafts[r.id] ?? r.organizer_reply },
    });
    load();
  }

  if (!data) return null;
  if (!data.count) {
    return <Empty title="No reviews yet">Attendees get an email asking for a review a few hours after the event ends.</Empty>;
  }
  return (
    <div className="space-y-4">
      <p className="flex items-center gap-2 font-semibold">
        <Stars value={data.average ?? 0} /> {data.average} average from {data.count} review{data.count === 1 ? "" : "s"}
      </p>
      {data.reviews.map((r) => (
        <div key={r.id} className="space-y-2 rounded-xl border border-zinc-200 bg-white p-4">
          <div className="flex justify-between"><Stars value={r.rating} /><span className="text-xs text-zinc-500">{r.author}</span></div>
          {r.comment && <p className="text-zinc-700">{r.comment}</p>}
          <Textarea rows={2} placeholder="Public reply (optional)" value={drafts[r.id] ?? r.organizer_reply}
            onChange={(e) => setDrafts({ ...drafts, [r.id]: e.target.value })} />
          <Button size="sm" variant="secondary" onClick={() => reply(r)}>{r.organizer_reply ? "Update reply" : "Reply"}</Button>
        </div>
      ))}
    </div>
  );
}
