"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Alert, Button, Textarea } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Review = { id: number; rating: number; comment: string; author: string; organizer_reply: string; created_at: string };
type Data = { average: number | null; count: number; reviews: Review[]; can_review: boolean; reason: string; mine: Review | null };

export function Stars({ value, size = "text-base" }: { value: number; size?: string }) {
  return (
    <span className={`${size} tracking-tight text-amber-500`} aria-label={`${value} out of 5`}>
      {"★★★★★".slice(0, Math.round(value))}<span className="text-zinc-300">{"★★★★★".slice(Math.round(value))}</span>
    </span>
  );
}

export function Reviews({ slug, eventStarted }: { slug: string; eventStarted: boolean }) {
  const { user, ready, request } = useAuth();
  const [data, setData] = useState<Data | null>(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const url = `/events/${slug}/reviews/`;

  const load = useCallback(() => {
    (user ? request<Data>(url) : apiFetch<Data>(url)).then((d) => {
      setData(d);
      if (d.mine) { setRating(d.mine.rating); setComment(d.mine.comment); }
    }).catch(() => {});
  }, [user, request, url]);
  useEffect(() => { if (ready) load(); }, [ready, load]);

  if (!data || (!eventStarted && data.count === 0)) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg("");
    try {
      await request(url, { body: { rating, comment } });
      setMsg("Thanks for your review!");
      load();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Couldn't save your review.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section id="reviews" className="mt-8">
      <h2 className="flex items-center gap-3 text-xl font-bold">
        Reviews {data.average && <span className="flex items-center gap-1 text-base font-semibold"><Stars value={data.average} /> {data.average} ({data.count})</span>}
      </h2>
      {data.can_review ? (
        <form onSubmit={submit} className="mt-3 space-y-3 rounded-xl border border-zinc-200 bg-white p-4">
          <p className="font-semibold">{data.mine ? "Update your review" : "How was it?"}</p>
          <div className="flex gap-1 text-3xl">
            {[1, 2, 3, 4, 5].map((n) => (
              <button type="button" key={n} onClick={() => setRating(n)} aria-label={`${n} stars`}
                className={n <= rating ? "text-amber-500" : "text-zinc-300 hover:text-amber-300"}>★</button>
            ))}
          </div>
          <Textarea rows={3} maxLength={2000} placeholder="What did you enjoy? What could be better? (optional)" value={comment}
            onChange={(e) => setComment(e.target.value)} />
          <Button type="submit" disabled={!rating} loading={busy}>{data.mine ? "Update review" : "Post review"}</Button>
          {msg && <Alert kind={msg.startsWith("Thanks") ? "success" : "error"}>{msg}</Alert>}
        </form>
      ) : eventStarted && !user ? (
        <p className="mt-2 text-sm text-zinc-600"><Link href={`/login?next=/e/${slug}%23reviews`} className="font-semibold text-brand">Sign in</Link> to review if you attended.</p>
      ) : null}
      <div className="mt-4 space-y-3">
        {data.reviews.map((r) => (
          <div key={r.id} className="rounded-xl border border-zinc-200 bg-white p-4">
            <div className="flex items-center justify-between">
              <Stars value={r.rating} />
              <span className="text-xs text-zinc-500">{r.author} · {new Date(r.created_at).toLocaleDateString("en-GB")}</span>
            </div>
            {r.comment && <p className="mt-2 whitespace-pre-line text-zinc-700">{r.comment}</p>}
            {r.organizer_reply && (
              <div className="mt-3 rounded-lg bg-zinc-50 p-3 text-sm"><b>Organizer:</b> {r.organizer_reply}</div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
