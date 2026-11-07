"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Attendees } from "@/components/dashboard/Attendees";
import { EventForm } from "@/components/dashboard/EventForm";
import { EventStats } from "@/components/dashboard/EventStats";
import { statusBadge, useOrg } from "@/components/dashboard/org";
import { PromoCodes } from "@/components/dashboard/PromoCodes";
import { TicketTypes } from "@/components/dashboard/TicketTypes";
import { Alert, Button, Field, PageLoader, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { eventDate } from "@/lib/format";
import type { OrgEvent } from "@/lib/types";

export default function Page() {
  return <Suspense fallback={<PageLoader />}><ManageEvent /></Suspense>;
}

function ManageEvent() {
  const { slug } = useParams<{ slug: string }>();
  const { org, base, can } = useOrg();
  const { request } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [ev, setEv] = useState<OrgEvent | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const editable = can("manage_events");
  const finance = can("view_finance") || editable;

  const tabs = [
    ["overview", "Overview"], ...(editable ? [["details", "Details"], ["tickets", "Tickets"], ["promo", "Promo codes"]] : []),
    ...(finance ? [["attendees", "Attendees"]] : []),
  ] as [string, string][];
  const tab = params.get("tab") ?? "overview";
  const goTab = (t: string) => router.replace(`${base}/events/${slug}?tab=${t}`, { scroll: false });

  const path = `/organizations/${org.slug}/events/${slug}/`;
  const load = useCallback(() => { request<OrgEvent>(path).then(setEv).catch(() => setError("Event not found.")); }, [request, path]);
  useEffect(load, [load]);

  async function act(action: string, body?: unknown) {
    setBusy(action);
    setError("");
    try {
      setEv(await request<OrgEvent>(`${path}${action}/`, { method: "POST", body }));
      if (action === "cancel") setCancelling(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed.");
    } finally {
      setBusy("");
    }
  }
  async function duplicate() {
    setBusy("duplicate");
    try {
      const copy = await request<OrgEvent>(`${path}duplicate/`, { method: "POST" });
      router.push(`${base}/events/${copy.slug}?tab=details`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not duplicate.");
      setBusy("");
    }
  }

  if (error && !ev) return <Alert>{error}</Alert>;
  if (!ev) return <PageLoader />;
  const publicUrl = typeof window !== "undefined" ? `${window.location.origin}/e/${ev.slug}` : `/e/${ev.slug}`;

  return (
    <div>
      <Link href={`${base}/events`} className="text-sm font-semibold text-brand">← Events</Link>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold">{ev.title}</h1>
          <p className="text-zinc-600">{eventDate(ev.start_at, { year: true })}{ev.venue_detail && ` · ${ev.venue_detail.name}, ${ev.venue_detail.city}`}</p>
          <div className="mt-2">{statusBadge(ev)}</div>
        </div>
        {editable && (
          <div className="flex flex-wrap gap-2">
            {ev.status === "draft" && <Button onClick={() => act("publish")} loading={busy === "publish"} disabled={ev.publish_problems.length > 0}>Publish</Button>}
            {ev.status === "published" && ev.tickets_sold === 0 && <Button variant="secondary" onClick={() => act("unpublish")} loading={busy === "unpublish"}>Unpublish</Button>}
            <Button variant="secondary" onClick={duplicate} loading={busy === "duplicate"}>Duplicate</Button>
            {ev.status === "published" && !ev.has_ended && <Button variant="danger" onClick={() => setCancelling(true)}>Cancel event</Button>}
          </div>
        )}
      </div>

      {error && <div className="mt-4"><Alert>{error}</Alert></div>}
      {ev.status === "draft" && ev.publish_problems.length > 0 && (
        <div className="mt-4"><Alert kind="info"><b>Before you can publish:</b> {ev.publish_problems.join(" ")}</Alert></div>
      )}
      {ev.status === "published" && (
        <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <span>🎉 Live at</span>
          <a href={`/e/${ev.slug}`} target="_blank" className="font-mono font-semibold underline">{publicUrl}</a>
          <button className="font-semibold text-brand" onClick={() => navigator.clipboard?.writeText(publicUrl)}>Copy link</button>
          <a className="font-semibold text-brand" target="_blank" rel="noreferrer"
            href={`https://wa.me/?text=${encodeURIComponent(`Get your tickets for ${ev.title}: ${publicUrl}`)}`}>Share on WhatsApp</a>
        </div>
      )}
      {cancelling && (
        <div className="mt-4 space-y-3 rounded-xl border-2 border-red-200 bg-red-50 p-5">
          <p className="font-bold text-red-900">Cancel this event?</p>
          <p className="text-sm text-red-900">All {ev.tickets_sold} ticket holders will get an SMS and email. This can&apos;t be undone.</p>
          <Field label="Reason (shown to buyers)"><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          <div className="flex gap-2">
            <Button variant="danger" disabled={!reason.trim()} loading={busy === "cancel"} onClick={() => act("cancel", { reason })}>Yes, cancel event</Button>
            <Button variant="ghost" onClick={() => setCancelling(false)}>Keep it</Button>
          </div>
        </div>
      )}

      <div className="mt-6 flex gap-1 overflow-x-auto border-b border-zinc-200">
        {tabs.map(([v, l]) => (
          <button key={v} onClick={() => goTab(v)}
            className={`shrink-0 border-b-2 px-4 py-2 font-semibold ${tab === v ? "border-brand text-brand" : "border-transparent text-zinc-600 hover:text-zinc-900"}`}>{l}</button>
        ))}
      </div>
      <div className="mt-6">
        {tab === "overview" && (finance ? <EventStats event={ev} /> : <p className="text-zinc-600">You have view-only access to this event.</p>)}
        {tab === "details" && editable && <EventForm event={ev} onSaved={setEv} />}
        {tab === "tickets" && editable && <TicketTypes event={ev} onChange={load} />}
        {tab === "promo" && editable && <PromoCodes event={ev} />}
        {tab === "attendees" && finance && <Attendees event={ev} />}
      </div>
    </div>
  );
}
