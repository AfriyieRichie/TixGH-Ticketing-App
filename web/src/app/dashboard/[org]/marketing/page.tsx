"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Stat, useOrg } from "@/components/dashboard/org";
import { Alert, Badge, Button, Card, Field, Input, PageLoader, Select, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { eventDate } from "@/lib/format";
import type { OrgEvent, Paginated } from "@/lib/types";

type Audience = {
  followers: number; past_attendees_opted_in: number; total_reachable: number; unsubscribed: number;
  daily_limit: number; can_send: boolean;
};
type Campaign = {
  id: number; subject: string; body: string; event: string | null; audience: string; status: string;
  automatic: boolean; recipients_count: number; sent_count: number; failed_count: number; created_at: string;
};

const AUDIENCES: Record<string, string> = {
  all: "Followers + past attendees who opted in",
  followers: "Followers only",
  past_attendees: "Past attendees who opted in",
};

export default function MarketingPage() {
  const { org, base, can } = useOrg();
  const { request } = useAuth();
  const [aud, setAud] = useState<Audience | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [events, setEvents] = useState<OrgEvent[]>([]);
  const [f, setF] = useState({ subject: "", body: "", event: "", audience: "all" });
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const api = `/organizations/${org.slug}`;

  const load = useCallback(() => {
    request<Audience>(`${api}/audience/`).then(setAud).catch(() => {});
    request<Paginated<Campaign>>(`${api}/campaigns/`).then((r) => setCampaigns(r.results)).catch(() => {});
  }, [request, api]);

  useEffect(() => {
    load();
    request<Paginated<OrgEvent>>(`${api}/events/?when=upcoming&status=published`)
      .then((r) => setEvents(r.results)).catch(() => {});
  }, [load, request, api]);

  if (!can("manage_events")) return <Alert kind="info">Your role doesn&apos;t include marketing.</Alert>;
  if (!aud) return <PageLoader />;
  const audience = aud;

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!confirm(`Send "${f.subject}" to up to ${audience.total_reachable} people?`)) return;
    setBusy(true);
    setMsg(null);
    try {
      const c = await request<Campaign>(`${api}/campaigns/`, { body: { ...f, event: f.event || null } });
      const sent = await request<Campaign>(`${api}/campaigns/${c.id}/send/`, { method: "POST" });
      setMsg({
        kind: "success",
        text: sent.status === "sent"
          ? `Sent to ${sent.sent_count} people.`
          : `Sending: ${sent.sent_count} of ${sent.recipients_count} so far. The rest go out automatically (daily limit ${audience.daily_limit}).`,
      });
      setF({ subject: "", body: "", event: "", audience: "all" });
    } catch (err) {
      setMsg({ kind: "error", text: err instanceof Error ? err.message : "Couldn't send." });
    } finally {
      setBusy(false);
      load();
    }
  }

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-extrabold">Marketing</h1>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Can reach" value={String(audience.total_reachable)} strong />
        <Stat label="Followers" value={String(audience.followers)} />
        <Stat label="Past attendees (opted in)" value={String(audience.past_attendees_opted_in)} />
        <Stat label="Unsubscribed" value={String(audience.unsubscribed)} />
      </div>
      <p className="-mt-4 text-sm text-zinc-500">
        People join your audience by following you or ticking &ldquo;Email me about future events&rdquo; at checkout.
        Followers are emailed automatically when you publish a new event. Every email has an unsubscribe link.
      </p>

      {!audience.can_send ? (
        <Alert kind="info">
          Campaigns are available to verified organizers.{" "}
          <Link href={`${base}/settings`} className="font-semibold underline">Request verification</Link>
        </Alert>
      ) : (
        <Card>
          <h2 className="mb-4 text-lg font-bold">New email campaign</h2>
          <form onSubmit={send} className="space-y-4">
            <Field label="Subject">
              <Input required maxLength={150} value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })}
                placeholder="Our biggest show of the year is here 🎉" />
            </Field>
            <Field label="Message" hint="Plain text. Leave a blank line between paragraphs.">
              <Textarea required rows={6} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Promote an event (adds a 'Get tickets' button)">
                <Select value={f.event} onChange={(e) => setF({ ...f, event: e.target.value })}>
                  <option value="">None</option>
                  {events.map((ev) => <option key={ev.slug} value={ev.slug}>{ev.title} · {eventDate(ev.start_at)}</option>)}
                </Select>
              </Field>
              <Field label="Send to">
                <Select value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })}>
                  {Object.entries(AUDIENCES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </Select>
              </Field>
            </div>
            {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
            <Button type="submit" loading={busy} disabled={!audience.total_reachable}>Send campaign</Button>
          </form>
        </Card>
      )}

      <section>
        <h2 className="mb-3 text-lg font-bold">Past campaigns</h2>
        {campaigns.length === 0 ? <p className="text-sm text-zinc-500">None yet.</p> : (
          <div className="divide-y divide-zinc-100 rounded-xl border border-zinc-200 bg-white">
            {campaigns.map((c) => (
              <div key={c.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{c.subject} {c.automatic && <Badge color="blue">Auto: new event</Badge>}</p>
                  <p className="text-xs text-zinc-500">{AUDIENCES[c.audience]} · {new Date(c.created_at).toLocaleDateString("en-GB")}</p>
                </div>
                <Badge color={c.status === "sent" ? "green" : c.status === "sending" ? "yellow" : "gray"}>{c.status}</Badge>
                <span className="text-sm text-zinc-600">
                  {c.sent_count}/{c.recipients_count} sent{c.failed_count ? ` · ${c.failed_count} failed` : ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
